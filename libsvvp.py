#!/usr/bin/python

import pxssh
import sys
import ConfigParser
import subprocess
import time
import tempfile
import shutil
import os


class ExecError(Exception):
    pass


class Server(object):
    def __init__(self, hostname, username, passwd):
        self.hostname = hostname
        self.username = username
        self.passwd = passwd

    def sendcmd(self, cmd, check=True, timeout=-1):
        s = pxssh.pxssh()
        s.login(self.hostname, self.username, self.passwd, login_timeout=60)
        s.sendline(cmd)
        s.prompt(timeout)
        out = s.before.strip(cmd).strip()

        # Check the command were execute successfully on the remote server
        retcode_cmd = 'echo $?'
        s.sendline(retcode_cmd)
        s.prompt()
        retcode = s.before.strip(retcode_cmd).strip()
        if check:
            if retcode != '0':
                raise ExecError("[%s]-[%s] failed:\n%s" % (self.hostname, cmd, out))
            else:
                return out
        return out

    def scp(self, local, rmt, timeout=600):
        # Check whether the sshd is enabled on the remote server
        try:
            self.sendcmd('hostname', check=False)
        except Exception:
            raise ExecError("Reason: password or sshd on remote server")

        scp_put = '''
set timeout %s
spawn scp %s %s@%s:%s
expect "(yes/no)?" {
send "yes\r"
expect "password:"
send "%s\r"
} "password:" {send "%s\r"}
expect eof
exit'''

        cmd = "echo '%s' > /tmp/scp_put.cmd" % (scp_put % (
            timeout,
            local,
            self.username,
            self.hostname,
            rmt,
            self.passwd,
            self.passwd)
        )
        execute(cmd)
        execute("expect /tmp/scp_put.cmd")
        execute("rm /tmp/scp_put.cmd")

        # Check whether the file were copied successfully
        cmd = "test -f %s" % rmt
        try:
            self.sendcmd(cmd)
        except ExecError:
            raise Exception("Reason: unknown")


