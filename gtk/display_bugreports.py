#/usr/bin/python

import debianbts
from gi.repository import Gtk

class BugReportListBoxRow(Gtk.ListBoxRow):
    def __init__(self, report):
        Gtk.ListBoxRow.__init__(self)
        self.report = report

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
        self.add(hbox)

        textBox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header = Gtk.Label("Bug #: %s" % self.report.bug_num, xalign=0)
        # TODO: highlight header
        desc = Gtk.Label(self.report.subject, xalign=0)
        textBox.pack_start(header, True, True, 0)
        textBox.pack_start(desc, True, True, 0)

        btnViewBug = Gtk.Button('View')
        hbox.pack_start(textBox, True, True, 0)
        hbox.pack_start(btnViewBug, True, True, 0)


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
    win = BugReportListWindow('python-debianbts')
    win.connect("delete-event", Gtk.main_quit)
    win.show_all()
    Gtk.main()
