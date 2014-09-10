/*
***************************************************************************
*                  Copyright (C) Ritesh Raj Sarraf <rrs@debian.org>       *
*                                                                         *
* This program is free software. You may use, modify, and redistribute it *
* under the terms of the GNU General Public License as published   	  *
* by the Free Software Foundation, either version 3 or (at your option)   *
* any later version. This program is distributed without any warranty.    *
***************************************************************************
*/

#include <sys/inotify.h>
#include <syslog.h>
#include <stdlib.h>
#include <limits.h>
#include <unistd.h>
#include <string.h>


#define BUF_LEN (10 * (sizeof(struct inotify_event) + NAME_MAX + 1))
#define PROG "apport-bug "
#define CRASH_PATH "/var/crash/"

int checkFileExtn(const char* extn, const char* CRASH_EXTN)
{
	#define CRASH_EXTN ".crash"
	size_t extnLength;
	size_t apportLength;

	extnLength = strlen(extn);
	apportLength = strlen(CRASH_EXTN);
	// syslog(LOG_NOTICE,"extnLength is %d and apportLength is %d\n", extnLength, apportLength);

	if(apportLength > extnLength) return 1;

	/* Check if it is a .crash file */
	// syslog(LOG_NOTICE,"strcmp length is %s\n", &extn[extnLength - apportLength]);
	return (strcmp(&extn[extnLength - apportLength], CRASH_EXTN)) == 0;
}

static void trapCrashFile(struct inotify_event *i)
{

    char cmdStr[1024] = { NULL };
    strcat(cmdStr, PROG);
    strcat(cmdStr, CRASH_PATH);
    strcat(cmdStr, i->name);
    // syslog(LOG_DEBUG, "cmdStr is %s at event %d\n", cmdStr, i->mask);

    if (checkFileExtn(i->name, CRASH_EXTN)) {
	    // syslog(LOG_DEBUG, "File %s has extension %s\n", i->name, CRASH_EXTN);
	    if (i->mask & IN_CREATE) {
		    system(cmdStr);
		    syslog(LOG_NOTICE, "cmdStr is %s at event %d\n", cmdStr, i->mask);
	    }
    } /* else {
	    syslog(LOG_DEBUG, "File %s does not have extension %s\n", i->name, CRASH_EXTN);
    } */

    /*
    if (i->mask & IN_CREATE)        system(cmdStr);
    if (i->mask & IN_ATTRIB)        printf("IN_ATTRIB ");
    if (i->mask & IN_MODIFY)        printf("IN_MODIFY ");
    */

}


int main()
{
    int inotifyFd, wd;
    char buf[BUF_LEN] __attribute__ ((aligned(4)));
    ssize_t numRead;
    char *p;
    struct inotify_event *event;

    daemon(0,0);

    /* Open a connection to the syslog server */
    openlog("apport-notifyd",LOG_NOWAIT|LOG_PID,LOG_USER); 

    /* Sends a message to the syslog daemon */
    syslog(LOG_NOTICE, "Successfully started daemon\n"); 

    inotifyFd = inotify_init();                 /* Create inotify instance */
    if (inotifyFd == -1)
	syslog(LOG_NOTICE, "inotify_init");

    // wd = inotify_add_watch(inotifyFd, CRASH_PATH, IN_CREATE|IN_ATTRIB|IN_MODIFY); /* We only care when a crash file gets created */
    // wd = inotify_add_watch(inotifyFd, CRASH_PATH, IN_CLOSE_WRITE); /* We only care when a crash file gets created */
    wd = inotify_add_watch(inotifyFd, CRASH_PATH, IN_CREATE); // We only care when a crash file gets created

    if (wd == -1)	syslog(LOG_NOTICE, "inotify_add_watch");

    for (;;) {                                  /* Read events forever */
        numRead = read(inotifyFd, buf, BUF_LEN);
        if (numRead == 0)
            syslog(LOG_NOTICE, "read() from inotify fd returned 0!");

        if (numRead == -1)
            syslog(LOG_DEBUG, "read");

        syslog(LOG_DEBUG, "Read %ld bytes from inotify fd\n", (long) numRead);

        /* Process all of the events in buffer returned by read() */

        for (p = buf; p < buf + numRead; ) {
            event = (struct inotify_event *) p;
            trapCrashFile(event);
	    syslog(LOG_NOTICE, "Got invoked\n");

            p += sizeof(struct inotify_event) + event->len + 1;
        }
    }
    closelog();
}
