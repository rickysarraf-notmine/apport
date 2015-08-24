#!/usr/bin/python
# -*- python -*-
# reportbug - Report a bug in the Debian distribution.
#   Written by Chris Lawrence <lawrencc@debian.org>
#   Copyright (C) 1999-2008 Chris Lawrence
#   Copyright (C) 2008-2014 Sandro Tosi <morph@debian.org>
#
# This program is freely distributable per the following license:
#
##  Permission to use, copy, modify, and distribute this software and its
##  documentation for any purpose and without fee is hereby granted,
##  provided that the above copyright notice appears in all copies and that
##  both that copyright notice and this permission notice appear in
##  supporting documentation.
##
##  I DISCLAIM ALL WARRANTIES WITH REGARD TO THIS SOFTWARE, INCLUDING ALL
##  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS, IN NO EVENT SHALL I
##  BE LIABLE FOR ANY SPECIAL, INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY
##  DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
##  WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,
##  ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS
##  SOFTWARE.

DEFAULT_BTS = 'debian'

import sys
import os
import optparse
import re
import locale
import commands
import rfc822
import gettext
import textwrap
# for blogging of attachments file
from glob import glob

from reportbug import utils
from reportbug import (
    VERSION,
    VERSION_NUMBER,
    COPYRIGHT,
    LICENSE
    )
from reportbug.utils import (
    MODE_EXPERT, MODE_ADVANCED, MODE_NOVICE, MODE_STANDARD,
    )
from reportbug.tempfiles import (
    TempFile,
    tempfile_prefix,
    cleanup_temp_file,
    )
from reportbug.exceptions import (
    UINotImportable, UINotImplemented,
    NoNetwork, NoPackage, NoBugs, NoReport,
    )
from reportbug import submit
from reportbug import checkversions
from reportbug import debbugs
from reportbug import checkbuildd
import reportbug.ui.text_ui as ui

from reportbug.ui import (
    UIS, AVAILABLE_UIS, getUI
    )

#ui = getUI('text')

try:
    gettext.install('reportbug')
except IOError:
    pass


# Magic constant time
MIN_USER_ID = 250
quietly = False

# Cheat for now.
# ewrite() may put stuff on the status bar or in message boxes depending on UI
def ewrite(*args):
    return quietly or ui.log_message(*args)

def efail(*args):
    ui.display_failure(*args)
    sys.exit(1)

# Lame message when we store a report as a temp file.
def stopmsg(filename):
    ui.final_message(
        'reportbug stopped; your incomplete report is stored as "%s".\n'
        'This file may be located in a temporary directory; if so, it might '
        'disappear without any further notice. To recover this file to use '
        'it as bug report body, please take a look at the "-i FILE, '
        '--include=FILE" option.\n'
        'Alternatively, you can copy the content of the temporary file (both '
        'headers and body) and copy it into your MUA and send the mail to '
        'submit@bugs.debian.org, editing the subject and bug text as needed '
        '(but not altering the other information).\n', filename)

def check_attachment_size(attachfile, maxsize):
    """Check if the attachment size is bigger than max allowed"""
    statinfo = os.stat(attachfile)
    attachsize = statinfo[6]
    return attachsize >= maxsize

def include_file_in_report(message, message_filename,
                           attachment_filenames, package_name,
                           include_filename, charset, inline=False, draftpath=None):
    """ Include a file in the report.

        :parameters:
            `message`
                The current text of the message.
            `message_filename`
                The current message filename.
            `attachment_filenames`
                List of current attachment filenames.
            `package_name`
                Name of the package for this report.
            `include_filename`
                Full pathname of the file to be included.
            `inline`
                If True, include the message inline with the message
                text. Otherwise, add the file path to the attachments.

        :return value:
            Tuple (`message`, `message_filename`, `attachments`) of
            values as modified during the process of including the new
            file.

        """
    if inline:
        try:
            fp = open(include_filename)
            message += '\n*** %s\n%s' % (
                       include_filename.decode(charset, 'replace'),
                       fp.read().decode(charset, 'replace'))
            fp.close()
            fp, temp_filename = TempFile(
                prefix=tempfile_prefix(package_name), dir=draftpath)
            fp.write(message.encode(charset, 'replace'))
            fp.close()
            os.unlink(message_filename)
            message_filename = temp_filename
        except (IOError, OSError), exc:
            ui.display_failure('Unable to attach file %s\n%s\n',
                               include_filename, str(exc))
    else:
        attachment_filenames.append(include_filename)

    return (message, message_filename, attachment_filenames)

# Useful to retrieve CCs given in handle_editing
CCS = []
def handle_editing(filename, dmessage, options, sendto, attachments, package,
                   severity, mode, editor=None, charset='utf-8', tags=''):
    if not editor:
        editor = options.editor
    editor = utils.which_editor(editor)
    message = None
    patch = False
    skip_editing = False
    # is this report just to be saved on a file ?
    justsave = False
    while True:
        if not skip_editing:
            (message, changed) = ui.spawn_editor(message or dmessage, filename,
                                                 editor, charset)
        skip_editing = False
        if not message:
            x = ''
            while x != 'y':
                x = ui.select_options('Done editing', 'Ynq',
                                      {'y': 'Continue (editing done).',
                                       'n': "Don't continue yet.",
                                       'q': 'Exit without sending report.'})
                if x == 'q':
                    stopmsg(filename)
                    sys.exit(1)

            message = open(filename).read().decode(charset, 'replace')
            changed = True

        prompt = 'Submit this report on %s (e to edit)' % package

        if options.kudos:
            prompt = 'Send this message (e to edit)'
            ewrite("Message will be sent to %s\n", sendto)
        elif options.outfile:
            ewrite("Report will be saved as %s\n", options.outfile)
        else:
            ewrite("Report will be sent to %s\n", sendto)

        if attachments:
            ewrite('Attachments:\n')
            for name in attachments:
                ewrite(' %s\n', name)

        subject = re.search('^Subject: ', message, re.M | re.I)
        if not subject:
            ui.long_message('No subject found in message.  Please edit again.\n')

        menuopts = "Ynaceilmpqdts"

        if not changed or not subject:
            menuopts = "ynacEilmpqdts"

        # cfr Debian BTS #293361
        if package == 'wnpp':
            for itp_line in debbugs.itp_template.rsplit('\n'):
                # if the line is not empty and it's in the message the user wrote
                if itp_line in message and itp_line != '':
                    ewrite("Wrong line: %s\n", itp_line)
                    menuopts = "Eq"
                    prompt = 'ERROR: you have composed a WNPP bug report with fields unchanged from the template; this will NOT be submitted. Please edit all fields so they contain correct values (e to edit)'

        if options.outfile:
            yesmessage = 'Save the report into %s .' % options.outfile
        else:
            yesmessage = 'Submit the bug report via email.'

        x = ui.select_options(prompt, menuopts,
                              {'y': yesmessage,
                               'n': "Don't submit the bug report; instead, "
                               "save it in a temporary file (exits reportbug).",
                               'q': "Save it in a temporary file and quit.",
                               'a': "Attach a file.",
                               'd': "Detach an attachment file.",
                               'i': "Include a text file.",
                               'c': "Change editor and re-edit.",
                               'e': 'Re-edit the bug report.',
                               'l': 'Pipe the message through the pager.',
                               'p': 'print message to stdout.',
                               't': 'Add tags.',
                               's': 'Add a X-Debbugs-CC recipient (a CC but after BTS processing).',
                               'm': "Choose a mailer to edit the report."})

        if x in ('a', 'i'):
            invalid = True
            while invalid:
                if x == 'i':
                    attachfile = ui.get_filename('Choose a text file to include: ')
                else:
                    attachfile = ui.get_filename('Choose a file to attach: ')
                if attachfile:
                    # expand vars & glob the input string
                    attachfile = os.path.expanduser(attachfile)
                    attachfglob = glob(attachfile)
                    # check if the globbing returns any result
                    if not attachfglob:
                        ui.display_failure("Can't find %s to include!\n", attachfile)
                    # loop over the globbed 'attachfile', you can specify wildcards now
                    for attachf in attachfglob:
                        if os.access(attachf, os.R_OK) and os.path.isfile(attachf):
                            if check_attachment_size(attachf, options.max_attachment_size):
                                ewrite('The attachment file %s size is bigger than the maximum of %d bytes: '
                                       'reduce its size else the report cannot be sent\n' %
                                       (attachf, options.max_attachment_size))
                            else:
                                invalid = False
                                inline = (x == 'i')
                                (message, filename, attachments) = include_file_in_report(
                                    message, filename, attachments, package,
                                    attachf, charset, inline=inline, draftpath=options.draftpath)
                                if not inline:
                                    skip_editing = True
                        else:
                            ui.display_failure("Cannot include %s!\n", attachf)
                else:
                    break
        elif x == 'd':
            skip_editing = True
            if not attachments:
                ewrite('No attachment file to detach.\n')
            else:
                detachprompt = 'Choose an attachment file to detach (an empty line will exit): '
                myattachments = []
                myattachments = [(x, '') for x in attachments]
                filetodetach = ui.menu(detachprompt, myattachments,
                    'Select the file:', default='', empty_ok=True)
                # only if selection is not empty and the file is in the attachment list
                if filetodetach != '' and filetodetach in attachments:
                    attachments.remove(filetodetach)
                    ewrite('Attachment file "%s" successfully detached.\n\n', filetodetach)
                else:
                    ewrite('Nothing to detach.\n\n')
        elif x == 'c':
            ed = ui.get_filename('Choose editor: ', default=options.editor)
            if ed:
                editor = ed
        elif x == 'm':
            mailers = [(x, '') for x in utils.MUA.keys()]
            mailers.sort()
            mailer = ui.menu('Choose a mailer for your report', mailers,
                             'Select mailer: ', default='', empty_ok=True)
            if mailer and mailer != -1:
                if not utils.mua_exists(utils.MUA[mailer]):
                    ewrite("Selected mail user agent cannot be found.\n")
                else:
                    # get the MUA
                    mailer = utils.MUA.get(mailer)
                    # in case there are attachments
                    if attachments:
                        # notify that they will be lost
                        if ui.yes_no(
                            'Editing the report will lose all attachments: are you sure you want to continue?',
                            'Yes, please',
                            'No, thanks',
                            True):
                            # if ok, go into the MUA
                            options.mua = mailer
                            break
                        # else, go back to the menu
                        else:
                            pass
                    # no attach, we can go directly into the MUA
                    else:
                        options.mua = mailer
                        break
            skip_editing = True
        elif x in ('n', 'q'):
            justsave = True
            break
        elif x in ('l', 'p'):
            skip_editing = True
            if x == 'l':
                pager = os.environ.get('PAGER', 'sensible-pager')
                os.popen(pager, 'w').write(message.encode(charset, 'replace'))
            else:
                sys.stdout.write(message.encode(charset, 'replace'))
        elif x == 't':
            newtaglist = []
            skip_editing = True
            ntags = debbugs.get_tags(severity, mode)
            newtaglist = ui.select_multiple(
                'Do any of the following apply to this report?', ntags,
                'Please select tags: ')
            if newtaglist:
                oldtags = ''
                newtags = ''
                if tags:
                    oldtags = 'Tags: ' + tags
                    newtaglist += tags.split()
                    # suppress twins in the tag list
                    newtaglist = list(set(newtaglist))
                    newtags = 'Tags: ' + ' '.join(newtaglist)
                else:
                    oldtags = 'Severity: ' + severity + '\n'
                    newtags = oldtags + 'Tags: ' + ' '.join(newtaglist) + '\n'
                if 'patch' in newtaglist:
                    patch = True
                message = message.replace(oldtags, newtags)
                open(filename, 'w').write(message.encode(charset, 'replace'))
        elif x == 's':
            skip_editing = True
            ccemail = ui.get_string(
                ('Please add the email address. Just press ENTER if you '
                 'don\'t want anymore.'), empty_ok=True, force_prompt=True)
            if ccemail:
                CCS.append(ccemail)
        elif x == 'y':
            if message == dmessage:
                x = ui.select_options(
                    'Report is unchanged.  Edit this report or quit', 'Eqs',
                    {'q': "Don't submit the bug report; instead, save it "
                     "in a temporary file and quit.",
                     'e': 'Re-edit the bug report.',
                     's': 'Send report anyway.'})
                if x == 'q':
                    stopmsg(filename)
                    sys.exit(1)
                    break
                elif x == 's':
                    ewrite('Sending empty report anyway...\n')
                    break
            else:
                break

    return open(filename).read(), patch, justsave

