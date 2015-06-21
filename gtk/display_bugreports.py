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
        self.set_size_request(500, 400)
        logs = debianbts.get_bug_log(self.report.bug_num)
        for l in logs:
            print("msg # %s" % l['msg_num'])
            print(l['body'])


class BugReportListWindow(Gtk.Window):

    def __init__(self, pkg):
        Gtk.Window.__init__(self, title=("Bug Reports of %s" % pkg))
        self.set_border_width(10)
        self.pkg = pkg
        
        # add ListBox to panel
        hbox = Gtk.Box(spacing=6)
        self.add(hbox)
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        hbox.pack_start(listbox, True, True, 0)

        self.addRows(listbox)

    def addRows(self, listbox):
        bugNumList = debianbts.get_bugs('package', self.pkg)
        reportList = debianbts.get_status(bugNumList)
        
        for r in reportList:
            listbox.add(BugReportListBoxRow(r))


if __name__ == '__main__':
    win = BugReportListWindow('apport-gtk')
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    Gtk.main()
