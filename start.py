#!/usr/bin/python

import time
import sys
import os
import ConfigParser


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


def _check_config(conf, type):
    cfg = Config(conf)
    cfg_eles = []
    if type == 'sut':
        # Get the SUT info
        sut_hostname = cfg.get('SUT', 'HOSTNAME')
        cfg_eles.append(sut_hostname)
        sut_user = cfg.get('SUT', 'USER')
        cfg_eles.append(sut_user)
        sut_password = cfg.get('SUT', 'PASSWORD')
        cfg_eles.append(sut_password)

        # Get the network info for configuring the SUT VM
        sut_bridge = cfg.get('SUT_VM', 'BRIDGE')
        cfg_eles.append(sut_bridge)
        sut_nic = cfg.get('SUT_VM', 'NIC')
        cfg_eles.append(sut_nic)

        # Get the VM info
        sut_vm = cfg.get('VM', 'NAME')
        cfg_eles.append(sut_vm)
        sut_vm_cpu_count = cfg.get('VM', 'CPU_COUNT')
        cfg_eles.append(sut_vm_cpu_count)
        sut_vm_cpu_mode = cfg.get('VM', 'CPU_MODE')
        cfg_eles.append(sut_vm_cpu_mode)
        sut_vm_mem = cfg.get('VM', 'MEM')
        cfg_eles.append(sut_vm_mem)

        # Get the rhvh product and version
        rhvh = cfg.get("RHVH", 'PRODUCT')
        cfg_eles.append(rhvh)
        rhvh_ver = cfg.get("RHVH", "VERSION")
        cfg_eles.append(rhvh_ver)

        # Get the ISO directory
        win_iso = cfg.get('SUT_VM', 'ISO')
        cfg_eles.append(win_iso)

        # Get the virtio file
        vm_virtio = cfg.get('SUT_VM', 'VIRTIO')
        cfg_eles.append(vm_virtio)
    else:
        # Get the SC info
        sc_hostname = cfg.get('SC', 'HOSTNAME')
        cfg_eles.append(sc_hostname)
        sc_user = cfg.get('SC', 'USER')
        cfg_eles.append(sc_user)
        sc_password = cfg.get('SC', 'PASSWORD')
        cfg_eles.append(sc_password)

        # Get the network info for configuring the SC VM
        sc_nic = cfg.get('SC', 'NIC')
        cfg_eles.append(sc_nic)

        # Get the VM info
        sc_vm1 = cfg.get('SC_VM_1', 'NAME')
        cfg_eles.append(sc_vm1)
        sc_vm1_cpu_count = cfg.get('SC_VM_1', 'CORE')
        cfg_eles.append(sc_vm1_cpu_count)
        sc_vm1_mem = cfg.get('SC_VM_1', 'MEM')
        cfg_eles.append(sc_vm1_mem)
        sc_vm2 = cfg.get('SC_VM_2', 'NAME')
        cfg_eles.append(sc_vm2)
        sc_vm2_cpu_count = cfg.get('SC_VM_2', 'CORE')
        cfg_eles.append(sc_vm2_cpu_count)
        sc_vm2_mem = cfg.get('SC_VM_2', 'MEM')
        cfg_eles.append(sc_vm2_mem)

    for ele in cfg_eles:
        if not ele:
            raise Exception("Required configuration variable is not set")


def _help(arg):
    print "Usage: start [type]"
    print "       [type]: sut or sc"
    print "Please correct the argument %s as [sut] or [sc]" % arg
    print "Example: 'start sut' or 'start sc'"


if __name__ == "__main__":
    # No arguments after this script
    if not sys.argv[1]:
        print "Start to setup SUT!"
        # Check all the configuration for sut_setup were filled in the svvp.ini
        try:
            _check_config('./svvp.ini', 'sut')
        except Exception:
            print "SUT required configuration variable is not set"
            sys.exit(1)

        os.system("python ./sut_setup.py")

        time.sleep(5)

        try:
            _check_config('./svvp.ini', 'sc')
        except Exception:
            print "SC required configuration variable is not set"
            sys.exit(1)

        print "Start to setup SC/MC"
        os.system("python ./sc_setup.py")
    else:
        # Arguments were appended
        correct_args = ['sut', 'sc']
        if sys.argv[1] not in correct_args:
            _help(sys.argv[1])
            sys.exit(1)

        # Setup sut
        if sys.argv[1] == 'sut':
            print "Start to setup SUT!"
            # Check all the configuration for sut_setup were filled in the svvp.ini
            try:
                _check_config('./svvp.ini', 'sut')
            except Exception:
                print "SUT required configuration variable is not set"
                sys.exit(1)

            os.system("python ./sut_setup.py")
        else:
            try:
                _check_config('./svvp.ini', 'sc')
            except Exception:
                print "SC required configuration variable is not set"
                sys.exit(1)

            print "Start to setup SC/MC"
            os.system("python ./sc_setup.py")
