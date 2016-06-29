#!/usr/bin/python


from libsvvp import Sc, Config


if __name__ == "__main__":
    cfg_file = "./svvp.ini"
    cfg = Config(cfg_file)

    # Get the SC info
    sc_hostname = cfg.get('SC', 'HOSTNAME')
    sc_user = cfg.get('SC', 'USER')
    sc_password = cfg.get('SC', 'PASSWORD')

    # Build the sc object
    sc = Sc(sc_hostname, sc_user, sc_password)

    pass
