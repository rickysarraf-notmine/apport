import subprocess

def collect_sysinfo(package, crashfile):                                                          
    '''
    package, package name
    crashfile, /var/crash/xxxx.crash
    '''

    script = '/usr/share/bug/%s/script' % package
    tmpout = '/tmp/.apport-reportbug'
    	                                                                   
    # TODO: what if cannot find script?                                        
    p = subprocess.Popen(['/usr/share/reportbug/handle_bugscript', script, tmpout], 
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    	                                                                   
    out, err = p.communicate()
    info = ''
    for l in open(tmpout).readlines():
        info += l
    	                                                                   
    # TODO: add apport info

    return info

def installed_version(package):
    p = subprocess.Popen(['dpkg', '--status', package], stdout=subprocess.PIPE) 
    out, err = p.communicate()
    
    version = ''
    out = out.decode('utf-8') # this is necessary for supporting Python3.x

    for l in out.split('\n'):
        if l.startswith('Version:'):
            version = l.replace('Version:', '')
            break
    
    return version.strip()

def user_email():
    return 'localhost'

if __name__ == '__main__':
    print(installed_version('gedit'))
