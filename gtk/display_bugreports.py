#/usr/bin/python

import debianbts
from gi.repository import Gtk

class BugReportListBoxRow(Gtk.ListBoxRow):
    def __init__(self, report):
        Gtk.ListBoxRow.__init__(self)
        self.report = report

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
        self.add(hbox)

        header = Gtk.Label("Bug #: %s" % self.report.bug_num, xalign=0)
        header.set_markup("<b>Bug #: %s</b>" % self.report.bug_num)
        desc = Gtk.Label(self.report.subject, xalign=0)
        desc.set_line_wrap(True)

        textBox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        textBox.pack_start(header, True, True, 0)
        textBox.pack_start(desc, True, True, 0)

        # set listener
        self.btnViewBug = Gtk.Button('View')
        self.btnViewBug.connect("clicked", self.callbacks)

        hbox.pack_start(textBox, True, True, 0)
        hbox.pack_start(self.btnViewBug, False, False, 0)

    def callbacks(self, obj):
        if obj == self.btnViewBug:
            print("To view bug # %s" % self.report.bug_num)
            bugWin = BugReportDetails(self.report)
            bugWin.show_all()
        

class BugReportDetails(Gtk.Window):
    '''
    Details of a single bug report
    '''

    def __init__(self, report):
        Gtk.Window.__init__(self, title=("%s: bug # %s" % (report.package, report.bug_num)))
        self.report = report
        self.set_border_width(10)
        self.set_size_request(500, 400)
        
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_border_width(0)
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.show()
        outerBox = Gtk.Box(spacing=0)
        outerBox.pack_start(scrolled_window, True, True, 0)
        self.add(outerBox)
        
        innerBox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        scrolled_window.add_with_viewport(innerBox)

        # TODO:
        # now we only show subject and severity, could add more here
        l_sub = Gtk.Label("", xalign=0)
        l_sub.set_markup("<b>Title:</b> %s" % self.report.subject)
        l_severity = Gtk.Label("", xalign=0)
        l_severity.set_markup("<b>Severity:</b> %s" % self.report.severity)

        innerBox.add(l_sub)
        innerBox.add(l_severity)

        logs = debianbts.get_bug_log(self.report.bug_num)
        for l in logs:
            l_msgnum = Gtk.Label("", xalign=0)
            l_msgnum.set_markup("<b>Message #:</b> %s" % l['msg_num'])

            l_msgbody = Gtk.Label(l['body'], xalign=0)
            l_msgbody.set_line_wrap(True)

            innerBox.add(l_msgnum)
            innerBox.add(l_msgbody)


class BugReportListWindow(Gtk.Window):

    def __init__(self, pkg):
        Gtk.Window.__init__(self, title=("Bug Reports of %s" % pkg))
        self.set_border_width(10)
        self.set_size_request(600, 400)
        self.pkg = pkg
        
        # create a new scrolled window.
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_border_width(0)
        # Gtk.PolicyType.AUTOMATIC wll automatically decide whether we need
        # scrollbars. The first one is the horizontal scrollbar, the second, the
        # vertical.
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.show()

        # create a box for displaying the scrolled window
        # and add this box into the main window
        hbox = Gtk.Box(spacing=0)
        hbox.pack_start(scrolled_window, True, True, 0)
        self.add(hbox)


        # put a listbox into the scrolled window
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled_window.add_with_viewport(listbox)

        self.addRows(listbox)

    def addRows(self, listbox):
        bugNumList = debianbts.get_bugs('package', self.pkg)
        reportList = debianbts.get_status(bugNumList)
        
        for r in reportList:
            listbox.add(BugReportListBoxRow(r))


if __name__ == '__main__':
    import platform
    print(platform.python_version())
    import sys
    win = BugReportListWindow(sys.argv[1])
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    Gtk.main()