def find_package_for(filename, notatty=False, pathonly=False):
    ewrite("Finding package for '%s'...\n", filename)
    (newfilename, packages) = utils.find_package_for(filename, pathonly)
    if newfilename != filename:
        filename = newfilename
        ewrite("Resolved as '%s'.\n", filename)
    if not packages:
        ewrite("No packages match.\n")
        return (filename, None)
    elif len(packages) > 1:
        packlist = packages.items()
        packlist.sort()

        if notatty:
            print "Please re-run reportbug selecting one of these packages:"
            for pkg, files in packlist:
                print "  "+pkg
            sys.exit(1)

        packs = []
        for pkg, files in packlist:
            if len(files) > 3:
                files[3:] = ['...']
            packs.append( (pkg, ', '.join(files) ) )

        package = ui.menu("Multiple packages match: ", packs, 'Select one '
                          'of these packages: ', any_ok=True)
        # for urwid, when pressing 'Cancel' in the menu
        if package == -1:
            package = None
        return (filename, package)
    else:
        package = packages.keys()[0]
        ewrite("Using package '%s'.\n", package)
        return (filename, package)

def validate_package_name(package):
    if not re.match(r'^[a-z0-9][a-z0-9\-\+\.]+$', package):
        ui.long_message("%s is not a valid package name.", package)
        package = None
    return package

def get_other_package_name(others):
    """Displays the list of pseudo-packages and returns the one selected."""

    result = ui.menu("Please enter the name of the package in which you "
                     "have found a problem, or choose one of these bug "
                     "categories:", others, "Enter a package: ", any_ok=True,
                     default='')
    if isinstance(result, basestring):
        return result
    else:
        return None

def get_package_name(bts='debian', mode=MODE_EXPERT):
    others = debbugs.SYSTEMS[bts].get('otherpkgs')
    prompt = "Please enter the name of the package in which you have found "\
             "a problem"
    if others:
        prompt += ", or type 'other' to report a more general problem."
    else:
        prompt += '.'
    prompt += " If you don't know what package the bug is in, "\
              "please contact debian-user@lists.debian.org for assistance."

    options = []
    pkglist = commands.getoutput('apt-cache pkgnames')
    if pkglist:
        options += pkglist.split()
    if others:
        options += others.keys()

    package = None
    while package is None:
        package = ui.get_string(prompt, options, force_prompt=True)
        if not package:
            return
        if others and package and package == 'other':
            package = get_other_package_name(others)
        if not package:
            return
        package = validate_package_name(package)

    if package in ('kernel', 'linux-image'):
        ui.long_message(
            "Automatically selecting the package for the running kernel")
        package = utils.get_running_kernel_pkg()

    if mode < MODE_STANDARD:
        if package == 'reportbug':
            if not ui.yes_no('Is "reportbug" actually the package you are '
                             'having problems with',
                             'Yes, I am actually experiencing a problem with '
                             'reportbug.',
                             'No, I really meant to file a bug report on '
                             'another package.'):
                return get_package_name(bts, mode)

    if mode < MODE_EXPERT:
        if package in ('bugs.debian.org', 'debbugs'):
            if ui.yes_no('Are you reporting a problem with this program '
                         '(reportbug)', 'Yes, this is actually a bug in '
                         'reportbug.', 'No, this is really a problem in the '
                         'bug tracking system itself.'):
                package = 'reportbug'

        if package in ('general', 'project', 'debian-general', 'base'):
            if not ui.yes_no(
                "Are you sure this bug doesn't apply to a specific package?",
                'Yes, this bug is truly general.',
                'No, this is not really a general bug.', False):
                return get_package_name(bts, mode)

        if package == 'wnpp':
            if not ui.yes_no(
                'Are you sure you want to file a WNPP report?',
                'Yes, I am a developer or know what I\'m doing.',
                'No, I am not a developer and I don\'t know what wnpp means.',
                False):
                return get_package_name(bts, mode)

        if package in ('ftp.debian.org', 'release.debian.org'):
            if not ui.yes_no(
                'Are you sure you want to file a bug on %s?' % (package),
                'Yes, I am a developer or know what I\'m doing.',
                'No, I am not a developer and I don\'t know what %s is.' % (package),
                False):
                return get_package_name(bts, mode)

    return package

def special_prompts(package, bts, ui, fromaddr, timeout, online, http_proxy):
    prompts = debbugs.SYSTEMS[bts].get('specials')
    if prompts:
        pkgprompts = prompts.get(package)
        if pkgprompts:
            return pkgprompts(package, bts, ui, fromaddr, timeout, online, http_proxy)
    return

