#!/usr/bin/python


from tools import Server, Config


if __name__ == "__main__":
    cfg_file = "./svvp.ini"
    cfg = Config(cfg_file)

    # Get the SUT info
    hostname = cfg.get('SUT', 'HOSTNAME')
    user = cfg.get('SUT', 'USER')
    password = cfg.get('SUT', 'PASSWORD')

    # Get the network info for configuring the SUT
    bridge = cfg.get('SUT_NET', 'BRIDGE')
    nic = cfg.get('SUT_NET', 'NIC')

    # Get the VM info
    vm = cfg.get('VM', 'NAME')
    cpu = cfg.get('VM', 'CPU')
    mem = cfg.get('VM', 'MEM')

    # Get the ISO directory
    iso = cfg.get('ISO', 'ISO')

    # Get the virtio file
    virtio = cfg.get('VIRTIO', 'VIRTIO')

    # First copy the iso file to the SUT
    





