#!/usr/bin/python

import pxssh
import sys
import ConfigParser
import subprocess


class ExecError(Exception):
    pass


class Server(object):
    def __init__(self, hostname, username, passwd):
        self.hostname = hostname
        self.username = username
        self.passwd = passwd

    def sendcmd(self, cmd, check=True, timeout=-1):
        s = pxssh.pxssh()
        s.login(self.hostname, self.username, self.passwd)
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
                raise ExecError("[%s]: Execute [%s]:\n%s" % (self.hostname, cmd, out))
            else:
                return out
        return out

    def scp(self, local, rmt):
        # Check whether the sshd is enabled on the remote server
        try:
            self.sendcmd('hostname', check=False)
        except Exception:
            raise ExecError("Reason: password or sshd on remote server")

        scp_put = '''
        set timeout 600
        spawn scp %s %s@%s:%s
        expect "(yes/no)?" {
        send "yes\r"
        expect "password:"
        send "%s\r"
        } "password:" {send "%s\r"}
        expect eof
        exit'''

        cmd = "echo '%s' > /tmp/scp_put.cmd" % (scp_put % (
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

    def gen_bridge(self, bridge, nic):
        # Copy the nic configure file to the remote server
        ifcfg_cfg = '''
        DEVICE=%s
        HWADDR=%s
        BRIDGE=%s
        ONBOOT=yes
        NM_CONTROLLED=no
        IPV6_AUTOCONF=no
        PEERNTP=yes
        IPV6INIT=no
        '''
        cmd_get_mac = "ifconfig -a |grep '^%s'" % nic
        output = self.sendcmd(cmd_get_mac)
        mac = output.split()[-1]

        cmd = "echo '%s' > /tmp/ifcfg_nic.cfg" % (ifcfg_cfg % (
            nic,
            mac,
            bridge))
        execute(cmd)

        self.scp("/tmp/ifcfg_nic.cfg", "/data/ifcfg_nic.cfg")
        self.sendcmd("mv /data/ifcfg_nic.cmd /etc/sysconfig/network-script/ifcfg_%s" % nic)

        # Copy the bridge configure file to the remote server
        ifcfg_br = '''
        DEVICE=%s
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
        HOTPLUG=no
        '''
        cmd = "echo '%s' > /tmp/ifcfg_br.cfg" % (ifcfg_br % (
            nic,
            mac,
            bridge))
        execute(cmd)

        self.scp("/tmp/ifcfg_br.cfg", "/data/ifcfg_br.cfg")
        execute("rm /tmp/ifcfg_br.cfg")

        self.sendcmd("mv /data/ifcfg_nic.cfg /etc/sysconfig/network-script/ifcfg_%s" % bridge)

        cmd = "brctl addif %s %s" % (bridge, nic)
        self.sendcmd(cmd)

        # Add the route to avoid the disconnection from remote server
        # cmd = "route add "
        #????????????
        pass

        cmd = "ifup %s" % bridge
        self.sendcmd(cmd, check=False)
        self.sendcmd("ifconfig %s" % bridge)

    def gen_qemu_ifup(self, bridge):
        qemu_ifup = '''
        #!/bin/sh
        switch=%s
        /sbin/ifconfig $1 0.0.0.0 up
        /usr/sbin/brctl addif ${switch} $1
        '''
        cmd = "echo '%s' > /tmp/qemu_ifup.cmd" % (qemu_ifup % (
            bridge))
        execute(cmd)
        self.scp("/tmp/qemu_ifup.cmd", "/data/qemu_ifup")
        execute("rm /tmp/qemu_ifup.cmd")

    def gen_raw_disk(self, path):
        cmd = "qemu-img create -f raw %s 120G" % path
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
        virtio = vm_info["virtio"]

        vm_install = '''
        /usr/libexec/qemu-kvm -name %s -M pc -cpu %s -enable-kvm -m %sG -smp %s,cores=%s \
        -uuid e48f4f59-7efa-45c6-b2be-ead3605ed62b \
        -smbios type=1,manufacturer='Red Hat',product=%s,version=%s,serial=4C4C4544-0056-4210-8032-C3C04F463358,uuid=ddbe6671-7ba7-4e7a-a62e-241a82ff600b \
        -nodefconfig -rtc base=localtime,driftfix=slew -drive file=%s,if=none,media=cdrom,id=drive-ide0-1-0,readonly=on,format=raw,serial= \
        -device ide-drive,bus=ide.1,unit=0,drive=drive-ide0-1-0,id=ide0-1-0 -drive file=%s,if=none,format=raw,cache=none,werror=stop,rerror=stop,id=drive-virtio-disk0,aio=native \
        -device virtio-blk-pci,scsi=off,bus=pci.0,addr=0x5,drive=drive-virtio-disk0,id=virtio-disk0,bootindex=1 \
        -netdev tap,script=/data/qemu-ifup,id=hostnet0,vhost=on -device virtio-net-pci,netdev=hostnet0,id=net0,mac=52:52:00:46:fe:70,bus=pci.0 -device piix3-usb-uhci,id=usb,bus=pci.0,addr=0x1.0x2 -device usb-tablet,id=tablet0 -device usb-ehci,id=ehci0 \
        -vnc :0 -chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s4=1 \
        -fda %s \
        -monitor stdio \
        -boot menu=on
        '''
        cmd = "echo '%s' > /tmp/vm_install.cmd" % (vm_install % (
            vm_name,
            cpu_mode,
            mem,
            core,
            core,
            product,
            version,
            iso,
            disk,
            virtio))
        execute(cmd)

        self.scp("/tmp/vm_install.cmd", "/data/vm_install.cmd")
        execute("rm /tmp/vm_install.cmd", check=False)

    def gen_sut_vm_boot(self, vm_info):
        vm_name = vm_info["vm_name"]
        cpu_mode = vm_info["cpu_mode"]
        mem = vm_info["mem"]
        core = vm_info["core"]
        product = vm_info["product"]
        version = vm_info["version"]
        disk = vm_info["disk"]

        vm_boot = '''
        /usr/libexec/qemu-kvm -name %s -M pc -cpu %s -enable-kvm -m %sG -smp %s,cores=%s \
        -uuid e48f4f59-7efa-45c6-b2be-ead3605ed62b \
        -smbios type=1,manufacturer='Red Hat',product=%s,version=%s,serial=4C4C4544-0056-4210-8032-C3C04F463358,uuid=ddbe6671-7ba7-4e7a-a62e-241a82ff600b \
        -nodefconfig -rtc base=localtime,driftfix=slew \
        -drive file=%s,if=none,format=raw,cache=none,werror=stop,rerror=stop,id=drive-virtio-disk0,aio=native \
        -device virtio-blk-pci,scsi=off,bus=pci.0,addr=0x5,drive=drive-virtio-disk0,id=virtio-disk0,bootindex=1 \
        -netdev tap,script=/data/qemu-ifup,id=hostnet0,vhost=on -device virtio-net-pci,netdev=hostnet0,id=net0,mac=52:52:00:46:fe:70,bus=pci.0 -device piix3-usb-uhci,id=usb,bus=pci.0,addr=0x1.0x2 -device usb-tablet,id=tablet0 -device usb-ehci,id=ehci0 \
        -vnc :0 -chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s4=1 \
        -monitor stdio \
        -boot menu=on
        '''
        cmd = "echo '%s' > /tmp/vm_boot.cmd" % (vm_boot % (
            vm_name,
            cpu_mode,
            mem,
            core,
            core,
            product,
            version,
            disk))
        execute(cmd)

        self.scp("/tmp/vm_boot.cmd", "/data/vm_boot.cmd")
        execute("rm /tmp/vm_boot.cmd", check=False)


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


def gen_bridge(hostname, user, passwd, bridge, nic):
    server = Server(hostname, user, passwd)

    # Copy the nic configure file to the remote server
    ifcfg_cfg = '''
    DEVICE=%s
    HWADDR=%s
    BRIDGE=%s
    ONBOOT=yes
    NM_CONTROLLED=no
    IPV6_AUTOCONF=no
    PEERNTP=yes
    IPV6INIT=no
    '''
    cmd_get_mac = "ifconfig -a |grep '^%s'" % nic
    output = server.sendcmd(cmd_get_mac)
    mac = output.split()[-1]

    cmd = "echo '%s' > /tmp/ifcfg_nic.cfg" % (ifcfg_cfg % (
        nic,
        mac,
        bridge))
    execute(cmd)

    server.scp("/tmp/ifcfg_nic.cfg", "/data/ifcfg_nic.cfg")
    server.sendcmd("mv /data/ifcfg_nic.cmd /etc/sysconfig/network-script/ifcfg_%s" % nic)

    # Copy the bridge configure file to the remote server
    ifcfg_br = '''
    DEVICE=%s
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
    HOTPLUG=no
    '''
    cmd = "echo '%s' > /tmp/ifcfg_br.cfg" % (ifcfg_br % (
        nic,
        mac,
        bridge))
    execute(cmd)

    server.scp("/tmp/ifcfg_br.cfg", "/data/ifcfg_br.cfg")
    execute("rm /tmp/ifcfg_br.cfg")

    server.sendcmd("mv /data/ifcfg_nic.cfg /etc/sysconfig/network-script/ifcfg_%s" % bridge)

    cmd = "brctl addif %s %s" % (bridge, nic)
    server.sendcmd(cmd)
    cmd = "ifup %s" % bridge
    server.sendcmd(cmd, check=False)
    server.sendcmd("ifconfig %s" % bridge)


def gen_sut_vm_install(hostname, user, passwd, vm_name, cpu_mode, mem, core, product, version, iso, network_script, vritio):
    server = Server(hostname, user, passwd)
    vm_install = '''
    /usr/libexec/qemu-kvm -name %s -M pc -cpu %s -enable-kvm -m %s -smp %s,cores=2 \
    -uuid e48f4f59-7efa-45c6-b2be-ead3605ed62b \
    -smbios type=1,manufacturer='Red Hat',product=%S,version=%S,serial=4C4C4544-0056-4210-8032-C3C04F463358,uuid=ddbe6671-7ba7-4e7a-a62e-241a82ff600b \
    -nodefconfig -rtc base=localtime,driftfix=slew -drive file=%s,if=none,media=cdrom,id=drive-ide0-1-0,readonly=on,format=raw,serial= \
    -device ide-drive,bus=ide.1,unit=0,drive=drive-ide0-1-0,id=ide0-1-0 -drive file=win2012r2.raw,if=none,format=raw,cache=none,werror=stop,rerror=stop,id=drive-virtio-disk0,aio=native \
    -device virtio-blk-pci,scsi=off,bus=pci.0,addr=0x5,drive=drive-virtio-disk0,id=virtio-disk0,bootindex=1 \
    -netdev tap,script=/data/qemu-ifup,id=hostnet0,vhost=on -device virtio-net-pci,netdev=hostnet0,id=net0,mac=52:52:00:46:fe:70,bus=pci.0 -device piix3-usb-uhci,id=usb,bus=pci.0,addr=0x1.0x2 -device usb-tablet,id=tablet0 -device usb-ehci,id=ehci0 \
    -vnc :0 -chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s4=1 \
    -fda virtio-win-1.7.5_amd64.vfd \
    -monitor stdio \
    -boot menu=on
    '''
    cmd = "echo '%s' > /tmp/vm_install.cmd" % (vm_install % (
        vm_name,
        cpu_mode,
        mem,
        core,
        core,
        product,
        version,
        iso,
        network_script,
        vritio))
    execute(cmd)

    server.scp("/tmp/vm_install.cmd", "/data/vm_install.cmd")
    execute("rm /tmp/vm_install.cmd", check=False)


def info_print(string):
    print "INFO: %s" % string


def warn_print(string):
    print "WARN: %s" % string


def error_print(string):
    print "EROR: %s" % string
