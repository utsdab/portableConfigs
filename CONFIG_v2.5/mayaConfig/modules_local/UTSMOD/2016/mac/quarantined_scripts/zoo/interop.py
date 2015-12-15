
import os
import time
import socket
import logging
import subprocess

import cPickle as pickle

try:
    from win32com import client
except ImportError:
    client = None

import path
import simple_p4

PORT = 4444

MAX_RECV = 2**16

logger = logging.getLogger(__name__)

class NoApplicationError(Exception): pass
class CommandError(Exception): pass

def getWMIProcess(processName):
    if client is None:
        return None

    wmi = client.GetObject('winmgmts:')
    processes = wmi.InstancesOf('Win32_Process')

    for process in processes:
        name = process.Properties_('Name').Value
        if name == processName:
            return process

    return None

def getPid(processName):
    process = getPid(processName)
    if process:
        return process.Properties_('ProcessId').Value

    return None

def isMayaOpen():
    return getWMIProcess('maya.exe') is not None

def openMaya(*args):
    mayaFilepath = path.Path(os.environ.get('ProgramFiles(x86)')) / 'Autodesk/Maya2012/bin/maya.exe'
    if not mayaFilepath.exists():
        raise NoApplicationError("Couldn't find the application %s" % mayaFilepath)

    proc = subprocess.Popen(args, executable=mayaFilepath, cwd=mayaFilepath.up())
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            sock.connect(('127.0.0.1', PORT))
            break
        except socket.error:
            time.sleep(0.1)

    return proc.pid

def executeInMaya(cmdStr, isPython=True, openIfNotFound=True, modulesToImport=()):
    if not isMayaOpen():
        if openIfNotFound:
            openMaya()
        else:
            raise Exception("Maya isn't open!")

    cmdPickle = pickle.dumps((isPython, modulesToImport, cmdStr))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(('127.0.0.1', PORT))
        logger.info('Waiting for maya...')
        sock.send(cmdPickle)
        returnPickle = sock.recv(MAX_RECV)

        success, returnVal = pickle.loads(returnPickle)

        if success:
            return returnVal

        else:
            logger.error("Command raised an exception on the remote: \"%s\"" % returnVal)
            raise CommandError(returnVal)

    finally:
        sock.close()

def executeMELInMaya(cmdStr, openIfNotFound=True):
    return executeInMaya(cmdStr, False, openIfNotFound)

def executePythonInMaya(cmdStr, openIfNotFound=True, modulesToImport=()):
    return executeInMaya(cmdStr, True, openIfNotFound, modulesToImport)

def openInMaya(filepath):
    filepath = path.Path(filepath)
    recentArg = 'mayaAscii' if filepath.hasExtension('ma') else 'mayaBinary'
    if not isMayaOpen():
        openMaya()
        executeMELInMaya('file -f -o "{0}"; addRecentFile "{0}" {1};'.format(filepath, recentArg))
    else:
        executeMELInMaya('saveChanges("file -f -o \\"{0}\\""); addRecentFile "{0}" {1};'.format(filepath, recentArg))

class Maya(object):
    class Router(object):
        def __get__(self, instance, owner):
            self.cmdToks = []

            return self

        def __getattr__(self, attr):
            if not attr.startswith('__'):
                self.cmdToks.append(attr)
                return self

        def __call__(self, *args, **kwargs):
            modulesToImport = []

            # special case for "cmds", it should already exist as a top level module
            if self.cmdToks[0] != 'cmds':
                modulesToImport.append(self.cmdToks[0])

            cmdStr = '.'.join(self.cmdToks)
            cmdStr += '('

            argToks = []
            if args:
                argToks.append(','.join(repr(a) for a in args))

            if kwargs:
                argToks.append(','.join('%s=%r' % item for item in kwargs.iteritems()))

            cmdStr += ','.join(argToks)
            cmdStr += ')'

            return executePythonInMaya(cmdStr, True, modulesToImport)

    python = Router()

    def disableCallbacks(self):
        self.python.maya_io.setCallbacksEnabled(False)

    def open(self, filepath, **kw):
        self.python.cmds.file(filepath, o=True, f=True, prompt=False, **kw)

    def save(self):
        filepath = self.python.cmds.file(q=True, sn=True)
        with simple_p4.EditAddContext(filepath):
            self.python.cmds.file(save=True, f=True)

    def __enter__(self):
        self.openOnEntry = isMayaOpen()
        if not self.openOnEntry:
            openMaya()

        self.callbacksEnabledOnEntry = self.python.maya_io.callbacksEnabled()

        return self

    def __exit__(self, *exc_info):

        # make sure to re-enable callbacks if they were enabled on entry...
        if self.callbacksEnabledOnEntry:
            self.python.maya_io.setCallbacksEnabled(True)

        ## if maya wasn't open when the context began, quit
        #if not self.openOnEntry:
            #self.python.cmds.quit(force=True)

#end
