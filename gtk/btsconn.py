#!/usr/bin/python3

import socket
import os, os.path
import json


class BtsConn:
    '''
    A connection to the debianbts proxy
    '''

    def __init__(self):
        self.sockfile = '/var/crash/.apport_local_socket'
        if os.path.exists(self.sockfile):
            self.client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.client.connect(self.sockfile)
        else:
            self.client = None
    
    def close(self):
        '''
        Close connection
        '''

        if self.client is not None:
            self.client.close()

    def sendcmd(self, action, arg):
        '''
        Send a command to proxy
        '''
        if self.client is None:
            return

        cmd = {}
        cmd['action'] = action
        cmd['arg'] = arg
        json_data = json.dumps(cmd)
        self.client.sendall(bytes(json_data, 'UTF-8'))
        
        data = self.client.recv(1024000)
        return json.loads(data.decode('UTF-8'))


def get_bugs(pkg):
    '''
    Get a list of bug numbers of the given package
    '''
    
    bts = BtsConn()
    ret = bts.sendcmd('GET_BUGS', pkg)
    bts.close()
    return ret

def get_bug_log(bugnum):
    '''
    Get buglog with the given bug num
    '''

    bts = BtsConn()
    ret = bts.sendcmd('GET_BUG_LOG', bugnum)
    bts.close()
    return ret

def get_status(pkg):
    '''
    Get bug reports of the given package
    '''

    bts = BtsConn()
    ret = bts.sendcmd('GET_STATUS', pkg)
    bts.close()
    return ret

if __name__ == '__main__':
    '''
    For testing only
    '''

    print(get_status('python'))
