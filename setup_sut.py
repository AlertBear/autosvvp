#!/usr/bin/python


import sys
from libsvvp import Server, Config
from libsvvp import info_print, error_print

if __name__ == "__main__":
    cfg_file = "./svvp.ini"
    cfg = Config(cfg_file)

    # Get the SUT info
    sut_hostname = cfg.get('SUT', 'HOSTNAME')
    sut_user = cfg.get('SUT', 'USER')
    sut_password = cfg.get('SUT', 'PASSWORD')

    # Get the network info for configuring the SUT
    sut_bridge = cfg.get('SUT_NET', 'BRIDGE')
    sut_nic = cfg.get('SUT_NET', 'NIC')

    # Get the VM info
    sut_vm = cfg.get('VM', 'NAME')
    sut_vm_cpu_count = cfg.get('VM', 'CPU_COUNT')
    sut_vm_cpu_mode = cfg.get('VM', 'CPU_MODE')
    sut_vm_mem = cfg.get('VM', 'MEM')

    # Get the rhvh product and version
    rhvh = cfg.get("RHVH", 'PRODUCT')
    rhvh_ver = cfg.get("RHVH", "VERSION")

    # Get the ISO directory
    win_iso = cfg.get('VM', 'ISO')

    # Get the virtio file
    vm_virtio = cfg.get('VM', 'VIRTIO')

    # First copy the iso file to the SUT
    sut = Server(sut_hostname, sut_user, sut_password)
    info_print("Copying the iso file to the SUT...")
    win_iso_name = win_iso.split('/')[-1]
    sut_iso_path = '/data' + '/' + win_iso_name
    try:
        sut.scp(win_iso, sut_iso_path)
    except Exception as e:
        error_print("Failed scp iso due to: \n%s" % e)
        sys.exit(1)

    # Copy the virtio file to the SUT
    info_print("Copying the virtio file to the SUT...")
    vm_virtio_name = vm_virtio.split('/')[-1]
    sut_virtio_path = '/data' + '/' + vm_virtio_name
    try:
        sut.scp(win_iso, sut_virtio_path)
    except Exception as e:
        error_print("Failed scp virtio due to: \n%s" % e)
        sys.exit(1)

    # Generate the qemu_ifup script
    info_print("Generating the  qemu_ifup file on the SUT...")
    try:
        sut.gen_qemu_ifup(sut_bridge)
    except Exception as e:
        error_print("Failed generate the network bridge due to: \n%s" % e)
        sys.exit(1)

    disk = "/data/windows.raw"
    # Generate the VM installation command file
    vf_info = {
        "vm_name": sut_vm,
        "cpu_mode": sut_vm_cpu_mode,
        "mem": sut_vm_mem,
        "core": sut_vm_cpu_count,
        "product": rhvh,
        "version": rhvh_ver,
        "iso": sut_virtio_path,
        "disk": disk,
        "virtio": sut_virtio_path
    }

    # Generate the bridge on the SUT
    info_print("Generating the network bridge on the SUT...")
    try:
        sut.gen_bridge(sut_bridge, sut_nic)
    except Exception as e:
        error_print("Failed generate the network bridge due to: \n%s" % e)
        sys.exit(1)

    # Generate the VM disk on the SUT
    info_print("Generating the virtual disk on the SUT...")
    try:
        sut.gen_raw_disk(disk)
    except Exception as e:
        error_print("Failed generate virtual disk due to: \n%s" % e)
        sys.exit(1)

    # Startup to install the windows on the SUT
    pass
