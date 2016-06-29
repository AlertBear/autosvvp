#!/usr/bin/python

from libsvvp import Sut, Sc, Config


if __name__ == "__main__":
    cfg_file = "./svvp.ini"
    cfg = Config(cfg_file)

    # Get the SUT info
    sut_hostname = cfg.get('SUT', 'HOSTNAME')
    sut_user = cfg.get('SUT', 'USER')
    sut_password = cfg.get('SUT', 'PASSWORD')
