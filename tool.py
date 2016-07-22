#!/usr/bin/python

import argparse
import traceback
import sys
from libsvvp import Sut, Sc, Config


if __name__ == "__main__":
    cfg_file = "./svvp.ini"
    cfg = Config(cfg_file)

    # Get the rhvh product and version
    rhvh = cfg.get("RHVH", 'PRODUCT')
    rhvh_ver = cfg.get("RHVH", "VERSION")
    # Get the SUT info
    sut_hostname = cfg.get('SUT', 'HOSTNAME')
    sut_user = cfg.get('SUT', 'USER')
    sut_password = cfg.get('SUT', 'PASSWORD')
    sut_nic = cfg.get('SUT', 'NIC')
    sut_bridge = sut_nic + 'br0'
    sut_vm = cfg.get('SUT_VM', 'NAME')
    sut_vm_cpu_count = cfg.get('SUT_VM', 'CPU_COUNT')
    sut_vm_cpu_mode = cfg.get('SUT_VM', 'CPU_MODE')
    sut_vm_mem = cfg.get('SUT_VM', 'MEM')
    sut_vm_vncport = cfg.get('SUT_VM', 'VNC')
    win_iso = cfg.get('REQUIRE', 'ISO')
    vm_virtio = cfg.get('REQUIRE', 'VIRTIO')
    sut_workdir = cfg.get('SUT', 'WORKDIR')
    win_iso_name = win_iso.split('/')[-1]
    sut_iso_path = sut_workdir + '/' + win_iso_name

    # Get the SC info
    sc_hostname = cfg.get('SC', 'HOSTNAME')
    sc_user = cfg.get('SC', 'USER')
    sc_password = cfg.get('SC', 'PASSWORD')
    sc_nic = cfg.get('SC', 'NIC')
    sc_bridge = sc_nic + 'br0'
    sc_pub_nic = cfg.get('SC', 'PUB_NIC')
    sc_pub_bridge = sc_pub_nic + 'br0'
    sc_vm1 = cfg.get('SC_VM_1', 'NAME')
    sc_vm1_cpu_count = cfg.get('SC_VM_1', 'CORE')
    sc_vm1_mem = cfg.get('SC_VM_1', 'MEM')
    sc_vm1_vnc = cfg.get('SC_VM_1', 'VNC')
    sc_vm2 = cfg.get('SC_VM_2', 'NAME')
    sc_vm2_cpu_count = cfg.get('SC_VM_2', 'CORE')
    sc_vm2_mem = cfg.get('SC_VM_2', 'MEM')
    sc_vm2_vnc = cfg.get('SC_VM_2', 'VNC')
    sc_workdir = cfg.get('SC', 'WORKDIR')
    sc_iso_path = sc_workdir + '/' + win_iso_name

    # Build the parser
    parser = argparse.ArgumentParser(description="Tool for svvp tests")

    # Add the interactive mode
    parser.add_argument('-i',
                        action="store",
                        choices=["sut", "sc"],
                        dest="int_host",
                        help="Interactive mode with the host")
    # Add to check the route info
    parser.add_argument('-r',
                        action="store",
                        choices=["sut", "sc"],
                        dest="route_host",
                        help="Route info of the sut or sc")
    # Add to review the configuration value in the svvp.ini
    parser.add_argument('-c',
                        action="store_true",
                        dest="configuration",
                        default=False,
                        help="Review the configuration value of the svvp.ini")
    # Add to set the boot_debug job test env for the sut and sc
    parser.add_argument('-d',
                        action="store",
                        choices=["serial", "net"],
                        dest="debug_job",
                        help="Setup the env of boot_debug job")
    # Add to create the boot_usb file for the sut or sc
    pass

    args = parser.parse_args()

    # Interactive mode with the sut or sc
    pass

    # Check the route info
    pass

    # Review the configuration
    pass

    # Do cleanup like delete the bridge, delete the install file etc.
    pass

    # Boot the SUT with USB disk
    pass

    # Boot the SUT with serial to test debug job
    if args.debug_job:
        sc = Sc(sc_hostname, sc_password, sc_workdir)
        sut = Sut(sut_hostname, sut_user, sut_password, sut_workdir)

        if args.debug_job == "serial":
            sc_vm1_info = {
                "vm_name": sc_vm1,
                "pub_bridge": sc_pub_bridge,
            }
            print "START to SETUP debug_serial job TEST ENV..."

            # Setup the public bridge on SC
            print "Creating the public bridge over the public nic..."
            try:
                sc.gen_public_bridge(sc_pub_bridge, sc_pub_nic)
            except Exception as e:
                print "ERROR: %s" % e
            # Create the debug_serial command script on SC
            print "Creating the debug_serial command script on SC..."
            try:
                sc.copy_sc_vm_boot_debug_serial(sc_vm1_info)
            except Exception as e:
                print "ERROR: %s" % e
                sys.exit(1)

            # Get the internal ip address of SC host
            cmd = "ip a s %s|grep 'inet '|" % sc_bridge
            try:
                output = sc.sendcmd(cmd)
            except Exception:
                print "ERROR: NO internal bridge was created, please create before setting up debug_serial env"
                sys.exit(1)
            else:
                sc_hostip = output.split()[1].split('/')[0]

            sut_vm_info = {
                "vm_name": sut_vm,
                "sc_hostip": sc_hostip
            }
            # Create the sut debug_serial command script on SUT
            print "Creating the debug_serial command script on SUT..."
            try:
                sut.copy_sut_vm_boot_debug_serial(sut_vm_info)
            except Exception as e:
                print "ERROR: %s" % e
                traceback.print_exc()
                sys.exit(1)
        else:
            print "START TO SETUP debug_net job TEST ENV..."
            sut_vm_info = {
                "vm_name": sut_vm,
            }
            # Create the debug_net command script
            print "Creating the debug_net command script on SUT..."
            try:
                sut.copy_sut_vm_boot_debug_net(sut_vm_info)
            except Exception as e:
                print "ERROR: %s" % e
                traceback.print_exc()
                sys.exit(1)
    # Boot the SC with serial to test debug job
    pass

    # Reset the VM
    pass
