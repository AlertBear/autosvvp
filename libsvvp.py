#!/usr/bin/python

import pxssh
import sys
import ConfigParser
import subprocess
import time


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
                raise ExecError("[%s]-[%s] failed:\n%s" % (self.hostname, cmd, out))
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


class Sut(Server):
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
IPV6INIT=no'''
        cmd_get_mac = "ifconfig -a |grep '^%s'" % nic
        output = self.sendcmd(cmd_get_mac)
        mac = output.split()[-1]

        cmd = "echo '%s' > /tmp/ifcfg_nic.cfg" % (ifcfg_cfg % (
            nic,
            mac,
            bridge))
        execute(cmd)

        rmt_ifcfgnic = '/data' + '/ifcfg_nic.cfg'
        self.scp("/tmp/ifcfg_nic.cfg", rmt_ifcfgnic)
        self.sendcmd("mv -f %s /etc/sysconfig/network-scripts/ifcfg-%s" % (rmt_ifcfgnic, nic))

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
HOTPLUG=no'''
        cmd = "echo '%s' > /tmp/ifcfg_br.cfg" % (ifcfg_br % (
            bridge))
        execute(cmd)

        rmt_ifcfgbr = '/data' + '/ifcfg_br.cfg'
        self.scp("/tmp/ifcfg_br.cfg", rmt_ifcfgbr)
        execute("rm /tmp/ifcfg_br.cfg")

        self.sendcmd("mv -f %s /etc/sysconfig/network-scripts/ifcfg-%s" % (rmt_ifcfgbr, bridge))

        # Delete the bridge if exists
        cmd = "ifconfig %s" % bridge
        try:
            self.sendcmd(cmd)
        except ExecError:
            pass
        else:
            # Get the device under the existing bridge
            cmd = "brctl show"
            cmd = "brctl delif %s %s" % bridge
            cmd = "brctl delbr %s" % bridge
            #????????????
            pass

        # Add the bridge and interface
        cmd = "brctl addbr %s " % bridge
        self.sendcmd(cmd)
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
        qemu_ifup = '''#!/bin/sh
switch=%s
/sbin/ifconfig $1 0.0.0.0 up
/usr/sbin/brctl addif ${switch} $1'''
        cmd = "echo '%s' > /tmp/qemu_ifup.cmd" % (qemu_ifup % (
            bridge))
        execute(cmd)

        rmt_qemu = '/data' + '/qemu-ifup'
        self.scp("/tmp/qemu_ifup.cmd", rmt_qemu)
        execute("rm /tmp/qemu_ifup.cmd")

    def gen_raw_disk(self, path):
        cmd = "qemu-img create -f raw %s 320G" % path
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

        # Generate the uuid for creating the VM
        uuid = execute('uuidgen').strip()
        # Generate the mac address for creating the nic of VM
        cmd = "echo $RANDOM | md5sum | sed 's/\(..\)/&:/g' | cut -c1-11"
        random_mac = execute(cmd).strip()

        vm_install = '''/usr/libexec/qemu-kvm -name %s -M pc -cpu %s -enable-kvm -m %sG -smp %s,cores=%s \
-uuid %s \
-smbios type=1,manufacturer="Red Hat",product="%s",version=%s,serial=4C4C4544-0056-4210-8032-C3C04F463358,uuid=%s \
-nodefconfig -rtc base=localtime,driftfix=slew -drive file=%s,if=none,media=cdrom,id=drive-ide0-1-0,readonly=on,format=raw,serial= \
-device ide-drive,bus=ide.1,unit=0,drive=drive-ide0-1-0,id=ide0-1-0 -drive file=%s,if=none,format=raw,cache=none,werror=stop,rerror=stop,id=drive-virtio-disk0,aio=native \
-device virtio-blk-pci,scsi=off,bus=pci.0,addr=0x5,drive=drive-virtio-disk0,id=virtio-disk0,bootindex=1 \
-netdev tap,script=/data/qemu-ifup,id=hostnet0,vhost=on -device virtio-net-pci,netdev=hostnet0,id=net0,mac=52:52:%s,bus=pci.0 -device piix3-usb-uhci,id=usb,bus=pci.0,addr=0x1.0x2 -device usb-tablet,id=tablet0 -device usb-ehci,id=ehci0 \
-vnc :0 -chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s4=1 \
-fda %s \
-monitor stdio \
-boot menu=on'''
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
            random_mac,
            virtio))
        execute(cmd)

        rmt_install = '/data' + '/vm_install.cmd'
        self.scp("/tmp/vm_install.cmd", rmt_install)
        execute("rm /tmp/vm_install.cmd", check=False)

    def gen_sut_vm_boot(self, vm_info):
        vm_name = vm_info["vm_name"]
        cpu_mode = vm_info["cpu_mode"]
        mem = vm_info["mem"]
        core = vm_info["core"]
        product = vm_info["product"]
        version = vm_info["version"]
        disk = vm_info["disk"]

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
-netdev tap,script=/data/qemu-ifup,id=hostnet0,vhost=on -device virtio-net-pci,netdev=hostnet0,id=net0,mac=52:52:%s,bus=pci.0 -device piix3-usb-uhci,id=usb,bus=pci.0,addr=0x1.0x2 -device usb-tablet,id=tablet0 -device usb-ehci,id=ehci0 \
-vnc :0 -chardev socket,path=/tmp/tt-1-1,server,nowait,id=tt-1-1 -mon mode=readline,chardev=tt-1-1 -global PIIX4_PM.disable_s4=1 \
-monitor stdio \
-boot menu=on  \
-device usb-ehci,id=ehci1 -drive file=usb-storage-intel-max.raw,if=none,id=drive-usb-2-0,media=disk,format=raw,cache=none,werror=stop,rerror=stop,aio=threads -device usb-storage,bus=ehci0.0,drive=drive-usb-2-0,id=usb-2-0,removable=on -rtc base=localtime,clock=host,driftfix=slew -chardev socket,id=111a,path=/tmp/monitor-win2012R2-amd-max,server,nowait -mon chardev=111a,mode=readline
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
            random_mac))
        execute(cmd)

        rmt_boot = '/data' + '/vm_boot.cmd'
        self.scp("/tmp/vm_boot.cmd", rmt_boot)
        execute("rm /tmp/vm_boot.cmd", check=False)

    def start_vm_install(self):
        rmt_install = '/data' + '/vm_install.cmd'
        cmd = "nohup sh %s &" % rmt_install
        output = self.sendcmd(cmd)
        thread = output.split()[-1]

        time.sleep(15)

        cmd = "ps %s" % thread
        try:
            self.sendcmd(cmd)
        except ExecError:
            cmd = "cat ~/nohup.out"
            nohup_out = self.sendcmd(cmd)
            raise Exception("Failed to start VM install due to:\n%s" % nohup_out)


class SC(Server):
    pass


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
    execute(cmd)


def info_print(string):
    print "INFO: %s" % string


def warn_print(string):
    print "WARN: %s" % string


def error_print(string):
    print "EROR: %s" % string
