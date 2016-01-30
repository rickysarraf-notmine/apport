#!/usr/bin/python3

from gi.repository import Gtk
from gi.repository import Gdk

import sys
import reportbug

class ReportBugWindow(Gtk.Window):

    def __init__(self, pkg):
        Gtk.Window.__init__(self, title=('Reporting bug for %s' % pkg))
        self.set_border_width(10)
        self.set_size_request(600, 400)
        self.pkg = pkg

        self.connect('delete-event', Gtk.main_quit)

        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.panel)

        self.collectInfoUI()
        self.createTextView()
        self.submitOrNot()

    def submitOrNot(self):
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.submit = Gtk.Button(label='Submit')
        hbox.pack_start(self.submit, False, True, 0)

        self.panel.pack_start(hbox, False, False, 0)


    def createTextView(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_border_width(0)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.show()

        textView = Gtk.TextView()
        textView.set_border_width(2)
        self.textBuffer = textView.get_buffer()
        self.textBuffer.set_text('this his a textview')
    
        scrolled.add_with_viewport(textView)

        self.panel.pack_start(scrolled, True, True, 0)

    def collectInfoUI(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        #
        # Bug report subject
        #
        hintSubject = Gtk.Label("Briefly describe the bug:") 
        hintSubject.set_alignment(0, 0.5)
        self.subject = Gtk.Entry()

        #
        # Severity and criteria
        #
        hintSeverity = Gtk.Label('Rate the severity(?) of the problem:')
        hintSeverity.set_alignment(0, 0.5)
        self.severity = Gtk.ComboBoxText() 
        severities = ['Important', 'Serious', 'Grave', 'Critical']
        for s in severities:
            self.severity.append_text(s)
        self.severity.set_entry_text_column(0)

        # TODO:
        # Critera options vary according to severity
        hintCriterion = Gtk.Label('Criteria(?):')
        hintCriterion.set_alignment(0, 0.5)
        self.criterion = Gtk.ComboBoxText()
        criteria = ['1', '2']
        for c in criteria:
            self.criterion.append_text(c)
        self.criterion.set_entry_text_column(0)

        t = Gtk.Table(2, 2, True)
        t.set_col_spacing(0, 10)
        t.attach(hintSeverity, 0, 1, 0, 1)
        t.attach(self.severity, 0, 1, 1, 2)
        t.attach(hintCriterion, 1, 2, 0, 1)
        t.attach(self.criterion, 1, 2, 1, 2)

        vbox.pack_start(hintSubject, False, True, 0)
        vbox.pack_start(self.subject, False, True, 0)
        vbox.pack_start(t, False, True, 0)
        
        self.panel.pack_start(vbox, False, True, 0)


def main(pkg):
    win = ReportBugWindow(pkg)
    win.show_all()
    Gtk.main()


if __name__ == '__main__':
    pkg = sys.argv[1]
    main(pkg)