def offer_configuration(options):
    charset = locale.nl_langinfo(locale.CODESET)
    # It would be nice if there were some canonical character set conversion
    if charset.lower() == 'ansi_x3.4-1968':
        charset = 'us-ascii'
    ui.charset = charset

    if not options.configure:
        ui.long_message('Welcome to reportbug!  Since it looks like this is '
                        'the first time you have used reportbug, we are '
                        'configuring its behavior.  These settings will be '
                        'saved to the file "%s", which you will be free to '
                        'edit further.\n\n', utils.USERFILE)
    mode = ui.menu('Please choose the default operating mode for reportbug.',
                   utils.MODES, 'Select mode: ', options.mode,
                   order=utils.MODELIST)

    if options.configure or not options.interface:
        # if there is only one UI available, the it's 'text', else ask
        if len(AVAILABLE_UIS) == 1:
            interface = 'text'
        else:
            interface = ui.menu(
                'Please choose the default interface for reportbug.', AVAILABLE_UIS,
                'Select interface: ', options.interface, order=['text'])
    else:
        interface = options.interface

    online = ui.yes_no('Will reportbug often have direct '
                       'Internet access?  (You should answer yes to this '
                       'question unless you know what you are doing and '
                       'plan to check whether duplicate reports have been '
                       'filed via some other channel.)',
                       'Yes, reportbug should assume it has access to the '
                       'network always.',
                       'No, I am only online occasionally to send and '
                       'receive mail.',
                       default=(not options.offline))

    def_realname, def_email = utils.get_email()

    try:
        def_email = def_email.encode(charset, 'replace')
    except UnicodeDecodeError:
        def_email = ''

    try:
        if options.realname:
            realname = options.realname.encode(charset, 'replace')
        else:
            realname = def_realname.encode(charset, 'replace')
    except UnicodeDecodeError:
        realname = ''

    realname = ui.get_string('What real name should be used for sending bug '
                             'reports?', default=realname, force_prompt=True)
    if isinstance(realname, basestring):
        realname = realname.decode(charset, 'replace')
        realname = realname.replace('"', '\\"')

    is_addr_ok = False
    while is_addr_ok != True:
        from_addr = ui.get_string(
            'Which of your email addresses should be used when sending bug '
            'reports? (Note that this address will be visible in the bug tracking '
            'system, so you may want to use a webmail address or another address '
            'with good spam filtering capabilities.)',
            default=(options.email or def_email), force_prompt=True)
        is_addr_ok = utils.check_email_addr(from_addr)
        if not is_addr_ok:
            ewrite('Your email address is not valid; please try another one.\n')
    stupidmode = not ui.yes_no(
        'Do you have a "mail transport agent" (MTA) like Exim, Postfix or '
        'SSMTP configured on this computer to send mail to the Internet?',
        'Yes, I can run /usr/sbin/sendmail without horrible things happening. '
        'If you can send email from this machine without setting an SMTP Host '
        'in your mailer, you should choose this answer.',
        'No, I need to use an SMTP Host or I don\'t know if I have an MTA.',
        (not options.smtphost) if options.smtphost else False)

    if stupidmode:
        opts = []
        if options.smtphost:
            opts += [options.smtphost]
        smtphost = ui.get_string(
            'Please enter the name of your SMTP host.  Usually it\'s called '
            'something like "mail.example.org" or "smtp.example.org". '
            'If you need to use a different port than default, use the '
            '<host>:<port> alternative format.\n\n'
            'Just press ENTER if you don\'t have one or don\'t know, and '
            'so a Debian SMTP host will be used.',
            options=opts, empty_ok=True, force_prompt=True)
        if smtphost:
            stupidmode = False
    else:
        smtphost = ''

    if smtphost:
        smtpuser = ui.get_string(
            ('If you need to use a user name to send email via "%s" on your '
             'computer, please enter that user name.  Just press ENTER if you '
             'don\'t need a user name.' % smtphost), empty_ok=True, force_prompt=True)
    else:
        smtpuser = ''

    if smtphost:
        smtptls = ui.yes_no(
            'Do you want to encrypt the SMTP connection with TLS (only '
            'available if the SMTP host supports it)?', 'Yes', 'No',
            default=False)

    http_proxy = ui.get_string(
       'Please enter the name of your proxy server.  It should only '
       'use this parameter if you are behind a firewall. '
       'The PROXY argument should be  formatted as a valid HTTP URL,'
       ' including (if necessary) a port number;'
       ' for example, http://192.168.1.1:3128/. '
       'Just press ENTER if you don\'t have one or don\'t know.',
       empty_ok=True, force_prompt=True)
    
    if os.path.exists(utils.USERFILE):
        try:
            os.rename(utils.USERFILE, utils.USERFILE+'~')
        except OSError:
            ui.display_failure('Unable to rename %s as %s~\n', utils.USERFILE,
                               utils.USERFILE)

    try:
        fd = os.open(utils.USERFILE, os.O_WRONLY|os.O_TRUNC|os.O_CREAT,
                     0600)
    except OSError, x:
        efail('Unable to save %s; most likely, you do not have a '
                        'home directory.  Please fix this before using '
                        'reportbug again.\n', utils.USERFILE)

    fp = os.fdopen(fd, 'w')
    print >> fp, '# reportbug preferences file'
    print >> fp, '# character encoding: %s' % charset
    print >> fp, '# Version of reportbug this preferences file was written by'
    print >> fp, 'reportbug_version "%s"' % VERSION_NUMBER
    print >> fp, '# default operating mode: one of:',
    print >> fp, ', '.join(utils.MODELIST)
    print >> fp, 'mode %s' % mode
    print >> fp, '# default user interface'
    print >> fp, 'ui %s' % interface
    print >> fp, '# offline setting - comment out to be online'
    if not online:
        print >> fp, 'offline'
    else:
        print >> fp, '#offline'
    print >> fp, '# name and email setting (if non-default)'
    rn = 'realname "%s"'
    em = 'email "%s"'
    email_addy = (from_addr or options.email or def_email)
    email_name = (realname or options.realname or def_realname)

    if email_name != def_realname:
        print >> fp, rn % email_name.encode(charset, 'replace')
    else:
        print >> fp, '# '+(rn % email_name.encode(charset, 'replace'))

    if email_addy != def_email:
        print >> fp, em % email_addy
    else:
        print >> fp, '# '+(em % email_addy)

    uid = os.getuid()
    if uid < MIN_USER_ID:
        print >> fp, '# Suppress user ID check for this user'
        print >> fp, 'no-check-uid'

    if smtphost:
        print >> fp, '# Send all outgoing mail via the following host'
        print >> fp, 'smtphost "%s"' % smtphost
        if smtpuser:
            print >> fp, 'smtpuser "%s"' % smtpuser
            print >> fp, '#smtppasswd "my password here"'
        else:
            print >> fp, '# If you need to enter a user name and password:'
            print >> fp, '#smtpuser "my username here"'
            print >> fp, '#smtppasswd "my password here"'
        if smtptls:
            print >> fp, '# Enable TLS for the SMTP host'
            print >> fp, 'smtptls'
        else:
            print >> fp, '# Enable this option if you need TLS for the SMTP host'
            print >> fp, '#smtptls'

    if http_proxy:
        print >> fp, '# Your proxy server address'
        print >> fp, 'http_proxy "%s"' % http_proxy

    if stupidmode:
        print >> fp, '# Disable fallback mode by commenting out the following:'
        print >> fp, 'no-cc'
        print >> fp, 'header "X-Debbugs-CC: %s"' % email_addy
        print >> fp, 'smtphost reportbug.debian.org'
    else:
        print >> fp, '# If nothing else works, remove the # at the beginning'
        print >> fp, '# of the following three lines:'
        print >> fp, '#no-cc'
        print >> fp, '#header "X-Debbugs-CC: %s"' % email_addy
        print >> fp, '#smtphost reportbug.debian.org'

    print >> fp, '# You can add other settings after this line.  See'
    print >> fp, '# /etc/reportbug.conf for a full listing of options.'
    fp.close()
    ui.final_message('Default preferences file written.  To reconfigure, '
                     're-run reportbug with the "--configure" option.\n')

def verify_option(option, opt, value, parser, *args):
    heading, valid = args
    if value == 'help':
        ewrite('%s:\n %s\n' % (heading, '\n '.join(valid)))
        sys.exit(1)
    elif value in valid:
        setattr(parser.values, option.dest, value)
    else:
        ewrite('Ignored bogus setting for %s: %s\n' % (opt, value))

def verify_append_option(option, opt, value, parser, *args):
    heading, valid = args
    if value == 'help':
        ewrite('%s:\n %s\n' % (heading, '\n '.join(valid)))
        sys.exit(1)
    elif value in valid:
        try:
            getattr(parser.values, option.dest).append(value)
        except AttributeError:
            setattr(parser.values, option.dest, [value])
    else:
        ewrite('Ignored bogus setting for %s: %s\n' % (opt, value))

