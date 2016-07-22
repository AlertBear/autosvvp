#!/usr/bin/python


import sys
import time
import traceback
from libsvvp import Sc, Config
from libsvvp import info_print, error_print, remote_view

if __name__ == "__main__":
    cfg_file = "./svvp.ini"
    cfg = Config(cfg_file)

    # Get the SC info
    sc_hostname = cfg.get('SC', 'HOSTNAME')
    sc_user = cfg.get('SC', 'USER')
    sc_password = cfg.get('SC', 'PASSWORD')
    # Get the network info for configuring the SC VM
    sc_nic = cfg.get('SC', 'NIC')
    sc_bridge = sc_nic + 'br0'

    # Get the VM info
    sc_vm1 = cfg.get('SC_VM_1', 'NAME')
    sc_vm1_cpu_count = cfg.get('SC_VM_1', 'CORE')
    sc_vm1_mem = cfg.get('SC_VM_1', 'MEM')
    sc_vm1_vnc = cfg.get('SC_VM_1', 'VNC')
    sc_vm2 = cfg.get('SC_VM_2', 'NAME')
    sc_vm2_cpu_count = cfg.get('SC_VM_2', 'CORE')
    sc_vm2_mem = cfg.get('SC_VM_2', 'MEM')
    sc_vm2_vnc = cfg.get('SC_VM_2', 'VNC')
    # Get the ISO directory
    win_iso = cfg.get('REQUIRE', 'ISO')
    # Get the virtio file
    vm_virtio = cfg.get('REQUIRE', 'VIRTIO')

    # SC workdir
    workdir = cfg.get('SC', 'WORKDIR')

    sc = Sc(sc_hostname, sc_user, sc_password, workdir)

    print "#######################START SET THE SC##########################"
    # Copy the windows iso file to the sc
    info_print("Copying the windows iso file to the SC...")
    win_iso_name = win_iso.split('/')[-1]
    sc_iso_path = workdir + '/' + win_iso_name
    try:
        sc.scp(win_iso, sc_iso_path)
    except Exception as e:
        error_print("Failed scp iso due to: \n%s" % e)
        sys.exit(1)

    # Copy the virtio file to the SUT
    info_print("Copying the virtio file to the SC...")
    vm_virtio_name = vm_virtio.split('/')[-1]
    sc_virtio_path = workdir + '/' + vm_virtio_name
    try:
        sc.scp(vm_virtio, sc_virtio_path)
    except Exception as e:
        error_print("Failed scp virtio due to: \n%s" % e)
        sys.exit(1)

    # Generate the qemu_ifup script
    info_print("Generating the qemu_ifup file on the SC...")
    try:
        sc.gen_internal_qemu_ifup(sc_bridge)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    # Generate the bridge on the sc
    info_print("Generating the network bridge on the SC...")
    try:
        sc.gen_internal_bridge(sc_bridge, sc_nic)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    # Generate the VM disk on the SC
    win1_raw = 'sc_vm1_windows.raw'
    disk1 = workdir + '/' + win1_raw
    info_print("Generating the virtual disk 1 on the SC...")
    try:
        sc.gen_raw_disk(disk1, '100G')
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    win2_raw = 'sc_vm2_windows.raw'
    disk2 = workdir + '/' + win2_raw
    info_print("Generating the virtual disk 2 on the SC...")
    try:
        sc.gen_raw_disk(disk2, '100G')
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    # Generate the VM1 installation command file
    sc_vm1_info = {
        "vm_name": sc_vm1,
        "mem": sc_vm1_mem,
        "core": sc_vm1_cpu_count,
        "iso": sc_iso_path,
        "disk": disk1,
        "virtio": vm_virtio,
        "vncport": sc_vm1_vnc
    }
    info_print("Generating the VM1 installation command file on the SC...")
    try:
        sc.gen_sc_vm_install(sc_vm1_info)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    # Generate the VM2 installation command file
    sc_vm2_info = {
        "vm_name": sc_vm2,
        "mem": sc_vm2_mem,
        "core": sc_vm2_cpu_count,
        "iso": sc_iso_path,
        "disk": disk2,
        "virtio": sc_virtio_path,
        "vncport": sc_vm2_vnc
    }
    info_print("Generating the VM2 installation command file on the SC...")
    try:
        sc.gen_sc_vm_install(sc_vm2_info)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    # Startup to install the windows on the SC
    info_print("Starting to install the windows VM %s..." % sc_vm1)
    try:
        sc.start_sc_vm_install(sc_vm1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    time.sleep(5)
    # View the vm from remote-viewer
    sc_vm1_vncport = str(5900 + int(sc_vm1_vnc))
    ipport1 = sc_hostname + ":" + sc_vm1_vncport
    remote_view(ipport1)

    # Startup to install the windows2 on the SC
    info_print("Starting to install the windows VM %s..." % sc_vm2)
    try:
        sc.start_sc_vm_install(sc_vm1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    time.sleep(5)
    # View the vm from remote-viewer
    sc_vm2_vncport = str(5900 + int(sc_vm2_vnc))
    ipport2 = sc_hostname + ":" + sc_vm2_vncport
    remote_view(ipport2)

    print "#####################COMPLETE SET THE SC##########################"
    sys.exit(0)
