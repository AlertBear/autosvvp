#!/usr/bin/python

from libsvvp import Sut, Sc, Config


if __name__ == "__main__":
    cfg_file = "./svvp.ini"
    cfg = Config(cfg_file)

    # Get the SUT info
    sut_hostname = cfg.get('SUT', 'HOSTNAME')
    sut_user = cfg.get('SUT', 'USER')
    sut_password = cfg.get('SUT', 'PASSWORD')

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
    pass

    # Boot the SC with serial to test debug job
    pass

    # Reset the VM
    pass
