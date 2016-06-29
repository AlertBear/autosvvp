#!/usr/bin/python


import sys
import time
import traceback
from libsvvp import Sut, Config
from libsvvp import info_print, error_print, remote_view

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
    # Get the network info for configuring the SUT VM
    sut_bridge = cfg.get('SUT', 'BRIDGE')
    sut_nic = cfg.get('SUT', 'NIC')
    # Get the VM info
    sut_vm = cfg.get('SUT_VM', 'NAME')
    sut_vm_cpu_count = cfg.get('SUT_VM', 'CPU_COUNT')
    sut_vm_cpu_mode = cfg.get('SUT_VM', 'CPU_MODE')
    sut_vm_mem = cfg.get('SUT_VM', 'MEM')
    # Get the ISO directory
    win_iso = cfg.get('REQUIRE', 'ISO')
    # Get the virtio file
    vm_virtio = cfg.get('REQUIRE', 'VIRTIO')

    # Sut workdir
    workdir = cfg.get('SUT', 'WORKDIR')

    sut = Sut(sut_hostname, sut_user, sut_password, workdir)

    info_print("START SET THE SUT\n######################################")
    # Copy the windows iso file to the SUT
    info_print("Copying the windows iso file to the SUT...")
    win_iso_name = win_iso.split('/')[-1]
    sut_iso_path = workdir + '/' + win_iso_name
    try:
        sut.scp(win_iso, sut_iso_path)
    except Exception as e:
        error_print("Failed scp iso due to: \n%s" % e)
        sys.exit(1)

    # Copy the virtio file to the SUT
    info_print("Copying the virtio file to the SUT...")
    vm_virtio_name = vm_virtio.split('/')[-1]
    sut_virtio_path = workdir + '/' + vm_virtio_name
    try:
        sut.scp(vm_virtio, sut_virtio_path)
    except Exception as e:
        error_print("Failed scp virtio due to: \n%s" % e)
        sys.exit(1)

    # Generate the qemu_ifup script
    info_print("Generating the qemu_ifup file on the SUT...")
    try:
        sut.gen_qemu_ifup(sut_bridge)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    # Generate the bridge on the SUT
    info_print("Generating the network bridge on the SUT...")
    try:
        sut.gen_bridge(sut_bridge, sut_nic)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    # Generate the VM disk on the SUT
    win_raw = 'windows.raw'
    disk = workdir + '/' + win_raw
    info_print("Generating the virtual disk on the SUT...")
    try:
        sut.gen_raw_disk(disk)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    # Generate the VM installation command file
    vf_info = {
        "vm_name": sut_vm,
        "cpu_mode": sut_vm_cpu_mode,
        "mem": sut_vm_mem,
        "core": sut_vm_cpu_count,
        "product": rhvh,
        "version": rhvh_ver,
        "iso": sut_iso_path,
        "disk": disk,
        "virtio": sut_virtio_path
    }
    info_print("Generating the VM installation command file on the SUT...")
    try:
        sut.gen_sut_vm_install(vf_info)
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    # Startup to install the windows on the SUT
    info_print("Starting to install the windows VM...")
    try:
        sut.start_vm_install()
    except Exception:
        traceback.print_exc()
        sys.exit(1)

    time.sleep(5)
    # View the vm from remote-viewer
    ipport = sut_hostname + ":" + "5900"
    remote_view(ipport)

    info_print("COMPLETE SET THE SUT\n######################################")
    sys.exit(0)