def main():
    global quietly, ui

    try:
        locale.setlocale(locale.LC_ALL, '')
    except locale.Error, x:
        print >> sys.stderr, '*** Warning:', x

    charset = locale.nl_langinfo(locale.CODESET)
    # It would be nice if there were some canonical character set conversion
    if charset.lower() == 'ansi_x3.4-1968':
        charset = 'us-ascii'

    defaults = dict(sendto="submit", mode="novice", mta="/usr/sbin/sendmail",
                    check_available=True, query_src=True, debconf=True,
                    editor='', offline=False, verify=True, check_uid=True,
                    testmode=False, attachments=[], keyid='', body=None,
                    bodyfile=None, smtptls=False, smtpuser='', smtppasswd='',
                    paranoid=False, mbox_reader_cmd=None)

    # Convention: consider `option.foo' names read-only; they always contain
    # the original value as determined by the cascade of command-line options
    # and configuration files.  When we need to adjust a value, we first say
    # "foo = options.foo" and then refer to just `foo'.
    args = utils.parse_config_files()
    for option, arg in args.items():
        if option in utils.CONFIG_ARGS:
            if isinstance(arg, unicode):
                arg = arg.encode(charset, 'replace')
            defaults[option] = arg
        else:
            sys.stderr.write('Warning: untranslated token "%s"\n' % option)

    parser = optparse.OptionParser(
        usage='%prog [options] <package | filename>', version=VERSION)
    parser.set_defaults(**defaults)
    parser.add_option('-c', '--no-config-files', action="store_true",
                      dest='noconf', help='do not include conffiles in report')
    parser.add_option('-C', '--class', action='callback', type='string',
                      callback=verify_option, dest="klass", metavar='CLASS',
                      callback_args=('Permitted report classes:',
                                     debbugs.CLASSLIST),
                      help='specify report class for GNATS BTSes')
    parser.add_option('-d', '--debug', action='store_true', default=False,
                      dest='debugmode', help='send report only to yourself')
    parser.add_option('--test', action="store_true", default=False,
                      dest="testmode",
                      help="operate in test mode (maintainer use only)")
    parser.add_option('-e', '--editor', dest='editor',
                      help='specify an editor for your report')
    parser.add_option('-f', '--filename', dest='searchfor',
                      help='report the bug against the package containing the specified file')
    parser.add_option('--from-buildd', dest='buildd_format',
                      help='parse information from buildd format: $source_$version')
    parser.add_option('--path', dest='pathonly', action="store_true",
                      default=False, help='only search the path with -f')
    parser.add_option('-g', '--gnupg', '--gpg', action='store_const',
                      dest='sign', const='gpg',
                      help='sign report with GNU Privacy Guard (GnuPG/gpg)')
    parser.add_option('-G', '--gnus', action='store_const', dest='mua',
                      const=utils.MUA['gnus'],
                      help='send the report using Gnus')
    parser.add_option('--pgp', action='store_const', dest='sign',
                      const='pgp',
                      help='sign report with Pretty Good Privacy (PGP)')
    parser.add_option('-K', '--keyid', type="string", dest="keyid",
                      help="key ID to use for PGP/GnuPG signatures")
    parser.add_option('-H', '--header', action='append', dest='headers',
                      help='add a custom RFC2822 header to your report')
    parser.add_option('-P', '--pseudo-header', action='append', dest='pseudos',
                      help='add a custom pseudo-header to your report')
    parser.add_option('--license', action='store_true', default=False,
                      help='show copyright and license information')
    parser.add_option('-m', '--maintonly', action='store_const',
                      dest='sendto', const='maintonly',
                      help='send the report to the maintainer only')
    parser.add_option('-M', '--mutt', action='store_const', dest='mua',
                      const=utils.MUA['mutt'],
                      help='send the report using mutt')
    parser.add_option('--mirror', action='append', help='add a BTS mirror',
                      dest='mirrors')
    parser.add_option('-n', '--mh', '--nmh', action='store_const', dest='mua',
                      help='send the report using mh/nmh',
                      const=utils.MUA['mh'])
    parser.add_option('-N', '--bugnumber', action='store_true',
                      dest='bugnumber',help='specify a bug number to look for')
    parser.add_option('--mua', dest='mua',
                      help='send the report using the specified mail user agent')
    parser.add_option('--mta', dest='mta', help='send the report using the '
                      'specified mail transport agent')
    parser.add_option('--list-cc', action='append', dest='listcc',
                      help='send a copy to the specified address')
    parser.add_option('-p', '--print', action='store_true', dest='printonly',
                      help='output the report to standard output only')
    parser.add_option('--report-quiet', action='store_const', dest='sendto',
                      const='quiet', help='file report without any mail to '
                      'the maintainer or tracking lists')
    parser.add_option('-q', '--quiet', action='store_true', dest='quietly',
                      help='reduce the verbosity of the output', default=False)
    parser.add_option('-s', '--subject', help='the subject for your report')
    parser.add_option('-x', '--no-cc', dest='nocc', action='store_true',
                      help='do not send a copy of the report to yourself')
    parser.add_option('-z', '--no-compress', dest='nocompress',
                      action='store_true', help='do not strip blank lines '
                      'and comments from config files')
    parser.add_option('-o', '--output', dest='outfile', help='output the report'
                      ' to the specified file (both mail headers and body)')
    parser.add_option('-O', '--offline', help='disable all external queries',
                      action='store_true')
    parser.add_option('-i', '--include', action='append',
                      help='include the specified file in the report')
    parser.add_option('-A', '--attach', action='append', dest='attachments',
                      help='attach the specified file to the report')
    parser.add_option('-b', '--no-query-bts', action='store_true',
                      dest='dontquery',help='do not query the BTS for reports')
    parser.add_option('--query-bts', action='store_false', dest='dontquery',
                      help='query the BTS for reports')
    parser.add_option('-T', '--tag', action='callback', dest='tags',
                      callback=verify_append_option,  type='string',
                      callback_args=('Permitted tags:',
                                     sorted(debbugs.get_tags().keys())+['none']),
                      help='add the specified tag to the report')
    parser.add_option('--http_proxy', '--proxy', help='use this proxy for '
                      'HTTP accesses')
    parser.add_option('--email', help='specify originating email address')
    parser.add_option('--realname', help='specify real name for your report')
    parser.add_option('--smtphost', help='specify SMTP server for mailing')
    parser.add_option('--tls', help='use TLS to talk to SMTP servers',
                      dest="smtptls", action='store_true')
    parser.add_option('--source', '--src', dest='source', default=False,
                      help='report the bug against the source package ',
                      action='store_true')
    parser.add_option('--smtpuser', help='username to use for SMTP')
    parser.add_option('--smtppasswd', help='password to use for SMTP')
    parser.add_option('--replyto', '--reply-to', help='specify Reply-To '
                      'address for your report')
    parser.add_option('--query-source', action='store_true', dest='query_src',
                      help='query on source packages, not binary packages')
    parser.add_option('--no-query-source', action='store_false',
                      dest='query_src', help='query on binary packages only')
    parser.add_option('--debconf', action='store_true',
                      help='include debconf settings in your report')
    parser.add_option('--no-debconf', action='store_false', dest='debconf',
                      help='exclude debconf settings from your report')
    parser.add_option('-j', '--justification', help='include justification '
                      'for the severity of your report')
    parser.add_option('-V', '--package-version', dest='pkgversion',
                      help='specify the version number for the package')
    parser.add_option('-u', '--interface', '--ui', action='callback',
                      callback=verify_option, type='string', dest='interface',
                      callback_args=('Valid user interfaces',
                                     AVAILABLE_UIS.keys()),
                      help='choose which user interface to use')
    parser.add_option('-Q', '--query-only', action='store_true',
                      dest='queryonly', help='only query the BTS')
    parser.add_option('-t', '--type', action='callback', dest='type',
                      callback=verify_option, type='string',
                      callback_args=('Valid types of report:',
                                     ('gnats', 'debbugs')),
                      help='choose the type of report to file')
    parser.add_option('-B', '--bts', action='callback', dest='bts',
                      callback=verify_option, type='string',
                      callback_args=('Valid bug tracking systems',
                                     debbugs.SYSTEMS.keys()),
                      help='choose BTS to file the report with')
    parser.add_option('-S', '--severity', action='callback',
                      callback=verify_option, type='string', dest='severity',
                      callback_args=('Valid severities', debbugs.SEVLIST),
                      help='identify the severity of the report')
    parser.add_option('--template', action='store_true',
                      help='output a template report only')
    parser.add_option('--configure', action='store_true',
                      help='reconfigure reportbug for this user')
    parser.add_option('--check-available', action='store_true',
                      help='check for new releases on various sites')
    parser.add_option('--no-check-available', action='store_false',
                      dest='check_available', help='do not check for new '
                      'releases')
    parser.add_option('--mode', action='callback', help='choose the operating '
                      'mode for reportbug', callback=verify_option,
                      type='string', dest='mode',
                      callback_args=('Permitted operating modes',
                                     utils.MODES.keys()))
    parser.add_option('-v', '--verify', action='store_true', help='verify '
                      'integrity of installed package using debsums')
    parser.add_option('--no-verify', action='store_false', dest='verify',
                      help='do not verify package installation')
    parser.add_option('-k', '--kudos', action='store_true', default=False,
                      help='send appreciative email to the maintainer, rather '
                      'than filing a bug report')
    parser.add_option('--body', dest="body", type="string",
                      help="specify the body for the report as a string")
    parser.add_option('--body-file', '--bodyfile', dest="bodyfile",
                      type="string",
                      help="use the specified file as the body of the report")
    parser.add_option('-I', '--no-check-installed', action='store_false',
                      default=True, dest='querydpkg',
                      help='don\'t check whether the package is installed')
    parser.add_option('--check-installed', action='store_true',
                      dest='querydpkg', help='check whether the specified '
                      'package is installed when filing a report (default)')
    parser.add_option('--exit-prompt', action='store_true', dest='exitprompt',
                      help='prompt before exiting')
    parser.add_option('--paranoid', action='store_true', dest='paranoid',
                      help='show contents of message before sending')
    parser.add_option('--no-paranoid', action='store_false', dest='paranoid',
                      help='don\'t show contents of message before sending '
                      '(default)')
    parser.add_option('--no-bug-script', dest="bugscript", default=True,
                      action='store_false',
                      help='don\'t execute the bug script (if present)')
    parser.add_option('--draftpath', dest="draftpath",
                      help='Save the draft in this directory')
    parser.add_option('--timeout', type="int", dest='timeout', default=60,
                      help='Specify the network timeout, in seconds [default: %default]')
    parser.add_option('--no-cc-menu', dest="ccmenu", default=True,
                      action='store_false',
                      help='don\'t show additional CC menu')
    parser.add_option('--no-tags-menu', dest="tagsmenu", default=True,
                      action='store_false',
                      help='don\'t show tags menu')
    parser.add_option('--mbox-reader-cmd', dest='mbox_reader_cmd',
                      help="Specify the program to open the reports mbox.")
    parser.add_option('--max-attachment-size', type="int", dest='max_attachment_size', help="Specify the maximum size in byte for an attachment [default: 10485760].")
    parser.add_option('--latest-first', action='store_true', dest='latest_first', default=False,
                      help='Order bugs to show the latest first')
    parser.add_option('--envelope-from', dest='envelopefrom',
                      help='Specify the Envelope From (Return-path) address used to send the bug report')


    (options, args) = parser.parse_args()

    # Load the interface, *before* the configuration step.
    sys.argv = sys.argv[:1] + list(args)

    # if not set in config file or on cli, then set 10M as default
    if not options.max_attachment_size:
        options.max_attachment_size = 10485760

    # check if attachment files exist, else exiting
    # all are checked, and it doesn't exit at the first missing

    if options.email:
        if not utils.check_email_addr(options.email):
            ewrite('Your email address is not valid; exiting.\n')
            sys.exit(1)

    if options.attachments:
        # needed to support glob
        for attachment in options.attachments:
            # remove each element
            options.attachments.remove(attachment)
            # and replace it with its glob
            options.attachments.extend(glob(attachment))
        any_missing = False
        for attachment in options.attachments:
            if not os.path.exists(os.path.expanduser(attachment)):
                print 'The attachment file %s does not exist.' % attachment
                any_missing = True
            elif check_attachment_size(attachment, options.max_attachment_size):
                print 'The attachment file %s size is bigger than the maximum of %d bytes: reduce ' \
                'its size else the report cannot be sent' % (attachment, options.max_attachment_size)
                any_missing = True
        if any_missing:
            print "The above files can't be attached; exiting"
            sys.exit(1)

    if options.keyid and not options.sign:
        ewrite('Option -K/--keyid requires --gpg or --pgp sign option set, which currently is not; exiting.\n')
        sys.exit(1)

    if options.draftpath:
        options.draftpath = os.path.expanduser(options.draftpath)
        if not os.path.exists(options.draftpath):
            print "The directory % does not exist; exiting." % options.draftpath
            sys.exit(1)

    if options.mua and not options.template:
        if not utils.mua_is_supported(options.mua):
            ewrite("Specified mail user agent is not supported; exiting.\n")
            sys.exit(1)

        if not utils.mua_exists(options.mua):
            ewrite("Selected mail user agent cannot be found; exiting.\n")
            sys.exit(1)

        options.mua = utils.mua_name(options.mua)

    # try to import the specified UI, but only if template
    # is not set (it's useful only in 'text' UI).
    if options.interface and not options.template:
        interface = options.interface

        iface = '%(interface)s_ui' % vars()

        try:
            lib_package = __import__('ui', fromlist=[iface])
            newui = getattr(lib_package, iface)
        except UINotImportable, msg:
            ui.long_message('*** Unable to import %s interface: %s '
                            'Falling back to text interface.\n',
                            interface, msg)
            ewrite('\n')

        if newui.initialize ():
            ui = newui
            submit.ui = ui
        else:
            ui.long_message('*** Unable to initialize %s interface. '
                            'Falling back to text interface.\n',
                            interface)

        # Add INTERFACE as an environment variable to access it from the
        # script gathering the special information for reportbug, when
        # a new bug should be filed against it.
        os.environ['INTERFACE'] = interface


    if not ui.can_input():
        defaults.update({ 'dontquery' : True, 'notatty' : True,
                          'printonly' : True })

    # force to report the bug against the source package if --from-buildd
    if options.buildd_format:
        options.source = True

    iface = UI(options, args)
    if not hasattr(ui, 'run_interface'):
        return iface.user_interface()
    return ui.run_interface(iface.user_interface)

