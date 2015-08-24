#!/usr/bin/env python3

from gi.repository import Gtk
import sys
import btsconn

class SimpleBugReport():
    def __init__(self, r):
        self.subject = r['subject']
        self.severity = r['severity']
        self.bug_num = r['bug_num']
        self.package = r['package']


class Page():
    def __init__(self):
        self.widget = self.create_widget()

#
# Introduction
#
class IntroPage(Page):
    def __init__(self, title):
        Page.__init__(self)
        self.title = title

    def __init__(self):
        Page.__init__(self)
        self.title = "Introduction"

    def create_widget(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        label = Gtk.Label(label="Welcome to use apport to submit bug reports!")
        label.set_line_wrap(True)
        box.pack_start(label, True, True, 0)

        return box


#
# Show existing reports in Debian BTS
#
class ExistingReportsPage(Page):
    def __init__(self):
        Page.__init__(self)
        self.title = "Existing Reports"

    def create_widget(self):
        mainbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Page overview label
        label = Gtk.Label(label="xx reports found in Debian BTS")
        label.set_line_wrap(True)
        mainbox.pack_start(label, False, False, 5)

        # Filter label and entry
        filterBox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        textFilter = Gtk.Entry()
        labelFilter = Gtk.Label(label="Filter:")
        filterBox.pack_start(labelFilter, False, False, 5)
        filterBox.pack_start(textFilter, True, True, 0)
        mainbox.pack_start(filterBox, False, False, 5) 

        # Show existing reports
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_border_width(0)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.show()
        mainbox.pack_start(scrolled, True, True, 0)

        # create widget inside scrolled window
        treeView = self.build_treeview()
        scrolled.add_with_viewport(treeView)  
        
        return mainbox

    def build_treeview(self):
        '''
        TODO: implement filter
        http://python-gtk-3-tutorial.readthedocs.org/en/latest/treeview.html#filtering
        '''
        reportStore = Gtk.ListStore(str, str, str)
        for r in self.fetch_reports():
            reportStore.append(r)

        treeview = Gtk.TreeView(reportStore)
        for i, colTitle in enumerate(['ID', 'Severity', 'Title']):
            render = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(colTitle, render, text=i)
            treeview.append_column(col)
        
        return treeview

    def fetch_reports(self):
        reports = []
        reportList = btsconn.get_status('vim')
        for r in reportList:
            reports.append([str(r['bug_num']), r['severity'], r['subject']])
        return reports

#
# Collect user's description
#
class DescPage(Page):
    def __init__(self):
        Page.__init__(self)
        self.title = "Description"

    def create_widget(self):
        mainbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        label = Gtk.Label(label=
                "Briefly describe the problem (This will be the\n"
                "bug email subject, so keep the summary as concise\n"
                "as possible, for example: \"fails to send email\"\n"
                "or \"does not start with -q option specified\").")
        label.set_line_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        box.pack_start(label, False, True, 5)

        self.descTextView = Gtk.Entry()
        box.pack_start(self.descTextView, False, True, 0) 

        mainbox.pack_start(box, True, True, 0)

        return mainbox

    def get_desc(self):
        return self.descTextView.get_text()


#
# Let the user rate severity
#
class SeverityPage(Page):
    def __init__(self):
        Page.__init__(self)
        self.title = "Severity"

    def get_severity(self):
        return self.severity

    def create_widget(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        def radiobutton_toggled(radiobutton):
            if radiobutton.get_active():
                l = radiobutton.get_label()
                if l.startswith('Critical'):
                    self.severity = 'Critical'
                elif l.startswith('Serious'):
                    self.severity = 'Serious'
                elif l.startswith('Important'):
                    self.severity = 'Important'
                elif l.startswith('Normal'):
                    self.severity = 'Normal'

        label = Gtk.Label(label="Rate the severity of this problem")
        label.set_line_wrap(True)
        box.pack_start(label, True, True, 0)

        #
        # add radio buttons
        #
        criticalRadioBtn = Gtk.RadioButton(label="Critical. Makes unrelated applications on the system break")
        criticalRadioBtn.connect("toggled", radiobutton_toggled)
        box.pack_start(criticalRadioBtn, True, True, 0)

        seriousRadioBtn = Gtk.RadioButton(label="Serious. Makes the package in question unusable by most or all users", group=criticalRadioBtn)
        seriousRadioBtn.connect("toggled", radiobutton_toggled)
        box.pack_start(seriousRadioBtn, True, True, 0)

        importantRadioBtn = Gtk.RadioButton(label="Important. Has a major effect on the usability of a package", group=criticalRadioBtn)
        importantRadioBtn.connect("toggled", radiobutton_toggled)
        box.pack_start(importantRadioBtn, True, True, 0)

        normalRadioBtn = Gtk.RadioButton(label="Normal. Does not undermine the usability of the whole package", group=criticalRadioBtn)
        normalRadioBtn.connect("toggled", radiobutton_toggled)
        box.pack_start(normalRadioBtn, True, True, 0)

        # set default severity
        self.severity = 'Critical'

        return box

#
# Draft email
#
class DraftPage(Page):
    '''
    display email editing text view
    attach both apport and reportbug system info
    '''
    def __init__(self):
        Page.__init__(self)
        self.title = "Draft"

    def create_widget(self):
        mainbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        subjectBox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        label = Gtk.Label(label="Subject:")
        subject = Gtk.Entry()
        subjectBox.pack_start(label, False, False, 5)
        subjectBox.pack_start(subject, True, True, 0)

        mainbox.pack_start(subjectBox, False, True, 5)

        self.editor = self.create_editor()
        mainbox.pack_start(self.editor, True, True, 0)
        
        expander = Gtk.Expander(label="System information")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_border_width(0)
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.show()
        expander.add(scrolled) 

        mainbox.pack_start(expander, False, True, 0)

        return mainbox

    def create_editor(self):
        scrollable = Gtk.ScrolledWindow()
        scrollable.set_border_width(0)
        scrollable.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrollable.show()

        textview = Gtk.TextView()
        textview.set_border_width(2)
        textview.get_buffer().set_text('this is a textview')

        scrollable.add_with_viewport(textview)

        return scrollable

#
# Reportbug Assistant
#
class ReportbugAssistant(Gtk.Assistant):
    def __init__(self):
        Gtk.Assistant.__init__(self)
        self.connect("cancel", self.cancel_button_clicked)
        self.connect("close", self.close_button_clicked)
        self.connect("apply", self.apply_button_clicked)

        self.set_size_request(700, 500)

    def add_intro_page(self, page):
        self.introPage = page
        self.add_page(page, Gtk.AssistantPageType.INTRO)

    def add_existing_reports_page(self, page):
        # self.existingReportsPage = page
        self.add_page(page, Gtk.AssistantPageType.CONTENT)

    def add_desc_page(self, page):
        self.descPage = page
        self.add_page(page, Gtk.AssistantPageType.CONTENT)

    def add_severity_page(self, page):
        self.severityPage = page
        self.add_page(page, Gtk.AssistantPageType.CONTENT)

    def add_page(self, page, ptype):
        self.append_page(page.widget)
        self.set_page_type(page.widget, ptype)
        self.set_page_title(page.widget, page.title)
        self.set_page_complete(page.widget, True)

    def apply_button_clicked(self, asst):
        print("The 'Apply' button has been clicked")
        print(self.descPage.get_desc())
        print(self.severityPage.get_severity())
    
    def close_button_clicked(self, asst):
        print("The 'Close' button has been clicked")
        Gtk.main_quit()
    
    def cancel_button_clicked(self, asst):
        print("The 'Cancel' button has been clicked")
        Gtk.main_quit()


def main():
    assistant = ReportbugAssistant()
    
    def get_buttons_hbox(assistant):
        # temporarily add a widget to the action area and get its parent
        label = Gtk.Label('')
        assistant.add_action_widget(label)
        hbox = label.get_parent()
        hbox.remove(label)
        return hbox

    # modify the default ``Apply'' button to ``Send'' 
    for child in get_buttons_hbox(assistant).get_children():
        label = child.get_label()
        if label == '_Apply':
            child.set_label('Send')

    introPage = IntroPage()
    assistant.add_intro_page(introPage)

    reportsPage = ExistingReportsPage()
    assistant.add_existing_reports_page(reportsPage)

    descPage = DescPage()
    assistant.add_desc_page(descPage)

    severityPage = SeverityPage()
    assistant.add_severity_page(severityPage)

    draftPage = DraftPage()
    assistant.add_page(draftPage, Gtk.AssistantPageType.CONFIRM)

    assistant.show_all()
    Gtk.main()


if __name__ == '__main__':
    main()