class Sut(Server):
    def __init__(self, hostname, user, password, workdir='/data'):
        super(Sut, self).__init__(hostname, user, password)
        self._make_workdir(workdir)
        self.workdir = workdir

    def _make_workdir(self, workdir):
        cmd = "test -d %s" % workdir
        try:
            self.sendcmd(cmd)
        except ExecError:
            cmd = "mkdir -p %s" % workdir
            self.sendcmd(cmd)

    def gen_internal_bridge(self, bridge, nic):
        # Copy the nic configure file to the remote server
        ifcfg_cfg = '''DEVICE=%s
HWADDR=%s
BRIDGE=%s
ONBOOT=yes
NM_CONTROLLED=no
IPV6_AUTOCONF=no
PEERNTP=yes
IPV6INIT=no'''
        cmd_get_mac = "ip link show %s|grep 'link/ether'" % nic
        output = self.sendcmd(cmd_get_mac)
        mac = output.split()[1]

        cmd = "echo '%s' > /tmp/ifcfg_nic.cfg" % (ifcfg_cfg % (
            nic,
            mac,
            bridge))
        execute(cmd)

        rmt_ifcfgnic = self.workdir + '/ifcfg_nic.cfg'
        self.scp("/tmp/ifcfg_nic.cfg", rmt_ifcfgnic)
        self.sendcmd("mv -f %s /etc/sysconfig/network-scripts/ifcfg-%s" % (rmt_ifcfgnic, nic))

        # Copy the bridge configure file to the remote server
        ifcfg_br = '''DEVICE=%s
TYPE=Bridge
DELAY=0
STP=off
ONBOOT=yes
BOOTPROTO=dhcp
DEFROUTE=yes
NM_CONTROLLED=no
IPV6_AUTOCONF=no
PEERNTP=yes
IPV6INIT=no
HOTPLUG=no'''
        cmd = "echo '%s' > /tmp/ifcfg_br.cfg" % (ifcfg_br % (
            bridge))
        execute(cmd)

        rmt_ifcfgbr = self.workdir + '/ifcfg_br.cfg'
        self.scp("/tmp/ifcfg_br.cfg", rmt_ifcfgbr)
        execute("rm /tmp/ifcfg_br.cfg")

        self.sendcmd("mv -f %s /etc/sysconfig/network-scripts/ifcfg-%s" % (rmt_ifcfgbr, bridge))

        # Delete the bridge if exists
        cmd = "ip link show %s" % bridge
        try:
            self.sendcmd(cmd)
        except ExecError:
            pass
        else:
            # Get the device under the existing bridge
            cmd = "ifdown %s" % bridge
            self.sendcmd(cmd, check=False)

            cmd = "brctl delbr %s" % bridge
            self.sendcmd(cmd)

        # Add the bridge and interface
        cmd = "brctl addbr %s " % bridge
        self.sendcmd(cmd)
        cmd = "brctl addif %s %s" % (bridge, nic)
        self.sendcmd(cmd)

        # Add the route to avoid the disconnection from remote server
        # Firstly, get the default gateway
        cmd = "ip route list|grep default|grep -v %s|grep -v %s" % (nic, bridge)
        try:
            output = self.sendcmd(cmd)
        except ExecError:
            raise Exception("No Default gateway for Public network")
        s, tmpfile = tempfile.mkstemp()
        with open(tmpfile, 'w') as f:
            f.write(output)
        cmd = "sed -n '/^default/p' %s" % tmpfile
        output = execute(cmd)
        default_gw = output.split()[2]

        # Add a route to avoid the disconnection by "ifup bridge"
        cmd = "ip route list|grep 10.0.0.0/8|grep %s" % default_gw
        try:
            self.sendcmd(cmd)
        except ExecError:
            cmd = "ip route add 10.0.0.0/8 via %s" % default_gw
            self.sendcmd(cmd)

        # ifup the bridge, may create the internal default gateway
        cmd = "ifup %s" % bridge
        try:
            self.sendcmd(cmd)
        except ExecError as e:
            print e

        # Delete the 192.168 gateway since no impact for internal comunicatation
        cmd = "ip route list|grep default|grep %s" % bridge
        try:
            self.sendcmd(cmd)
        except ExecError:
            pass
        else:
            cmd = "ip route list|grep default|grep %s" % bridge
            internal_gw = self.sendcmd(cmd).split()[2]
            cmd = "ip route del default via %s" % internal_gw
            self.sendcmd(cmd)

        # Add the original gateway
        cmd = "ip route list|grep default|grep %s" % default_gw
        try:
            self.sendcmd(cmd)
        except ExecError:
            cmd = "ip route add default via %s" % default_gw
            self.sendcmd(cmd)
        # Delete the new add route if the original gateway were added
        cmd = "ip route list|grep default|grep %s" % default_gw
        try:
            self.sendcmd(cmd)
        except ExecError:
            pass
        else:
            cmd = "ip route del 10.0.0.0/8"
            self.sendcmd(cmd, check=False)

    def gen_internal_qemu_ifup(self, bridge):
        qemu_ifup = '''#!/bin/sh
switch=%s
/sbin/ip link set $1 up
/usr/sbin/brctl addif ${switch} $1'''
        cmd = "echo '%s' > /tmp/qemu_ifup.cmd" % (qemu_ifup % (
            bridge))
        execute(cmd)

        rmt_qemu = self.workdir + '/qemu-ifup'
        self.scp("/tmp/qemu_ifup.cmd", rmt_qemu)
        cmd = "chmod +x %s" % rmt_qemu
        self.sendcmd(cmd)
        execute("rm /tmp/qemu_ifup.cmd")

    def gen_raw_disk(self, path, size):
        cmd = "qemu-img create -f raw %s %s" % (path, size)
        self.sendcmd(cmd)

    def gen_sut_vm_install(self, vm_info):
        vm_name = vm_info["vm_name"]
        cpu_mode = vm_info["cpu_mode"]
        mem = vm_info["mem"]
        core = vm_info["core"]
        product = vm_info["product"]
        version = vm_info["version"]
        iso = vm_info["iso"]
        disk = vm_info["disk"]
        usb_disk = vm_info["usb_disk"]
        virtio = vm_info["virtio"]
        vncport = vm_info.get("vncport")
        if not vncport:
            vncport = 0

        # Generate the uuid for creating the VM
        uuid = execute('uuidgen').strip()
        # Generate the mac address for creating the nic of VM
        cmd = "echo $RANDOM | md5sum | sed 's/\(..\)/&:/g' | cut -c1-11"
        random_mac = execute(cmd).strip()

        vm_install = '''/usr/libexec/qemu-kvm -name %s -M pc -cpu %s -enable-kvm -m %sG -smp %s,cores=%s \
-uuid %s \
-smbios type=1,manufacturer="Red Hat",product="%s",version=%s,serial=4C4C4544-0056-4210-8032-C3C04F463358,uuid=%s \
-nodefconfig -rtc base=localtime,driftfix=slew \
-drive file=%s,if=none,media=cdrom,id=drive-ide0-1-0,readonly=on,format=raw,serial= \
-device ide-drive,bus=ide.1,unit=0,drive=drive-ide0-1-0,id=ide0-1-0 \
-drive file=%s,if=none,format=raw,cache=none,werror=stop,rerror=stop,id=drive-virtio-disk0,aio=native \
-device virtio-blk-pci,scsi=off,bus=pci.0,addr=0x5,drive=drive-virtio-disk0,id=virtio-disk0,bootindex=1 \
-netdev tap,script=%s/qemu-ifup,id=hostnet0,vhost=on -device virtio-net-pci,netdev=hostnet0,id=net0,mac=52:52:%s,bus=pci.0 -device piix3-usb-uhci,id=usb,bus=pci.0,addr=0x1.0x2 -device usb-tablet,id=tablet0 -device usb-ehci,id=ehci0 \
-vnc :%s -chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s4=1 \
-fda %s \
-monitor stdio -name %s \
-boot menu=on \
-device usb-ehci,id=ehci1 -drive file=%s,if=none,id=drive-usb-2-0,media=disk,format=raw,cache=none,werror=stop,rerror=stop,aio=threads -device usb-storage,bus=ehci0.0,drive=drive-usb-2-0,id=usb-2-0,removable=on -rtc base=localtime,clock=host,driftfix=slew
'''
        cmd = "echo '%s' > /tmp/vm_install.cmd" % (vm_install % (
            vm_name,
            cpu_mode,
            mem,
            core,
            core,
            uuid,
            product,
            version,
            uuid,
            iso,
            disk,
            self.workdir,
            random_mac,
            vncport,
            virtio,
            vm_name,
            usb_disk))
        execute(cmd)

        rmt_install = self.workdir + '/sut_vm_install_%s.cmd' % vm_name
        self.scp("/tmp/vm_install.cmd", rmt_install)
        execute("rm /tmp/vm_install.cmd", check=False)

    def start_vm_install(self):
        rmt_install = self.workdir + '/sut_vm_install_%s.cmd'
        cmd = "nohup sh %s > %s/nohup.out 2>&1 &" % (rmt_install, self.workdir)
        output = self.sendcmd(cmd)
        thread = output.split()[-1]

        time.sleep(15)

        cmd = "ps %s" % thread
        try:
            self.sendcmd(cmd)
        except ExecError:
            cmd = "cat %s/nohup.out" % self.workdir
            nohup_out = self.sendcmd(cmd)
            raise Exception("Failed to start VM install due to:\n%s" % nohup_out)

    def gen_sut_vm_boot(self, vm_info):
        vm_name = vm_info["vm_name"]
        cpu_mode = vm_info["cpu_mode"]
        mem = vm_info["mem"]
        core = vm_info["core"]
        product = vm_info["product"]
        version = vm_info["version"]
        disk = vm_info["disk"]
        iso = vm_info["iso"]
        vncport = vm_info.get("vncport")
        if not vncport:
            vncport = 0
        # Generate the uuid for creating the VM
        uuid = execute('uuidgen').strip()
        # Generate the mac address for creating the nic of VM
        cmd = "echo $RANDOM | md5sum | sed 's/\(..\)/&:/g' | cut -c1-11"
        random_mac = execute(cmd).strip()

        vm_boot = '''/usr/libexec/qemu-kvm -name %s -M pc -cpu %s -enable-kvm -m %sG -smp %s,cores=%s \
-uuid %s \
-smbios type=1,manufacturer="Red Hat",product="%s",version=%s,serial=4C4C4544-0056-4210-8032-C3C04F463358,uuid=%s \
-nodefconfig -rtc base=localtime,driftfix=slew \
-drive file=%s,if=none,format=raw,cache=none,werror=stop,rerror=stop,id=drive-virtio-disk0,aio=native \
-device virtio-blk-pci,scsi=off,bus=pci.0,addr=0x5,drive=drive-virtio-disk0,id=virtio-disk0,bootindex=1 \
-drive file=%s,if=none,media=cdrom,id=drive-ide0-1-0,readonly=on,format=raw,serial= \
-device ide-drive,bus=ide.1,unit=0,drive=drive-ide0-1-0,id=ide0-1-0 \
-netdev tap,script=%s/qemu-ifup,id=hostnet0,vhost=on -device virtio-net-pci,netdev=hostnet0,id=net0,mac=52:52:%s,bus=pci.0 -device piix3-usb-uhci,id=usb,bus=pci.0,addr=0x1.0x2 -device usb-tablet,id=tablet0 -device usb-ehci,id=ehci0 \
-vnc :%s -chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s4=1 \
-monitor stdio -name %s \
-boot menu=on  \
'''
        cmd = "echo '%s' > /tmp/vm_boot.cmd" % (vm_boot % (
            vm_name,
            cpu_mode,
            mem,
            core,
            core,
            uuid,
            product,
            version,
            uuid,
            disk,
            iso,
            self.workdir,
            random_mac,
            vncport,
            vm_name))
        execute(cmd)

        rmt_boot = self.workdir + '/sut_vm_boot_%s.cmd' % vm_name
        self.scp("/tmp/vm_boot.cmd", rmt_boot)
        execute("rm /tmp/vm_boot.cmd", check=False)

    def gen_sut_vm_boot_usb(self, vm_info):
        vm_name = vm_info["vm_name"]
        cpu_mode = vm_info["cpu_mode"]
        mem = vm_info["mem"]
        core = vm_info["core"]
        product = vm_info["product"]
        version = vm_info["version"]
        disk = vm_info["disk"]
        usb_disk = vm_info["usb_disk"]
        vncport = vm_info.get("vncport")
        if not vncport:
            vncport = 0
        # Generate the uuid for creating the VM
        uuid = execute('uuidgen').strip()
        # Generate the mac address for creating the nic of VM
        cmd = "echo $RANDOM | md5sum | sed 's/\(..\)/&:/g' | cut -c1-11"
        random_mac = execute(cmd).strip()

        vm_boot = '''/usr/libexec/qemu-kvm -name %s -M pc -cpu %s -enable-kvm -m %sG -smp %s,cores=%s \
-uuid %s \
-smbios type=1,manufacturer="Red Hat",product="%s",version=%s,serial=4C4C4544-0056-4210-8032-C3C04F463358,uuid=%s \
-nodefconfig -rtc base=localtime,driftfix=slew \
-drive file=%s,if=none,format=raw,cache=none,werror=stop,rerror=stop,id=drive-virtio-disk0,aio=native \
-device virtio-blk-pci,scsi=off,bus=pci.0,addr=0x5,drive=drive-virtio-disk0,id=virtio-disk0,bootindex=1 \
-netdev tap,script=%s/qemu-ifup,id=hostnet0,vhost=on -device virtio-net-pci,netdev=hostnet0,id=net0,mac=52:52:%s,bus=pci.0 -device piix3-usb-uhci,id=usb,bus=pci.0,addr=0x1.0x2 -device usb-tablet,id=tablet0 -device usb-ehci,id=ehci0 \
-vnc :%s -chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s4=1 \
-monitor stdio -name %s\
-boot menu=on \
-device usb-ehci,id=ehci1 -drive file=%s,if=none,id=drive-usb-2-0,media=disk,format=raw,cache=none,werror=stop,rerror=stop,aio=threads -device usb-storage,bus=ehci0.0,drive=drive-usb-2-0,id=usb-2-0,removable=on -rtc base=localtime,clock=host,driftfix=slew
'''
        cmd = "echo '%s' > /tmp/vm_boot_usb.cmd" % (vm_boot % (
            vm_name,
            cpu_mode,
            mem,
            core,
            core,
            uuid,
            product,
            version,
            uuid,
            disk,
            self.workdir,
            random_mac,
            vncport,
            vm_name,
            usb_disk))
        execute(cmd)

        rmt_boot = self.workdir + '/sut_vm_usb_%s.cmd' % vm_name
        self.scp("/tmp/vm_boot_usb.cmd", rmt_boot)
        execute("rm /tmp/vm_boot_usb.cmd", check=False)

    def gen_sut_vm_boot_debug_net(self, vm_info):
        vm_name = vm_info["vm_name"]
        cpu_mode = vm_info["cpu_mode"]
        mem = vm_info["mem"]
        core = vm_info["core"]
        product = vm_info["product"]
        version = vm_info["version"]
        disk = vm_info["disk"]
        vncport = vm_info.get("vncport")
        if not vncport:
            vncport = 0
        # Generate the uuid for creating the VM
        uuid = execute('uuidgen').strip()
        # Generate the mac address for creating the nic of VM
        cmd = "echo $RANDOM | md5sum | sed 's/\(..\)/&:/g' | cut -c1-11"
        random_mac = execute(cmd).strip()

        vm_boot = '''/usr/libexec/qemu-kvm -name %s -M pc -cpu %s -enable-kvm -m %sG -smp %s,cores=%s \
-uuid %s \
-smbios type=1,manufacturer="Red Hat",product="%s",version=%s,serial=4C4C4544-0056-4210-8032-C3C04F463358,uuid=%s \
-nodefconfig -rtc base=localtime,driftfix=slew \
-drive file=%s,if=none,format=raw,cache=none,werror=stop,rerror=stop,id=drive-virtio-disk0,aio=native \
-device virtio-blk-pci,scsi=off,bus=pci.0,addr=0x5,drive=drive-virtio-disk0,id=virtio-disk0,bootindex=1 \
-netdev tap,script=%s/qemu-ifup,id=hostnet0,vhost=on -device virtio-net-pci,netdev=hostnet0,id=net0,mac=52:52:%s,bus=pci.0 -device piix3-usb-uhci,id=usb,bus=pci.0,addr=0x1.0x2 -device usb-tablet,id=tablet0 -device usb-ehci,id=ehci0 \
-vnc :%s -chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s4=1 \
-monitor stdio -name %s\
-boot menu=on  \
-netdev tap,id=hostnet1,vhost=on,script=%s/qemu-ifup -device e1000,netdev=hostnet1,addr=0x9,id=net1,mac=00:52:%s
'''
        cmd = "echo '%s' > /tmp/vm_boot_debug_net.cmd" % (vm_boot % (
            vm_name,
            cpu_mode,
            mem,
            core,
            core,
            uuid,
            product,
            version,
            uuid,
            disk,
            self.workdir,
            random_mac,
            vncport,
            vm_name,
            self.workdir,
            random_mac))
        execute(cmd)

        rmt_boot = self.workdir + '/sut_vm_debug_net_%s.cmd' % vm_name
        self.scp("/tmp/vm_boot_debug_net.cmd", rmt_boot)
        execute("rm /tmp/vm_boot_debug_net.cmd", check=False)

    def gen_sut_vm_boot_debug_serial(self, vm_info):
        vm_name = vm_info["vm_name"]
        cpu_mode = vm_info["cpu_mode"]
        mem = vm_info["mem"]
        core = vm_info["core"]
        product = vm_info["product"]
        version = vm_info["version"]
        disk = vm_info["disk"]
        vncport = vm_info.get("vncport")
        if not vncport:
            vncport = 0
        serialport = vm_info.get("serialport")
        sc_hostip = vm_info["sc_hostip"]
        if not serialport:
            serialport = 4555
        # Generate the uuid for creating the VM
        uuid = execute('uuidgen').strip()
        # Generate the mac address for creating the nic of VM
        cmd = "echo $RANDOM | md5sum | sed 's/\(..\)/&:/g' | cut -c1-11"
        random_mac = execute(cmd).strip()

        vm_boot = '''/usr/libexec/qemu-kvm -name %s -M pc -cpu %s -enable-kvm -m %sG -smp %s,cores=%s \
-uuid %s \
-smbios type=1,manufacturer="Red Hat",product="%s",version=%s,serial=4C4C4544-0056-4210-8032-C3C04F463358,uuid=%s \
-nodefconfig -rtc base=localtime,driftfix=slew \
-drive file=%s,if=none,format=raw,cache=none,werror=stop,rerror=stop,id=drive-virtio-disk0,aio=native \
-device virtio-blk-pci,scsi=off,bus=pci.0,addr=0x5,drive=drive-virtio-disk0,id=virtio-disk0,bootindex=1 \
-netdev tap,script=%s/qemu-ifup,id=hostnet0,vhost=on -device virtio-net-pci,netdev=hostnet0,id=net0,mac=52:52:%s,bus=pci.0 -device piix3-usb-uhci,id=usb,bus=pci.0,addr=0x1.0x2 -device usb-tablet,id=tablet0 -device usb-ehci,id=ehci0 \
-vnc :%s -chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s4=1 \
-monitor stdio  -name %s\
-boot menu=on  \
-serial tcp:%s:%s
'''
        cmd = "echo '%s' > /tmp/vm_boot_debug_serial.cmd" % (vm_boot % (
            vm_name,
            cpu_mode,
            mem,
            core,
            core,
            uuid,
            product,
            version,
            uuid,
            disk,
            self.workdir,
            random_mac,
            vncport,
            self.workdir,
            random_mac,
            vm_name,
            sc_hostip,
            serialport))
        execute(cmd)

        rmt_boot = self.workdir + '/sut_vm_debug_serial_%s.cmd' % vm_name
        self.scp("/tmp/vm_boot_debug_serial.cmd", rmt_boot)
        execute("rm /tmp/vm_boot_debug_serial.cmd", check=False)

    def copy_sut_vm_boot_debug_net(self, vm_info):
        vm_name = vm_info["vm_name"]
        cmd = "echo $RANDOM | md5sum | sed 's/\(..\)/&:/g' | cut -c1-11"
        random_mac = execute(cmd).strip()

        # Check the SUT vm install script created
        vm_install_script = self.workdir + '/sut_vm_debug_net_%s' % vm_name
        if not os.path.isfile(vm_install_script):
            raise Exception("No SUT install script found, please install the SUT firstly")
        # Copy the install script and modify it
        vm_debug_net_script = self.workdir + '/sut_vm_debug_net_%s' % vm_name
        shutil.copyfile(vm_install_script, vm_debug_net_script)
        # Modify the new copied vm_boot script
        net_para = "-netdev tap,id=hostnet1,vhost=on,script=%s/qemu-ifup -device e1000," \
                   "netdev=hostnet1,addr=0x9,id=net1,mac=00:52:%s" % (self.workdir, random_mac)

        with open(vm_debug_net_script, 'a') as f:
            f.write(net_para)

    def copy_sut_vm_boot_debug_serial(self, vm_info):
        vm_name = vm_info["vm_name"]
        serialport = vm_info.get("serialport")
        sc_hostip = vm_info["sc_hostip"]
        if not serialport:
            serialport = 4555

        # Check the SUT vm install script created
        vm_install_script = self.workdir + '/sut_vm_debug_serial_%s' % vm_name
        if not os.path.isfile(vm_install_script):
            raise Exception("No SUT install script found, please install the SUT firstly")
        # Copy the install script and modify it
        vm_debug_serial_script = self.workdir + '/sut_vm_debug_serial_%s' % vm_name
        shutil.copyfile(vm_install_script, vm_debug_serial_script)
        # Modify the new copied vm_boot script
        serial_para = " -serial tcp:%s:%s" % (sc_hostip, serialport)
        with open(vm_debug_serial_script, 'a') as f:
            f.write(serial_para)


