#!/usr/bin/python

import argparse
from libsvvp import Sut, Sc, Config


if __name__ == "__main__":
    cfg_file = "./svvp.ini"
    cfg = Config(cfg_file)

    # Get the SUT info
    sut_hostname = cfg.get('SUT', 'HOSTNAME')
    sut_user = cfg.get('SUT', 'USER')
    sut_password = cfg.get('SUT', 'PASSWORD')

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
    # Add to create the boot_debug file for the sut or sc
    parser.add_argument('-b',
                        action="store",
                        choices=["sut", "sc"],
                        dest="boot_debug",
                        help="Create the boot_debug script to test the boot_debug job")
    # Add to create the boot_usb file for the sut or sc

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
