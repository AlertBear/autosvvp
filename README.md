## Introduction

This project is to setup the environment of SVVP testing, which including
Create the sut VM and two SC VMs. 
 
 
start:
> This file is the main program used when deploying the test env, in svvp
testing, there are two kinds of VMs needed to create and setup. 


sut_setup.py:
> The program file used to setup sut VM, which can be called by "start"


sc_setup.py:
> The program file used to setup sc VMs, which can be called by "start"


libsvvp.py:
> The lib file contains all lib function


svvp.ini:
> The configuration file which must be configured before starting 


tool:
> This program will be used to help user do some common configuration,
 like cleanup the system, delete the nic bridge, etc.

 
## Getting started
1. Clone the codes to local disk
   git clone http://10.8.176.174/dguo/autosvvp
2. Configure the parameters in svvp.ini
   vi svvp.ini
3. Start to setup the sut or sc
   ./start sut or ./start sc

## Usage of the tool
tool under the directory is mainly used for doing some common jobs, like 
cleanup the files created on the SUT or SC, delete the nic bridge created
during the test setup.

> usage: tool [-h] [-i {sut,sc}] [-r {sut,sc}] [-u] [-d {serial,net}]
            [-k {sut,sc}] [-c {sut,sc}]
Tool for svvp tests
optional arguments:
  -h, --help            show this help message and exit
  -i {sut,sc}, --interactive {sut,sc}
                        Interactive mode with the host
  -r {sut,sc}, --route {sut,sc}
                        Route info of the sut or sc
  -u, --usb             Create the usb boot command script
  -d {serial,net}, --debug {serial,net}
                        Setup the test env of Debug Capability Test
  -k {sut,sc}, --kill {sut,sc}
                        Kill the process of VM on SUT or SC
  -c {sut,sc}, --cleanup {sut,sc}