class Sc(Server):
    def __init__(self, hostname, username, password, workdir='/home/svvp'):
        super(Sc, self).__init__(hostname, username, password)
        self._make_workdir(workdir)
        self.workdir = workdir

    def _make_workdir(self, workdir):
        cmd = "test -d %s" % workdir
        try:
            self.sendcmd(cmd)
        except ExecError:
            cmd = "mkdir -p %s" % workdir
            self.sendcmd(cmd)

    def gen_internal_bridge(self, bridge, nic):
        # Copy the nic configure file to the remote server
        ifcfg_cfg = '''DEVICE=%s
HWADDR=%s
BRIDGE=%s
ONBOOT=yes
NM_CONTROLLED=no
IPV6_AUTOCONF=no
PEERNTP=yes
IPV6INIT=no'''
        cmd_get_mac = "ip link show %s|grep 'link/ether'" % nic
        output = self.sendcmd(cmd_get_mac)
        mac = output.split()[1]

        cmd = "echo '%s' > /tmp/ifcfg_nic.cfg" % (ifcfg_cfg % (
            nic,
            mac,
            bridge))
        execute(cmd)

        rmt_ifcfgnic = self.workdir + '/ifcfg_nic.cfg'
        self.scp("/tmp/ifcfg_nic.cfg", rmt_ifcfgnic)
        self.sendcmd("mv -f %s /etc/sysconfig/network-scripts/ifcfg-%s" % (rmt_ifcfgnic, nic))

        # Copy the bridge configure file to the remote server
        ifcfg_br = '''DEVICE=%s
TYPE=Bridge
DELAY=0
STP=off
ONBOOT=yes
BOOTPROTO=dhcp
DEFROUTE=yes
NM_CONTROLLED=no
IPV6_AUTOCONF=no
PEERNTP=yes
IPV6INIT=no
HOTPLUG=no'''
        cmd = "echo '%s' > /tmp/ifcfg_br.cfg" % (ifcfg_br % (
            bridge))
        execute(cmd)

        rmt_ifcfgbr = self.workdir + '/ifcfg_br.cfg'
        self.scp("/tmp/ifcfg_br.cfg", rmt_ifcfgbr)
        execute("rm /tmp/ifcfg_br.cfg")

        self.sendcmd("mv -f %s /etc/sysconfig/network-scripts/ifcfg-%s" % (rmt_ifcfgbr, bridge))

        # Delete the bridge if exists
        cmd = "ip link show %s" % bridge
        try:
            self.sendcmd(cmd)
        except ExecError:
            pass
        else:
            # Get the device under the existing bridge
            cmd = "ifdown %s" % bridge
            self.sendcmd(cmd, check=False)

            cmd = "brctl delbr %s" % bridge
            self.sendcmd(cmd)

        # Add the bridge and interface
        cmd = "brctl addbr %s " % bridge
        self.sendcmd(cmd)
        cmd = "brctl addif %s %s" % (bridge, nic)
        self.sendcmd(cmd)

        # Add the route to avoid the disconnection from remote server
        # Firstly, get the default gateway
        cmd = "ip route list|grep default|grep -v %s|grep -v %s" % (nic, bridge)
        output = self.sendcmd(cmd)
        s, tmpfile = tempfile.mkstemp()
        with open(tmpfile, 'w') as f:
            f.write(output)
        cmd = "sed -n '/^default/p' %s" % tmpfile
        output = execute(cmd)
        default_gw = output.split()[2]

        # Add a route to avoid the disconnection by "ifup bridge"
        cmd = "ip route list|grep 10.0.0.0/8|grep %s" % default_gw
        try:
            self.sendcmd(cmd)
        except ExecError:
            cmd = "ip route add 10.0.0.0/8 via %s" % default_gw
            self.sendcmd(cmd)

        # ifup the bridge, may create the default gateway
        cmd = "ifup %s" % bridge
        self.sendcmd(cmd, check=False)

        # Delete the 192.168 gateway since no impact for internal comunicatation
        cmd = "ip route list|grep default|grep %s" % bridge
        try:
            self.sendcmd(cmd)
        except ExecError:
            pass
        else:
            cmd = "ip route del default"
            self.sendcmd(cmd)

        # Add the original gateway
        cmd = "ip route list|grep default|grep %s" % default_gw
        try:
            self.sendcmd(cmd)
        except ExecError:
            cmd = "ip route add default via %s" % default_gw
            self.sendcmd(cmd)
        # Delete the new add route if the original gateway were added
        cmd = "ip route list|grep default|grep %s" % default_gw
        try:
            self.sendcmd(cmd)
        except ExecError:
            pass
        else:
            cmd = "ip route del 10.0.0.0/8"
            self.sendcmd(cmd, check=False)

    def gen_internal_qemu_ifup(self, bridge):
        qemu_ifup = '''#!/bin/sh
switch=%s
/sbin/ip link set $1 up
/usr/sbin/brctl addif ${switch} $1'''
        cmd = "echo '%s' > /tmp/qemu_ifup.cmd" % (qemu_ifup % (
            bridge))
        execute(cmd)

        rmt_qemu = self.workdir + '/qemu-ifup'
        self.scp("/tmp/qemu_ifup.cmd", rmt_qemu)
        cmd = "chmod +x %s" % rmt_qemu
        self.sendcmd(cmd)
        execute("rm /tmp/qemu_ifup.cmd")

    def gen_public_bridge(self, bridge, nic):
        # Copy the nic configure file to the remote server
        ifcfg_cfg = '''DEVICE=%s
HWADDR=%s
BRIDGE=%s
ONBOOT=yes
NM_CONTROLLED=no
IPV6_AUTOCONF=no
PEERNTP=yes
IPV6INIT=no'''
        cmd_get_mac = "ip link show %s|grep 'link/ether'" % nic
        output = self.sendcmd(cmd_get_mac)
        mac = output.split()[1]

        cmd = "echo '%s' > /tmp/ifcfg_nic.cfg" % (ifcfg_cfg % (
            nic,
            mac,
            bridge))
        execute(cmd)

        rmt_ifcfgnic = self.workdir + '/ifcfg_nic.cfg'
        self.scp("/tmp/ifcfg_nic.cfg", rmt_ifcfgnic)
        self.sendcmd("mv -f %s /etc/sysconfig/network-scripts/ifcfg-%s" % (rmt_ifcfgnic, nic))

        # Copy the bridge configure file to the remote server
        ifcfg_br = '''DEVICE=%s
TYPE=Bridge
DELAY=0
STP=off
ONBOOT=yes
BOOTPROTO=dhcp
DEFROUTE=yes
NM_CONTROLLED=no
IPV6_AUTOCONF=no
PEERNTP=yes
IPV6INIT=no
HOTPLUG=no'''
        cmd = "echo '%s' > /tmp/ifcfg_br.cfg" % (ifcfg_br % (
            bridge))
        execute(cmd)

        rmt_ifcfgbr = self.workdir + '/ifcfg_br.cfg'
        self.scp("/tmp/ifcfg_br.cfg", rmt_ifcfgbr)
        execute("rm /tmp/ifcfg_br.cfg")

        self.sendcmd("mv -f %s /etc/sysconfig/network-scripts/ifcfg-%s" % (rmt_ifcfgbr, bridge))

        # Delete the bridge if exists
        cmd = "ip link show %s" % bridge
        try:
            self.sendcmd(cmd)
        except ExecError:
            pass
        else:
            # Get the device under the existing bridge
            cmd = "ifdown %s" % bridge
            self.sendcmd(cmd, check=False)

            cmd = "brctl delbr %s" % bridge
            self.sendcmd(cmd)

        # Add the bridge and interface
        cmd = "brctl addbr %s " % bridge
        self.sendcmd(cmd)
        cmd = "brctl addif %s %s" % (bridge, nic)
        self.sendcmd(cmd)

        # ifup the bridge
        cmd = "ifup %s" % bridge
        self.sendcmd(cmd)

    def gen_public_qemu_ifup(self, bridge):
        qemu_ifup = '''#!/bin/sh
switch=%s
/sbin/ip link set $1 up
/usr/sbin/brctl addif ${switch} $1'''
        cmd = "echo '%s' > /tmp/qemu_ifup1.cmd" % (qemu_ifup % (
            bridge))
        execute(cmd)

        rmt_qemu = self.workdir + '/qemu-ifup.pub'
        self.scp("/tmp/qemu_ifup1.cmd", rmt_qemu)
        cmd = "chmod +x %s" % rmt_qemu
        self.sendcmd(cmd)
        execute("rm /tmp/qemu_ifup1.cmd")

    def gen_raw_disk(self, path, size):
        cmd = "qemu-img create -f raw %s %s" % (path, size)
        self.sendcmd(cmd)

    def gen_sc_vm_install(self, vm_info):
        vm_name = vm_info["vm_name"]
        mem = vm_info["mem"]
        core = vm_info["core"]
        iso = vm_info["iso"]
        disk = vm_info["disk"]
        vncport = vm_info.get("vncport")
        if not vncport:
            vncport = 0
        # Generate the mac address for creating the nic of VM
        cmd = "echo $RANDOM | md5sum | sed 's/\(..\)/&:/g' | cut -c1-11"
        random_mac = execute(cmd).strip()
        # Generate the uuid for creating the VM
        uuid = execute('uuidgen').strip()

        sc_vm_install = '''/usr/libexec/qemu-kvm -name %s -m %sG -smp %s -usb -device usb-tablet \
-drive file=%s,format=raw,if=none,id=drive-ide0-0-0,werror=stop,rerror=stop,cache=none \
-device ide-drive,drive=drive-ide0-0-0,id=ide0-0-0,bootindex=1 \
-drive file=%s,if=none,media=cdrom,id=drive-ide0-1-0,readonly=on,format=raw,serial= \
-device ide-drive,bus=ide.1,drive=drive-ide0-1-0,id=ide0-1-0 \
-netdev tap,id=hostnet0,script=%s/qemu-ifup,vhost=on -device e1000,netdev=hostnet0,mac=00:52:%s,bus=pci.0,addr=0x4 -uuid %s \
-rtc base=localtime,clock=host,driftfix=slew  \
-monitor stdio -name %s -vnc :%s \
-chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s3=1 -global PIIX4_PM.disable_s4=1'''

        cmd = "echo '%s' > /tmp/sc_vm_install_%s.cmd" % (sc_vm_install % (
            vm_name,
            mem,
            core,
            disk,
            iso,
            self.workdir,
            random_mac,
            uuid,
            vm_name,
            vncport), vm_name)
        execute(cmd)

        rmt_install = self.workdir + '/sc_vm_install_%s.cmd' % vm_name
        self.scp("/tmp/sc_vm_install_%s.cmd" % vm_name, rmt_install)
        execute("rm /tmp/sc_vm_install_%s.cmd" % vm_name, check=False)

    def start_sc_vm_install(self, vm_name):
        rmt_install = self.workdir + '/sc_vm_install_%s.cmd' % vm_name
        cmd = "nohup sh %s > %s/nohup.out 2>&1 &" % (rmt_install, self.workdir)
        output = self.sendcmd(cmd)
        thread = output.split()[-1]

        time.sleep(15)

        cmd = "ps %s" % thread
        try:
            self.sendcmd(cmd)
        except ExecError:
            cmd = "cat %s/nohup.out" % self.workdir
            nohup_out = self.sendcmd(cmd)
            raise Exception("Failed to start SC VM %s install due to:\n%s" % (vm_name, nohup_out))

    def gen_sc_vm_boot(self, vm_info):
        vm_name = vm_info["vm_name"]
        mem = vm_info["mem"]
        core = vm_info["core"]
        disk = vm_info["disk"]
        vncport = vm_info.get("vncport")
        if not vncport:
            vncport = 0
        # Generate the mac address for creating the nic of VM
        cmd = "echo $RANDOM | md5sum | sed 's/\(..\)/&:/g' | cut -c1-11"
        random_mac = execute(cmd).strip()
        # Generate the uuid for creating the VM
        uuid = execute('uuidgen').strip()

        sc_vm_boot = '''/usr/libexec/qemu-kvm -name %s -m %sG -smp % -usb -device usb-tablet \
-drive file=%s,format=raw,if=none,id=drive-ide0-0-0,werror=stop,rerror=stop,cache=none \
-device ide-drive,drive=drive-ide0-0-0,id=ide0-0-0,bootindex=1 \
-netdev tap,id=hostnet0,script=%s/qemu-ifup,vhost=on -device e1000,netdev=hostnet0,mac=00:52:%s,bus=pci.0,addr=0x4 -uuid %s \
-rtc base=localtime,clock=host,driftfix=slew  \
-monitor stdio -name %s -vnc :%s \
-chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s3=1 -global PIIX4_PM.disable_s4=1'''

        cmd = "echo '%s' > /tmp/sc_vm_boot_%s.cmd" % (sc_vm_boot % (
            vm_name,
            mem,
            core,
            disk,
            self.workdir,
            random_mac,
            uuid,
            vm_name,
            vncport), vm_name)
        execute(cmd)

        rmt_boot = self.workdir + '/sc_vm_boot_%s.cmd' % vm_name
        self.scp("/tmp/sc_vm_boot_%s.cmd" % vm_name, rmt_boot)
        execute("rm /tmp/sc_vm_boot_%s.cmd" % vm_name, check=False)

    def gen_sc_vm_boot_debug_serial(self, vm_info):
        vm_name = vm_info["vm_name"]
        mem = vm_info["mem"]
        core = vm_info["core"]
        disk = vm_info["disk"]
        vncport = vm_info.get("vncport")
        if not vncport:
            vncport = 0
        serialport = vm_info.get("serialport")
        if not serialport:
            serialport = 4555

        # Generate the mac address for creating the nic of VM
        cmd = "echo $RANDOM | md5sum | sed 's/\(..\)/&:/g' | cut -c1-11"
        random_mac = execute(cmd).strip()
        # Generate the uuid for creating the VM
        uuid = execute('uuidgen').strip()

        sc_vm_boot_debug_serial = '''/usr/libexec/qemu-kvm -name %s -m %sG -smp % -usb -device usb-tablet \
-drive file=%s,format=raw,if=none,id=drive-ide0-0-0,werror=stop,rerror=stop,cache=none \
-device ide-drive,drive=drive-ide0-0-0,id=ide0-0-0,bootindex=1 \
-netdev tap,id=hostnet0,script=%s/qemu-ifup,vhost=on -device e1000,netdev=hostnet0,mac=00:52:%s,bus=pci.0,addr=0x4 -uuid %s \
-rtc base=localtime,clock=host,driftfix=slew  \
-monitor stdio -name %s -vnc :%s \
-chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s3=1 -global PIIX4_PM.disable_s4=1 \
-netdev tap,id=hostnet1,script=%s/qemu-ifup.pub,vhost=on -device e1000,netdev=hostnet1,addr=0x9,id=net1,mac=52:52:%s
-serial tcp:0:%s,server,nowait'''
        cmd = "echo '%s' > /tmp/sc_vm_boot_debug_serial_%s.cmd" % (sc_vm_boot_debug_serial % (
            vm_name,
            mem,
            core,
            disk,
            self.workdir,
            random_mac,
            uuid,
            vm_name,
            vncport,
            self.workdir,
            random_mac,
            serialport), vm_name)
        execute(cmd)

        rmt_boot = self.workdir + '/sc_vm_boot_debug_serial_%s.cmd' % vm_name
        self.scp("/tmp/sc_vm_boot_debug_serial_%s.cmd" % vm_name, rmt_boot)
        execute("rm /tmp/sc_vm_boot_serial_%s.cmd" % vm_name, check=False)

    def copy_sc_vm_boot_debug_serial(self, vm_info):
        vm_name = vm_info["vm_name"]
        pub_bridge = vm_info["pub_bridge"]
        serialport = vm_info.get("serialport")
        if not serialport:
            serialport = 4555
        cmd = "echo $RANDOM | md5sum | sed 's/\(..\)/&:/g' | cut -c1-11"
        random_mac = execute(cmd).strip()

        # Check the SC vm install script created
        vm_install_script = self.workdir + '/sc_vm_debug_serial_%s' % vm_name
        if not os.path.isfile(vm_install_script):
            raise Exception("No SC install script found, please install the SUT firstly")
        # Copy the install script and modify it
        vm_debug_serial_script = self.workdir + '/sc_vm_debug_serial_%s' % vm_name
        shutil.copyfile(vm_install_script, vm_debug_serial_script)
        # Generate the qemu-ifup.pub script
        self.gen_public_qemu_ifup(pub_bridge)
        # Modify the new copied vm_boot script
        serial_para = ''''-netdev tap,id=hostnet1,script=%s/qemu-ifup.pub,vhost=on -device e1000,netdev=hostnet1,addr=0x9,id=net1,mac=00:52:%s
-serial tcp:0:%s,server,nowait''' % (self.workdir, random_mac, serialport)
        with open(vm_debug_serial_script, 'a') as f:
            f.write(serial_para)


