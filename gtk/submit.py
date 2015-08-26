#
# Send bug report to Debian BTS
# This is a significantly simplified version of reportbug.submit
#
import sys
import os
import re
import commands
from subprocess import Popen, STDOUT, PIPE
import rfc822
import smtplib
import socket
import email
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.MIMEAudio import MIMEAudio
from email.MIMEImage import MIMEImage
from email.MIMEBase import MIMEBase
from email.MIMEMessage import MIMEMessage
from email.Header import Header
import mimetypes

quietly = False

ascii_range = ''.join([chr(ai) for ai in range(32,127)])
notascii = re.compile(r'[^'+re.escape(ascii_range)+']')
notascii2 = re.compile(r'[^'+re.escape(ascii_range)+r'\s]')

# Wrapper for MIMEText
class BetterMIMEText(MIMEText):
    def __init__(self, _text, _subtype='plain', _charset=None):
        MIMEText.__init__(self, _text, _subtype, 'us-ascii')
        # Only set the charset paraemeter to non-ASCII if the body
        # includes unprintable characters
        if notascii2.search(_text):
            self.set_param('charset', _charset)

def encode_if_needed(text, charset, encoding='q'):
    needed = False

    if notascii.search(text):
        # Fall back on something vaguely sensible if there are high chars
        # and the encoding is us-ascii
        if charset == 'us-ascii':
            charset = 'iso-8859-15'
        return Header(text, charset)
    else:
        return Header(text, 'us-ascii')

def rfc2047_encode_address(addr, charset, mua=None):
    newlist = []
    addresses = rfc822.AddressList(addr).addresslist
    for (realname, address) in addresses:
        if realname:
            newlist.append( email.Utils.formataddr(
                (str(rfc2047_encode_header(realname, charset, mua)), address)))
        else:
            newlist.append( address )
    return ', '.join(newlist)

def rfc2047_encode_header(header, charset, mua=None):
    if mua: return header
    #print repr(header), repr(charset)

    return encode_if_needed(header, charset)

def send_report(body, fromaddr, sendto, ccaddr, bccaddr,
                headers, package='x', charset="us-ascii", mailing=True,
                sysinfo=None,
                rtype='debbugs',
                mta='/usr/bin/sendmail',
                smtphost='reportbug.debian.org'):
                
    '''Send a report.'''

    failed = using_sendmail = False
    msgname = ''
    body_charset = charset

    if isinstance(body, unicode):
        # Since the body is Unicode, utf-8 seems like a sensible body encoding
        # to choose pretty much all the time.
        body = body.encode('utf-8', 'replace')
        body_charset = 'utf-8'

    mua = None
    tfprefix = 'reportbug-%s-123' % package
    message = BetterMIMEText(body, _charset=body_charset)

    # Standard headers
    message['From'] = rfc2047_encode_address(fromaddr, 'utf-8', mua)
    message['To'] = rfc2047_encode_address(sendto, charset, mua)

    for (header, value) in headers:
        if header in ['From', 'To', 'Cc', 'Bcc', 'X-Debbugs-CC', 'Reply-To',
                      'Mail-Followup-To']:
            message[header] = rfc2047_encode_address(value, charset, mua)
        else:
            message[header] = rfc2047_encode_header(value, charset, mua)

    if ccaddr:
        message['Cc'] = rfc2047_encode_address(ccaddr, charset, mua)

    if bccaddr:
        message['Bcc'] = rfc2047_encode_address(bccaddr, charset, mua)

    replyto = None
    replyto = os.environ.get("REPLYTO", replyto)
    if replyto:
        message['Reply-To'] = rfc2047_encode_address(replyto, charset, mua)

    if mailing:
        message['Message-ID'] = email.Utils.make_msgid('reportbug')
        message['X-Mailer'] = '123'
        message['Date'] = email.Utils.formatdate(localtime=True)

    addrs = [str(x) for x in (message.get_all('To', []) +
                              message.get_all('Cc', []) +
                              message.get_all('Bcc', []))]
    alist = email.Utils.getaddresses(addrs)

    cclist = [str(x) for x in message.get_all('X-Debbugs-Cc', [])]
    debbugs_cc = email.Utils.getaddresses(cclist)
    if cclist:
        del message['X-Debbugs-Cc']
        addrlist = ', '.join(cclist)
        message['X-Debbugs-Cc'] = rfc2047_encode_address(addrlist, charset, mua)


    message = message.as_string()
    filename = None
    if smtphost:
        toaddrs = [x[1] for x in alist]
        smtp_message = re.sub(r'(?m)^[.]', '..', message)

        tryagain = True
        refused = None
        retry = 0
        while tryagain:
            tryagain = False
            print("Connecting to %s via SMTP...\n" % smtphost)
            try:
                conn = None
                # if we're using reportbug.debian.org, send mail to
                # submit
                if smtphost.lower() == 'reportbug.debian.org':
                    conn = smtplib.SMTP(smtphost,587)
                else: 
                    conn = smtplib.SMTP(smtphost)
                response = conn.ehlo()
                if not (200 <= response[0] <= 299):
                    conn.helo()

                refused = conn.sendmail(fromaddr, toaddrs, smtp_message)
                conn.quit()
            except (socket.error, smtplib.SMTPException), x:
                # If wrong password, try again...
                if isinstance(x, smtplib.SMTPAuthenticationError):
                    print('SMTP error: authentication failed.  Try again.\n')
                    tryagain = True
                    smtppasswd = None
                    retry += 1
                    if retry <= 2:
                        continue
                    else:
                        tryagain = False

        # Handle when some recipients are refused.
        if refused:
            for (addr, err) in refused.iteritems():
                print('Unable to send report to %s: %d %s\n' % 
                        (addr, err[0], err[1]))
            fh, msgname = TempFile(prefix=tfprefix, dir=draftpath)
            fh.write(message)
            fh.close()

            print('Wrote bug report to %s\n' %  msgname)
    else:
        try:
            pipe.write(message)
            pipe.flush()
            if msgname:
                print("Bug report written as %s\n" % msgname)
        except IOError:
            failed = True
            pipe.close()

        if failed or (pipe.close() and using_sendmail):
            failed = True
            fh, msgname = TempFile(prefix=tfprefix, dir=draftpath)
            fh.write(message)
            fh.close()
            print('Error: send/write operation failed, bug report '
                            'saved to %s\n', msgname)

    return
