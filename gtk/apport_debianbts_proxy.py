#!/usr/bin/python2

import debianbts
import socket
import os, os.path
import time
import json

'''
This is the debianbts proxy used by apport to fetch data from
Debian BTS. Apport itself cannot use debianbts library directly
because of python version issues so we create this proxy as
a workaround.
'''

sockfile = '/var/crash/.apport_local_socket'

def execute(cmd, sock):
    '''
    execute command and send data back

    GET_BUGS:<package>
    GET_STATUS:<package>
    GET_BUG_LOG:<bug num>
    SEND_REPORT:<data>
    '''

    action = cmd['action']
    arg = cmd['arg']

    print('Executing command `%s` with args: %s' % (action, arg))

    if action == 'GET_BUGS':
        bug_nums = debianbts.get_bugs('package', arg)
        print("bug nums:", bug_nums)
        data = json.dumps(bug_nums)
        sock.sendall(data)

    elif action == 'GET_STATUS':
        bug_nums = debianbts.get_bugs('package', arg)
        reports = debianbts.get_status(bug_nums)

        simple_reports = []
        for r in reports:
            sr = {}
            sr['bug_num'] = r.bug_num
            sr['subject'] = r.subject
            sr['severity'] = r.severity
            sr['package'] = r.package
            simple_reports.append(sr)

        data = json.dumps(simple_reports)
        sock.sendall(data)

    elif action == 'GET_BUG_LOG':
        buglogs = debianbts.get_bug_log(arg)
        simple_buglogs = []
        for l in buglogs:
            sl = {}
            sl['body'] = l['body']
            sl['msg_num'] = l['msg_num']
            simple_buglogs.append(sl)

        data = json.dumps(simple_buglogs)
        sock.sendall(data)

    elif action == 'SEND_REPORT':
        print(arg)

        import submit
        submit.prepare_and_send(
                arg['package'],
                arg['version'],
                arg['severity'],
                arg['tag'],
                arg['subject'],
                arg['body'],
                arg['sysinfo'],
                arg['fromaddr'],
                arg['sendto'])


        data = json.dumps('succ')
        sock.sendall(data)

def main():
    if os.path.exists(sockfile):
        os.remove(sockfile)

    server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_sock.bind(sockfile)
    server_sock.listen(2)
    print('Listening connections on %s' % sockfile)

    while True:
        client_sock, client_addr = server_sock.accept()

        data = client_sock.recv(1024)
        cmd = json.loads(data)
        execute(cmd, client_sock)

    server_sock.close()
    os.remove(sockfile)


if __name__ == '__main__':
    main()