class Config:
    def __init__(self, path):
        self.path = path
        self.cf = ConfigParser.ConfigParser()
        self.cf.read(self.path)

    def get(self, field, key):
        result = ""
        try:
            result = self.cf.get(field, key)
        except:
            result = ""
        return result

    def set(self, field, key, value):
        try:
            self.cf.set(field, key, value)
            self.cf.write(open(self.path, 'w'))
        except:
            return False
        return True


def read_config(config_file_path, field, key):
    cf = ConfigParser.ConfigParser()
    try:
        cf.read(config_file_path)
        result = cf.get(field, key)
    except:
        sys.exit(1)
    return result


def write_config(config_file_path, field, key, value):
    cf = ConfigParser.ConfigParser()
    try:
        cf.read(config_file_path)
        cf.set(field, key, value)
        cf.write(open(config_file_path, 'w'))
    except:
        sys.exit(1)
    return True


def execute(cmd, check=True):
    try:
        out = subprocess.check_output(cmd, shell=True)
    except subprocess.CalledProcessError as e:
        if check:
            raise ExecError(e.output)
        else:
            return e.output
    else:
        return out


def remote_view(ipport):
    cmd = "remote-viewer vnc://%s &" % ipport
    subprocess.Popen(cmd, shell=True)
    # execute(cmd)


def info_print(string):
    print "INFO: %s" % string


def warn_print(string):
    print "WARN: %s" % string


def error_print(string):
    print "EROR: %s" % string