class UI(object):
    def __init__(self, options, args):
        self.options = options
        self.args = args

    def user_interface(self):
        body = ''
        filename = None
        notatty = not ui.ISATTY

        charset = locale.nl_langinfo(locale.CODESET)
        # It would be nice if there were some canonical character set conversion
        if charset.lower() == 'ansi_x3.4-1968':
            charset = 'us-ascii'

        # Allow the UI to know what charset we're using
        ui.charset = charset

        if self.options.configure:
            offer_configuration(self.options)
            sys.exit(0)
        elif self.options.license:
            print COPYRIGHT
            print
            print LICENSE
            sys.exit(0)

        # These option values may get adjusted below, so give them a variable name.
        sendto = self.options.sendto
        check_available = self.options.check_available
        dontquery = self.options.dontquery
        headers = self.options.headers or []
        pseudos = self.options.pseudos or []
        mua = self.options.mua
        pkgversion = self.options.pkgversion
        quietly = self.options.quietly
        severity = self.options.severity
        smtphost = self.options.smtphost
        subject = self.options.subject
        # decode subject (if present) using the current charset
        if subject:
            subject = subject.decode(charset, 'replace')
        bts = self.options.bts or 'debian'
        sysinfo = debbugs.SYSTEMS[bts]
        rtype = self.options.type or sysinfo.get('type')
        attachments = self.options.attachments
        pgp_addr = self.options.keyid
        bugnumber = self.options.bugnumber

        # if user specified a bug number on the command-line, don't query BTS
        if bugnumber:
            dontquery = True

        if self.options.body:
            body = textwrap.fill(self.options.body)
        elif self.options.bodyfile:
            try:
                if check_attachment_size(self.options.bodyfile, self.options.max_attachment_size):
                    print 'Body file %s size bigger than the maximum of %d bytes: ' \
                    'reduce its size else the report cannot be sent'% (self.options.bodyfile, self.options.max_attachment_size)
                    raise Exception
                body = open(self.options.bodyfile).read()
            except:
                efail('Unable to read body from file %s.\n', self.options.bodyfile)

        if body and not body.endswith('\n'):
            body += '\n'

        if self.options.queryonly:
            check_available = False

        if self.options.offline:
            check_available = False
            dontquery = True

        if self.options.tags:
            taglist = self.options.tags
            if 'none' in taglist:
                taglist = []
        else:
            taglist = []

        if self.options.testmode:
            self.options.debugmode = True
            self.options.tags = ['none']
            check_available = False
            dontquery = True
            severity = 'normal'
            subject = 'testing'
            taglist = []

        interactive = True
        if self.options.template:
            check_available = interactive = False
            dontquery = quietly = notatty = True
            mua = smtphost = None
            severity = severity or 'wishlist'
            subject = subject or 'none'
            taglist = taglist or []

        if self.options.outfile or self.options.printonly:
            mua = smtphost = None

        if smtphost and smtphost.lower() in ('master.debian.org', 'bugs.debian.org'):
            ui.long_message('*** Warning: %s is no longer an appropriate smtphost setting for reportbug: it has been superseded by reportbug.debian.org and this one is forced as smtphost; please update your .reportbugrc file.\n', smtphost.lower())
            smtphost = 'reportbug.debian.org'

        if attachments and mua:
            ewrite('Attachments are incompatible with using an MUA.  They will be ignored.\n')
            attachments = []

        if utils.first_run():
            if not self.args and not self.options.searchfor:
                offer_configuration(self.options)
                main()
                sys.exit(0)
            else:
                ewrite('Warning: no reportbug configuration found.  Proceeding in %s mode.\n' % self.options.mode)

        mode = utils.MODELIST.index(self.options.mode)

        # Disable signatures when in printonly or mua mode
        # (since they'll be bogus anyway)
        sign = self.options.sign
        if (self.options.mua or self.options.printonly) and sign:
            sign = ''
            if self.options.mua:
                ewrite('The signature option is ignored when using an MUA.\n')
            elif self.options.printonly:
                ewrite('The signature option is ignored when producing a template.\n')

        uid = os.getuid()
        if uid < MIN_USER_ID:
            if notatty and not uid:
                ewrite("reportbug will not run as root non-interactively.\n")
                sys.exit(1)

            if not uid or self.options.check_uid:
                if not uid:
                    message = "Running 'reportbug' as root is probably insecure!"
                else:
                    message = "Running 'reportbug' as an administrative user "\
                              "is probably not a good idea!"
                message += '  Continue'

                if not ui.yes_no(message, 'Continue with reportbug.', 'Exit.',
                                 False):
                    ewrite("reportbug stopped.\n")
                    sys.exit(1)

        if (utils.first_run() and not self.args and not self.options.searchfor):
            offer_configuration(self.options)
            ewrite('To report a bug, please rerun reportbug.\n')
            sys.exit(0)

        foundfile = None
        package = None
        if not len(self.args) and not self.options.searchfor and not notatty and not self.options.buildd_format:
            package = get_package_name(bts, mode)
        elif self.options.buildd_format:
            # retrieve package name and version from the input string
            package, self.options.pkgversion = self.options.buildd_format.split('_')
            # TODO: fix it when refactoring
            # if not done as of below, it will ask for version when the package
            # is not available on the local system (try a dummy one, like foo_12-3)
            pkgversion = self.options.pkgversion
        elif len(self.args) > 1:
            ewrite("Please report one bug at a time.\n")
            ewrite("[Did you forget to put all switches before the "
                   "package name?]\n")
            sys.exit(1)
        elif self.options.searchfor:
            (foundfile, package) = find_package_for(self.options.searchfor, notatty,
                                                    self.options.pathonly)
        elif len(self.args):
            package = self.args[0]
            if package and package.startswith('/'):
                (foundfile, package) = find_package_for(package, notatty)
            elif package and self.options.source:
                # convert it to the source package if we are reporting for src
                package = utils.get_source_name(package)

        others = debbugs.SYSTEMS[bts].get('otherpkgs')
        if package == 'other' and others:
            package = get_other_package_name(others)

        if package in ('kernel', 'linux-image'):
            ui.long_message(
                "Automatically selecting the package for the running kernel")
            package = utils.get_running_kernel_pkg()

        if not package:
            efail("No package specified or we were unable to find it in the apt"
                  " cache; stopping.\n")

        tfprefix = tempfile_prefix(package)
        if self.options.interface == 'text':
            ewrite('*** Welcome to reportbug.  Use ? for help at prompts. ***\n')
        # we show this for the 2 "textual" UIs
        if self.options.interface in ('text', 'urwid'):
            ewrite('Note: bug reports are publicly archived (including the email address of the submitter).\n')

        try:
            blah = u'hello'.encode(charset)
        except LookupError:
            ui.display_failure(
                'Unable to use specified character set "%s"; you probably need '
                'either cjkcodecs (for users of Asian locales) or iconvcodec '
                'installed.\nFalling back to ASCII encoding.\n', charset)
            charset = 'us-ascii'
        else:
            ewrite("Detected character set: %s\n"
                   "Please change your locale if this is incorrect.\n\n", charset)

        fromaddr = utils.get_user_id(self.options.email, self.options.realname, charset)
        ewrite("Using '%s' as your from address.\n", fromaddr.encode(charset, 'replace'))
        fromaddr = fromaddr.encode('utf-8')
        if self.options.debugmode:
            sendto = fromaddr

        edname = utils.which_editor(self.options.editor)
        baseedname = os.path.basename(edname)
        if baseedname == 'sensible-editor':
            edname = utils.realpath('/usr/bin/editor')

        if not notatty and 'vi' in baseedname and mode < MODE_STANDARD and \
               'EDITOR' not in os.environ:
            if not ui.yes_no('You appear to be using the "vi" editor, which is '
                             'not suited for new users.  You probably want to '
                             'change this setting by using "update-alternatives '
                             '--config editor" as root.  (You can bypass this '
                             'message in the future by using reportbug in '
                             '"standard" mode or higher.) '
                             'Do you want to continue?',
                             'Continue filing this report.',
                             'Stop reportbug to change editors.', False):
                ewrite('Exiting per user request.\n')
                sys.exit(1)

        incfiles = u""
        if self.options.include:
            for f in self.options.include:
                if os.path.exists(f):
                    fp = open(f)
                    incfiles = u'%s\n*** %s\n%s' % (
                               incfiles, f.decode('utf-8', 'replace'),
                               fp.read().decode('utf-8', 'replace'))
                    fp.close()
                else:
                    ewrite("Can't find %s to include!\n", f)
                    sys.exit(1)
            incfiles += '\n'

        pkgavail = maintainer = origin = src_name = state = debsumsoutput = ''
        depends = []
        recommends = []
        suggests = []
        conffiles = []
        reportinfo = None
        isvirtual = (package in sysinfo.get('otherpkgs', {}).keys() and
                     package not in sysinfo.get('nonvirtual', []))
        issource = installed = usedavail = False
        status = None

        if self.options.source:
            issource = True

        exinfo = None
        # If user specified a bug number on the command line
        try:
            if bugnumber:
                reportre = re.compile(r'^#?(\d+)$')
                match = reportre.match(package)
                if match:
                    report = int(match.group(1))
                    exinfo = ui.show_report(report, 'debian', self.options.mirrors,
                                          self.options.http_proxy, self.options.timeout, queryonly=True,
                                          title=VERSION,
                                          archived=False,
                                          mbox_reader_cmd=self.options.mbox_reader_cmd)
                    # When asking to re-display the bugs list, None is returned
                    # given we're in the part of code that's executed when the
                    # user pass a bug number on the cli, so we'll exit
                    if exinfo is None:
                        raise NoReport
                    else:
                        package = exinfo.package or exinfo.source
                else:
                    efail("The report bug number provided seems to not exist.\n")
        except NoBugs:
            efail('No such bug report.\n')
        except NoReport:
            efail('Exiting.\n')

        if not pkgversion and self.options.querydpkg and \
               sysinfo.get('query-dpkg', True) and \
               package not in debbugs.SYSTEMS[bts].get('otherpkgs').keys():
            ewrite("Getting status for %s...\n", package)
            status = utils.get_package_status(package)

            pkgavail, installed = status[1], status[6]
            # Packages that only exist to do weird dependency things
            deppkgs = sysinfo.get('deppkgs')
            if pkgavail and deppkgs:
                if installed and package in deppkgs:
                    depends = status[2]
                    if depends:
                        newdepends = []
                        for x in depends:
                            newdepends.extend(x)
                        depends = newdepends
                        if len(depends) == 1:
                            if mode < MODE_ADVANCED:
                                ewrite('Dependency package "%s" corresponds to '
                                   'actual package "%s".\n', package, depends[0])
                                package = depends[0]
                        else:
                            opts = [(x,
                                     (utils.get_package_status(x)[11] or
                                      'not installed')) for x in depends]
                            if mode >= MODE_ADVANCED:
                                opts += [(package,
                                          status[11]+' (dependency package)')]

                            package = ui.menu('%s is a dependency package.  '
                                              'Which of the following '
                                              'packages is the bug in?' % package,
                                              opts,
                                              'Select one of these packages: ')
                        ewrite("Getting status for %s...\n", package)
                        status = utils.get_package_status(package)
                        pkgavail, installed = status[1], status[6]

            if not pkgavail and not isvirtual:
                # Look for a matching source package
                packages = utils.get_source_package(package)
                if self.options.source:
                    issource = True
                    # package is already ok here, just need the version
                    # so we loop over the bin pkgs looking for one installed
                    # and then get its version
                    if len(packages) > 0:
                        for p in packages:
                            v = utils.get_package_status(p[0])[0]
                            if v:
                                pkgversion = v
                                break
                elif len(packages) > 0:
                    src = utils.get_source_name(package)
                    if len(packages) and not notatty:
                        packages.sort()
                        if src not in [x[0] for x in packages]:
                            packages.append( (src, 'Source package') )

                        if len(packages) > 1:
                            package = ui.menu(
                                'Which of the following packages is the bug in?',
                                packages, empty_ok=True,
                                prompt='Select one of these packages: ')
                        else:
                            package = packages[0][0]

                    if not package:
                        efail("No package specified; stopping.\n")

                    if package != src:
                        ewrite("Getting status for %s...\n", package)
                        status = utils.get_package_status(package)
                        pkgavail, installed = status[1], status[6]
                    elif len(packages) > 1:
                        issource = True
                else:
                    ewrite('No matching source or binary packages.\n')

            if (not installed and not isvirtual and not issource) and not notatty:
                packages = utils.packages_providing(package)
                tmp = pack = None
                if not packages:
                    if ui.yes_no(
                        'A package named "%s" does not appear to be installed; do '
                        'you want to search for a similar-looking filename in '
                        'an installed package' % package,
                        'Look for a file with a similar filename.',
                        'Continue filing with this package name.', True):
                        pkgavail = False
                    else:
                        pack = package
                        packages = [(package, '')]
                        ewrite("Getting available info for %s...\n", package)
                        status = utils.get_package_status(package, avail=True)
                        check_available = False
                        usedavail = True

                if not packages and not pkgavail and not pack:
                    (tmp, pack) = find_package_for(package, notatty)
                    if pack:
                        status = None
                        if not ui.yes_no(
                            "A package named '%s' does not appear to be installed "
                            "on your system; however, '%s' contains a file named "
                            "'%s'.  Do you want to file your report on the "
                            "package reportbug found" % (package, pack, tmp),
                            'Yes, use the package specified.',
                            'No, give up the search.'):
                            efail("Package not installed; stopping.\n")

                if not status and pack:
                    foundfile, package = tmp, pack
                    ewrite("Getting status for %s...\n", package)
                    status = utils.get_package_status(package)
                elif not packages:
                    if not ui.yes_no(
                        'This package does not appear to be installed; continue '
                        'with this report', 'Ignore this problem and continue.',
                        'Exit without filing a report.', False):
                        efail("Package not installed; stopping.\n")
                elif (len(packages) > 1) or (packages[0][0] != package):
                    this_package = [(package, 'Uninstalled/non-existent package')]
                    packages.sort()
                    package = ui.menu('Which of the following installed packages '
                                      'is the bug in?', packages + this_package,
                                      'Select one of these packages: ',
                                      empty_ok=True)
                    if not package:
                        efail("No package specified; stopping.\n")
                    else:
                        ewrite("Getting status for %s...\n", package)
                        status = utils.get_package_status(package)
            elif not pkgavail and not notatty and not isvirtual and not issource:
                if not ui.yes_no(
                    'This package does not appear to exist; continue',
                    'Ignore this problem and continue.',
                    'Exit without filing a report.', False):
                    efail("Package does not exist; stopping.\n")
                    sys.exit(1)

            # we can use status only if it's not a source pkg
            if not issource:
                (pkgversion, pkgavail, depends, recommends, conffiles, maintainer,
                 installed, origin, vendor, reportinfo, priority, desc, src_name,
                 fulldesc, state, suggests, section) = status

        buginfo = '/usr/share/bug/' + package
        bugexec = submitas = submitto = presubj = None
        reportwith = []
        supplemental = []
        if os.path.isfile(buginfo) and os.access(buginfo, os.X_OK):
            bugexec = buginfo
        elif os.path.isdir(buginfo):
            if os.path.isfile(buginfo+'/script') and os.access(buginfo+'/script', os.X_OK):
                bugexec = buginfo+'/script'

            if os.path.isfile(buginfo+'/presubj'):
                presubj = buginfo+'/presubj'

            if os.path.isfile(buginfo+'/control'):
                submitas, submitto, reportwith, supplemental = \
                          utils.parse_bug_control_file(buginfo+'/control')
        elif os.path.isfile('/usr/share/bug/default/'+package) \
             and os.access('/usr/share/bug/default/'+package, os.X_OK):
            bugexec = '/usr/share/bug/default/'+package
        elif os.path.isdir('/usr/share/bug/default/'+package):
            buginfo = '/usr/share/bug/default/'+package
            if os.path.isfile(buginfo+'/script') and os.access(buginfo+'/script',
                                                               os.X_OK):
                bugexec = buginfo+'/script'

            if os.path.isfile(buginfo+'/presubj'):
                presubj = buginfo+'/presubj'

            if os.path.isfile(buginfo+'/control'):
                submitas, submitto, reportwith, supplemental = \
                          utils.parse_bug_control_file(buginfo+'/control')

        if submitas and (submitas not in reportwith):
            reportwith += [submitas]

        if reportwith:
            # Remove current package from report-with list
            reportwith = [x for x in reportwith if x != package]

        if (pkgavail and self.options.verify and os.path.exists('/usr/bin/debsums')
            and not self.options.kudos and state == 'installed'):
            ewrite('Verifying package integrity...\n')
            rc, output = commands.getstatusoutput('/usr/bin/debsums --ignore-permissions -s'+
                                                  commands.mkarg(package))
            debsumsoutput = output

            if rc and not notatty:
                if not ui.yes_no(
                    'There may be a problem with your installation of '+package+
                    ';\nthe following problems were detected by debsums:\n'+
                    output+'\nDo you still want to file a report',
                    'Ignore this problem and continue.  This may be '
                    'appropriate if you have fixed the package manually already.  '
                    'This problem may also result from the use of localepurge.',
                    'Exit without filing a report.', False, nowrap=True):
                    efail("Package integrity check failed; stopping.\n")

        if not pkgversion or usedavail or (not pkgavail and
                                           not self.options.pkgversion and
                                           not self.options.source):
            if not bugnumber and not (isvirtual or notatty):
                pkgversion = ui.get_string('Please enter the version of the '
                                           'package this report applies to '
                                           '(blank OK)', empty_ok=True, force_prompt=True)
        elif (check_available and not (self.options.kudos or notatty or self.options.offline)
              and state == 'installed' and bts == 'debian'):
            arch = utils.get_arch()
            check_more = (mode > MODE_STANDARD)
            if check_more:
                ewrite('Checking for newer versions at madison,'+
                  ' incoming.debian.org and http://ftp-master.debian.org/new.html\n')
            else:
                ewrite('Checking for newer versions at madison...\n')
            (avail, toonew) = checkversions.check_available(
                package, pkgversion, timeout=self.options.timeout,
                check_incoming=check_more, check_newqueue=check_more,
                http_proxy=self.options.http_proxy, arch=arch)
            if toonew:
                if not ui.yes_no(
                    '\nYour version of %s (%s) is newer than that in Debian!\n'
                    'Do you still want to file a report' % (package, pkgversion),
                    'Ignore this problem and continue.  This may be '
                    'appropriate if you know this bug is present in older '
                    'releases of the package, or you\'re running a mixed '
                    'stable/testing installation.',
                    'Exit without filing a report.', False):
                    efail("Newer released version; stopping.\n")

            if avail:
                availtext = ''
                availlist = avail.keys()
                availlist.sort()
                for rel in availlist:
                    availtext += '  %s: %s\n' % (rel, avail[rel])

                if not ui.yes_no(
                    ('\nYour version (%s) of %s appears to be out of date.\nThe '
                    'following newer release(s) are available in the Debian '
                    'archive:\n' % (pkgversion, package))+availtext+
                    'Do you still want to file a report',
                    'Ignore this problem and continue.  This may be '
                    'appropriate if you know this bug is still present in more '
                    'recent releases of the package.',
                    'Exit without filing a report.', False, nowrap=True):
                    efail("Newer released version; stopping.\n")

        bts = DEFAULT_BTS
        if self.options.bts:
            bts = self.options.bts
            ewrite("Will send report to %s (per request).\n",
                   debbugs.SYSTEMS[bts].get('name', bts))
        elif origin:
            if origin.lower() == bts:
                ewrite("Package originates from %s.\n", vendor or origin)
                reportinfo = None
            elif origin.lower() in debbugs.SYSTEMS.keys():
                ewrite("Package originates from %s; overriding your system "
                       "selection.\n", vendor or origin)
                bts = origin.lower()
                sysinfo = debbugs.SYSTEMS[bts]
            elif reportinfo:
                ewrite("Unknown origin %s; will send to %s.\n", origin,
                       reportinfo[1])
                rtype, submitto = reportinfo
            elif submitto:
                ewrite("Unknown origin %s; will send to %s.\n", origin, submitto)
            else:
                ewrite("Unknown origin %s; will send to %s.\n", origin, bts)
        elif reportinfo:
            rtype, submitto = reportinfo
            ewrite("Will use %s protocol talking to %s.\n", rtype, submitto)
            dontquery = True
        else:
            lsbr = commands.getoutput('lsb_release -si 2>/dev/null')
            if lsbr:
                distro = lsbr.strip().lower()
                if distro in debbugs.SYSTEMS:
                    bts = distro
                    ewrite("Will send report to %s (per lsb_release).\n",
                           debbugs.SYSTEMS[bts].get('name', bts))

        if rtype == 'mailto':
            rtype = 'debbugs'
            dontquery = True

        special = False
        if not body and not subject and not notatty:
            res = special_prompts(package, bts, ui, fromaddr,
                                  self.options.timeout,
                                  not self.options.offline and
                                      (check_available or not dontquery),
                                  self.options.http_proxy)
            if res:
                (subject, severity, h, ph, body, query) = res
                headers += h
                pseudos += ph
                if not query:
                    dontquery = True
                special = True



        if not (dontquery or notatty or self.options.kudos):
            pkg, src = package, issource
            if self.options.query_src:
                src = True
                if src_name:
                    pkg = src_name
            try:
                exinfo = ui.handle_bts_query(pkg, bts, self.options.timeout,
                                             self.options.mirrors,
                                             self.options.http_proxy,
                                             source=src,
                                             queryonly=self.options.queryonly,
                                             version=pkgversion,
                                             mbox_reader_cmd=
                                                 self.options.mbox_reader_cmd,
                                             latest_first=self.options.latest_first)
            except UINotImplemented:
                exinfo = None
            except NoNetwork:
                sys.exit(1)
            except NoPackage:
                if not self.options.queryonly and maintainer and ui.yes_no(
                    'There is no record of this package in the bug tracking '
                    'system.\nSend report directly to maintainer',
                    'Send the report to the maintainer (%s).' % maintainer,
                    'Send the report to the BTS anyway.'):
                    rtype = 'debbugs'
                    sendto = maintainer
            except NoBugs:
                ewrite('No bug reports found.\n')
            except NoReport:
                if self.options.queryonly:
                    ewrite('Exiting at user request.\n')
                else:
                    ewrite('Nothing new to report; exiting.\n')
                return

            if self.options.queryonly and not exinfo:
                return

        ccaddr = os.environ.get('MAILCC')
        if self.options.nocc:
            bccaddr = os.environ.get('MAILBCC')
        else:
            bccaddr = os.environ.get('MAILBCC', fromaddr)

        if maintainer:
            mstr = u"Maintainer for %s is '%s'.\n" % (package, maintainer)
            ewrite(mstr.encode(charset, 'replace'))
            if 'qa.debian.org' in maintainer:
                ui.long_message('''\
This package seems to be currently "orphaned"; it also seems you're a
bit interested in this package, since you're reporting a bug against
it, so you might consider adopting it.  Please be aware that your
report may not be resolved for a while, because the package lacks an
active maintainer, but please GO ON and REPORT the bug, if there is
one.

For more details, please see: http://www.debian.org/devel/wnpp/''')

        if self.options.kudos and not self.options.debugmode:
            sendto = '%s@packages.debian.org' % package

        depinfo = ""
        # Grab dependency list, removing version conditions.
        if (depends or recommends or suggests) and not self.options.kudos:
            ewrite("Looking up dependencies of %s...\n", package)
            depinfo = (utils.get_dependency_info(package, depends) +
                       utils.get_dependency_info(package, recommends, "recommends") +
                       utils.get_dependency_info(package, suggests, "suggests"))

        if reportwith and not self.options.kudos:
            # retrieve information for the packages listed in 'report-with' bug
            # control file field
            for extrapackage in reportwith:
                ewrite("Getting status for related package %s...\n", extrapackage)
                extrastatus = utils.get_package_status(extrapackage)
                # depends
                if extrastatus[2]:
                    extradepends = [x for x in extrastatus[2] if package not in x]
                    ewrite("Looking up 'depends' of related package %s...\n", extrapackage)
                    depinfo += utils.get_dependency_info(extrapackage, extradepends)
                # recommends
                if extrastatus[3]:
                    extrarecommends = [x for x in extrastatus[3] if package not in x]
                    ewrite("Looking up 'recommends' of related package %s...\n", extrapackage)
                    depinfo += utils.get_dependency_info(extrapackage, extrarecommends, "recommends")
                # suggests
                if extrastatus[15]:
                    extrasuggests = [x for x in extrastatus[15] if package not in x]
                    ewrite("Looking up 'suggests' of related package %s...\n", extrapackage)
                    depinfo += utils.get_dependency_info(extrapackage, extrasuggests, "suggests")

        if supplemental and not self.options.kudos:
            ewrite("Looking up status of additional packages...\n")
            depinfo += utils.get_dependency_info(
                package, [[x] for x in supplemental], rel='is related to')

        confinfo = []
        if conffiles and not self.options.kudos:
            ewrite("Getting changed configuration files...\n")
            confinfo, changed = utils.get_changed_config_files(
                conffiles, self.options.nocompress)

            if self.options.noconf and changed:
                for f in changed:
                    confinfo[f] = 'changed [not included]'
            elif changed and not notatty:
                while 1:
                    x = ui.select_options(
                        "*** WARNING: The following configuration files have been "
                        "modified:\n"+ "\n".join(changed)+
                        "\nSend modified configuration files", 'Ynd',
                        {'y':'Send your modified configuration files.',
                         'n':"Don't send modified configuration files.",
                         'd':'Display modified configuration files.'})
                    if x == 'n':
                        for f in changed:
                            confinfo[f] = 'changed [not included]'
                        break
                    elif x == 'd':
                        PAGER = os.environ.get('PAGER', '/usr/bin/sensible-pager')
                        ui.system(PAGER+' '+' '.join(changed))
                    else:
                        break

        conftext = u''
        if confinfo:
            conftext = u'\n-- Configuration Files:\n'
            files = confinfo.keys()
            files.sort()
            for f in files:
                conftext = conftext + u'%s %s\n' % (f, confinfo[f])

        if (self.options.debconf and os.path.exists('/usr/bin/debconf-show') and
            not self.options.kudos and installed):
            showpkgs = package
            if reportwith:
                showpkgs += ' ' + ' '.join(reportwith)
            (status, output) = commands.getstatusoutput(
                'DEBCONF_SYSTEMRC=1 DEBCONF_NOWARNINGS=yes '
                '/usr/bin/debconf-show %s' % showpkgs )
            if status:
                conftext += '\n-- debconf-show failed\n'
            elif output:
                output = output.decode('utf-8', 'replace')
                outstr = output.encode(charset, 'replace')
                if (notatty or ui.yes_no(
                    "*** The following debconf settings were detected:\n"
                    +outstr+"\nInclude these settings in your report",
                    'Send your debconf settings.',
                    "Don't send your debconf settings.", nowrap=True)):
                    conftext += u'\n-- debconf information:\n%s\n' % output
                else:
                    conftext += u'\n-- debconf information excluded\n'
            else:
                conftext += u'\n-- no debconf information\n'

        ewrite('\n')
        prompted = False
        if interactive and not (self.options.kudos or exinfo) and presubj:
            ui.display_report(open(presubj).read()+'\n', presubj=True)

        if self.options.kudos:
            subject = subject or ('Thanks for packaging %s!' % package)
        elif exinfo:
            if special:
                body = ''
            prompted = True
            subject_ok = False
            while not subject_ok:
                subject = ui.get_string(
                    'Please provide a subject for your response.', default="Re: %s" % exinfo.subject, force_prompt=True)
                if subject:
                    subject_ok = True
                else:
                    ewrite("Providing a subject is mandatory.\n")

            # Check to make sure the bug still exists to avoid auto-reopens
            if subject and pkgversion:
                if not ui.yes_no('Does this bug still exist in version %s '
                                 'of this package?' % pkgversion,
                                 'Yes, it does.',
                                 'No, it doesn\'t (or I don\'t know).',
                                 default=False):
                    pkgversion = None
        elif not subject and not notatty:
            prompted = True
            subject_ok = False
            while not subject_ok:
                subject = ui.get_string(
                    'Briefly describe the problem (max. 100 characters '
                    'allowed). This will be the bug email subject, so keep the '
                    'summary as concise as possible, for example: "fails to '
                    'send email" or "does not start with -q option specified" '
                    '(enter Ctrl+c to exit reportbug without reporting a bug).',
                    force_prompt=True)

                if subject:
                    subject_ok = True
                else:
                    ewrite("Providing a subject is mandatory.\n")

        if len(subject) > 100 and prompted and mode < MODE_EXPERT:
            subject = ui.get_string(
                'Your description is a bit long; please enter a shorter subject. '
                '(An empty response will retain the existing subject.)',
                empty_ok=True, force_prompt=True) or subject
        if package != 'wnpp' and mode < MODE_EXPERT:
            if foundfile:
                subject = foundfile + ": " + subject
                ewrite("Rewriting subject to '%s'\n", subject)
            elif (not re.match(r"\S+:\s", subject) and
                  not subject.startswith(package)):
                subject = package + ": " + subject
                ewrite("Rewriting subject to '%s'\n", subject)

        listcc = self.options.listcc
        if not listcc:
            listcc = []

        if not listcc and mode > MODE_STANDARD and rtype == 'debbugs' and not self.options.testmode and not self.options.template and self.options.ccmenu:
            listcc += ui.get_multiline('Enter any additional addresses this report should be sent to; press ENTER after each address.')

        if severity and rtype:
            severity = debbugs.convert_severity(severity, rtype)

        klass = self.options.klass
        if not notatty and not (exinfo or self.options.kudos):
            if not severity:
                if rtype == 'gnats':
                    severities = debbugs.SEVERITIES_gnats
                    default = 'non-critical'
                else:
                    severities = debbugs.SEVERITIES
                    if mode < MODE_STANDARD:
                        ewrite("Removing release critical severities, since running in \'%s\' mode.\n" % utils.MODELIST[mode])
                        for sev in ['critical', 'grave', 'serious', 'does-not-build']:
                            del severities[sev]
                    default = 'normal'
                while not severity or severity not in debbugs.SEVLIST:
                    severity = ui.menu("How would you rate the severity of this "
                                       "problem or report?", severities,
                                       'Please select a severity level: ',
                                       default=default, order=debbugs.SEVLIST)

            if rtype == 'gnats':
                # Class of report
                klass = ui.menu("What sort of problem are you reporting?",
                                debbugs.CLASSES, 'Please select a class: ',
                                default='sw-bug', order=debbugs.CLASSLIST)

        severity = severity or 'normal'

        justification = self.options.justification
        if rtype == 'debbugs' and package != 'wnpp' and mode < MODE_EXPERT:
            if severity in ('critical', 'grave'):
                justification = ui.menu(
                    'You are reporting a ' +severity+' bug; which of the '
                    'following criteria does it meet?',
                    debbugs.JUSTIFICATIONS[severity],
                    'Please select the impact of the bug: ', default='unknown')
            elif severity == 'serious':
                justification = ui.get_string(
                    'You are reporting a serious bug; which section of the '
                    'Debian Policy Manual contains the "must" or "required" '
                    'directive that it violates (E.g., "1.2.3")? '
                    'Just type "unknown" if you are not sure (that would '
                    'downgrade severity to normal).', force_prompt=True)
                if re.match('[0-9]+\.[0-9.]+', justification):
                    justification = 'Policy ' + justification
                elif not justification:
                    justification = 'unknown'

            if justification == 'unknown':
                justification = ''
                severity = 'normal'
                ewrite('Severity downgraded to "normal".\n')

        if severity == 'does-not-build':
            if pkgversion and not src_name:
                src_name = package
            if src_name and check_available and not notatty:
                ewrite('Checking buildd.debian.org for past builds of %s...\n',
                       src_name)
                built = checkbuildd.check_built(src_name,
                                                http_proxy=self.options.http_proxy,
                                                timeout=self.options.timeout)

                severity = 'serious'
                justification = 'fails to build from source'
                # special-case only if it was built in the past
                if built:
                    justification += ' (but built successfully in the past)'
            else:
                severity = 'serious'
                justification = 'fails to build from source'
                if not notatty:
                    # special-case only if it was built in the past
                    if ui.yes_no(
                        'Has this package successfully been built for this '
                        'architecture in the past (you can look this up at '
                        'buildd.debian.org)',
                        'Yes, this is a recently-introduced problem.',
                        'No, it has always been this way.'):
                        justification += ' (but built successfully in the past)'

        HOMEDIR = os.environ.get('HOME', '/')

        if (rtype == 'debbugs' and not self.options.tags and
            not (notatty or self.options.kudos or exinfo) and
            package not in ('wnpp', 'ftp.debian.org', 'release.debian.org') and
            mode > MODE_NOVICE and self.options.tagsmenu):
            tags = debbugs.get_tags(severity, mode)

            taglist = ui.select_multiple(
                'Do any of the following apply to this report?', tags,
                'Please select tags: ')

        patch = ('patch' in taglist)

        if justification and 'security' not in taglist and 'security' in \
               justification:
            ewrite('Adding security tag to this report.\n')
            taglist += ['security']

        if taglist:
            tags = ' '.join(taglist)
        else:
            tags = ''

        if 'security' in taglist:
            if ui.yes_no(
                'Are you reporting an undisclosed vulnerability? If so, in order to responsibly disclose the issue, it should not be sent to the public BTS right now, but instead to the private Security Team mailing list.',
                'Yes, it is an undisclosed vulnerability, send this report to the private Security Team mailing list and not to the BTS.',
                'No, it is already a publicly disclosed vulnerability, send this report to the BTS.', False):
                sendto = 'team@security.debian.org'

        # Execute bug script
        if self.options.bugscript and bugexec and not self.options.kudos:
            # add a warning, since it can take a while, 587952
            ewrite("Gathering additional data, this may take a while...\n")
            handler = '/usr/share/reportbug/handle_bugscript'

            # we get the return code of the script, headers and pseudo- set
            # by the script, and last the text output of the script
            (rc, bugscript_hdrs, bugscript_pseudo, text, bugscript_attachments) = \
                 utils.exec_and_parse_bugscript(handler, bugexec)

            if rc and not notatty:
                if not ui.yes_no(
                    'The package bug script %s exited with an error status (return '
                    'code = %s). Do you still want to file a report?' % (bugexec,rc),
                    'Ignore this problem and continue.',
                    'Exit without filing a report.', False, nowrap=True):
                    efail("Package bug script failed; stopping.\n")

            # add bugscript headers only if present
            if bugscript_hdrs:
                headers.extend(bugscript_hdrs.split('\n'))
            if bugscript_pseudo:
                pseudos.append(bugscript_pseudo.strip())
            # add attachments only if no MUA is used, using attachments with a
            # MUA is not yet supported by reportbug.
            if bugscript_attachments and not mua:
                attachments += bugscript_attachments
            addinfo = None
            if not self.options.noconf:
                addinfo = u"\n-- Package-specific info:\n"+text

            if addinfo and incfiles:
                incfiles = addinfo + u"\n" + incfiles
            elif addinfo:
                incfiles = addinfo

        if bts == 'debian' and 'security' in taglist and sendto != 'team@security.debian.org':
            ewrite('Will send a CC of this report to the Debian Security and Testing Security Team.\n')
            listcc += ['Debian Security Team <team@security.debian.org>']
            listcc += ['Debian Testing Security Team <secure-testing-team@lists.alioth.debian.org>']

        # Prepare bug report
        if self.options.kudos:
            message = u'\n\n'
            if not mua:
                SIGFILE = os.path.join(HOMEDIR, '.signature')
                try:
                    message = u"\n\n-- \n"+open(SIGFILE).read().decode('utf-8', 'replace')
                except IOError:
                    pass
        else:
            p = submitas or package
            # multiarch: remove arch qualifier only if we're not reporting
            # against the src package
            if not p.startswith('src:'):
                p = p.split(':')[0]
            message = utils.generate_blank_report(
                p, pkgversion, severity, justification,
                depinfo, conftext, foundfile, incfiles, bts, exinfo, rtype,
                klass, subject, tags, body, mode, pseudos, debsumsoutput,
                issource=issource)

        # Substitute server email address
        if submitto and '@' not in sendto:
            if '@' in submitto:
                sendto = submitto
            else:
                if exinfo:
                    if sendto != 'submit':
                        sendto = '%d-%s' % (exinfo.bug_num, sendto)
                    else:
                        sendto = str(exinfo.bug_num)

                sendto = sendto+'@'+submitto
        elif '@' not in sendto:
            if exinfo:
                if sendto != 'submit':
                    sendto = '%d-%s' % (exinfo.bug_num, sendto)
                else:
                    sendto = str(exinfo.bug_num)

            try:
                sendto = sysinfo['email'] % sendto
            except TypeError:
                sendto = sysinfo['email']

            sendto = rfc822.dump_address_pair((sysinfo['name']+
                                               ' Bug Tracking System', sendto))

        mailing = not (mua or self.options.printonly or self.options.template)
        message = u"Subject: %s\n%s" % (subject, message)
        justsave = False

        if mailing:
            fh, filename = TempFile(prefix=tfprefix, dir=self.options.draftpath)
            fh.write(message.encode(charset, 'replace'))
            fh.close()
            oldmua = mua or self.options.mua
            if not self.options.body and not self.options.bodyfile:
                message, haspatch, justsave = handle_editing(
                    filename, message, self.options, sendto, attachments,
                    package, severity, mode, charset=charset, tags=tags)
                if haspatch:
                    patch = True

            if not oldmua and self.options.mua:
                mua = self.options.mua
            if mua:
                mailing = False
            elif not sendto:
                print message,
                cleanup_temp_file(filename)
                return

            cleanup_temp_file(filename)

            if not mua and patch and not attachments and not notatty:
                while True:
                    patchfile = ui.get_filename(
                        'What is the filename of the patch (if none, or you have '
                        'already included it, just press ENTER)?',
                        force_prompt=True)
                    if patchfile:
                        attachfile = os.path.expanduser(patchfile)
                        # loop over the glob of 'attachfile', we support glob now
                        for attachf in glob(attachfile):
                            if os.path.exists(attachfile):
                                attachments.append(attachfile)
                            else:
                                ewrite('%s not found!', attachfile)
                    else:
                        break
        if CCS:
            listcc += CCS
        if listcc:
            headers.append('X-Debbugs-CC: '+', '.join(listcc))

        # Pass both headers and pseudo-headers (passed on command-line, f.e.)
        body, headers, pseudoheaders = utils.cleanup_msg(message, headers, pseudos, rtype)

        if sign:
            ewrite('Passing message to %s for signature...\n', sign)
            oldbody = body
            body = submit.sign_message(body, fromaddr, package, pgp_addr, sign, self.options.draftpath)
            if not body:
                ewrite('Signature failed; sending message unsigned.\n')
                body = oldbody

        if pseudoheaders:
            body = '\n'.join(pseudoheaders)+'\n\n'+body

        # Strip the body of useless whitespace at the end, then put a final
        # newline in the message.  See #234963.
        body = body.rstrip('\n')+'\n'

        if justsave:
            fh, outputfile = TempFile(prefix=tfprefix,
                                      dir=self.options.draftpath)
            fh.close()
            mua = mailing = False
            # fake sending the report, it actually saves it in a tempfile
            # but with all the email headers and stuff
            submit.send_report(
                body, attachments, mua, fromaddr, sendto, ccaddr, bccaddr,
                headers, package, charset, mailing, sysinfo, rtype, exinfo,
                outfile=self.options.outfile or outputfile, mta=None,
                smtphost=None)
        else:
            submit.send_report(
                body, attachments, mua, fromaddr, sendto, ccaddr, bccaddr,
                headers, package, charset, mailing, sysinfo, rtype, exinfo,
                self.options.replyto, self.options.printonly,
                self.options.template, self.options.outfile, self.options.mta,
                self.options.kudos, self.options.smtptls, smtphost,
                self.options.smtpuser, self.options.smtppasswd,
                self.options.paranoid, self.options.draftpath,
                self.options.envelopefrom)

        if self.options.exitprompt:
            ui.get_string('Please press ENTER to exit reportbug: ')
        return

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        ewrite("\nreportbug: exiting due to user interrupt.\n")
    except debbugs.Error, x:
        ewrite('error accessing BTS: %s\n' % x)
