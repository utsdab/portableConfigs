
import sys
import time
import logging

logger = logging.getLogger(__name__)

# time in seconds to delay before exiting - giving a chance to the user to see the output
FINISH_DELAY = 3

try:
    import wingdbstub
except ImportError: pass

def sendEmail():
    server = smtplib.SMTP('localhost')
    server.set_debuglevel(1)
    server.sendmail(fromaddr, toaddrs, msg)
    server.quit()

def handleException(*exc_info):
    logger.error("An unhandled error occurred!", exc_info=exc_info)
    print "Press enter to dismiss, or just close the window"
    userInputStr = raw_input().strip().lower()

def setupConsole(installExceptionHandler=True):
    if installExceptionHandler:
        sys.excepthook = handleException

    stdoutHandler = logging.StreamHandler(sys.stdout)
    rootLogger = logging.getLogger()
    rootLogger.addHandler(stdoutHandler)
    rootLogger.setLevel(logging.INFO)

#end
