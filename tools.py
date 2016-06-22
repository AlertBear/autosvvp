#!/usr/bin/python

import pxssh
import sys
import ConfigParser
import pexpect
import subprocess


class ExecError(Exception):
    pass


class Server(object):
    def __init__(self, hostname, username, passwd):
        self.hostname = hostname
        self.username = username
        self.passwd = passwd

    def sendcmd(self, cmd, check=True, timeout=-1):
        s = pxssh.pxssh()
        s.login(self.hostname, self.username, self.passwd)
        s.sendline(cmd)
        s.prompt(timeout)
        out = s.before.strip(cmd).strip()

        # Check the command were execute successfully on the remote server
        retcode_cmd = 'echo $?'
        s.sendline(retcode_cmd)
        s.prompt()
        retcode = s.before.strip(retcode_cmd).strip()
        if check:
            if retcode != '0':
                raise ExecError("[%s]: Execute [%s]:\n%s" % (self.hostname, cmd, out))
            else:
                return out
        return out

    def scp(self, file, rmtdir):
        cmd = "scp %s %s@%s:%s" % (file, self.username, self.hostname, rmtdir)
        child = pexpect.spawn(cmd)
        child.send('\r')
        prompts = ['password:', 'lost connection', '#', '$', pexpect.TIMEOUT, pexpect.EOF]

        while True:
            i = child.expect(prompts, timeout=600)

            if i == 0:
                child.sendline(self.passwd)
                child.expect()
            elif i == 1:
                raise Exception("Failed to scp due to incorrect password or the sshd status on remote server")
            elif i == 2:
                child.close()
                break
            elif i == 3:
                child.close()
                break
            elif i == 4:
                raise Exception("Failed to scp due to TIMEOUT")
            elif i == 5:
                raise Exception("Failed to scp due to EOF")


class Config:
    def __init__(self, path):
        self.path = path
        self.cf = ConfigParser.ConfigParser()
        self.cf.read(self.path)

    def get(self, field, key):
        result = ""
        try:
            result = self.cf.get(field, key)
        except:
            result = ""
        return result

    def set(self, field, key, value):
        try:
            self.cf.set(field, key, value)
            self.cf.write(open(self.path, 'w'))
        except:
            return False
        return True


def read_config(config_file_path, field, key):
    cf = ConfigParser.ConfigParser()
    try:
        cf.read(config_file_path)
        result = cf.get(field, key)
    except:
        sys.exit(1)
    return result


def write_config(config_file_path, field, key, value):
    cf = ConfigParser.ConfigParser()
    try:
        cf.read(config_file_path)
        cf.set(field, key, value)
        cf.write(open(config_file_path, 'w'))
    except:
        sys.exit(1)
    return True


def execute(cmd, check=True):
    try:
        out = subprocess.check_output(cmd, shell=True)
    except subprocess.CalledProcessError as e:
        if check:
            raise ExecError(e.output)
        else:
            return e.output
    else:
        return out


# Simple test for the class Server
if __name__ == "__main__":
    testserver = sys.argv[1]
    username = "root"
    passwd = "redhat"
    mserver = Server(testserver, username, passwd)

    file = '/tmp/server.py'
    rmtdir = '/data'
    mserver.scp(file, rmtdir)
