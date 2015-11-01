
import sys
import cgitb
import logging
import threading
import SocketServer

import cPickle as pickle

from maya import cmds, utils, mel

import interop

logger = logging.getLogger(__name__)

CMD_SERVER = None
CMD_SERVER_THREAD = None

def pythonCmdExecutor(cmdStr, modulesToImport=()):
    globalDict = {'cmds': cmds}
    for moduleName in modulesToImport:
        globalDict[moduleName] = __import__(moduleName)

    return eval(cmdStr, globalDict)

def melCmdExecutor(cmdStr, _=()):
    return mel.eval(cmdStr)

class MayaCmdsHandler(object):
    def __init__(self, request, address, server):
        isPython, modulesToImport, cmdStr = pickle.loads(request.recv(1024).strip())
        cmdExecutor = pythonCmdExecutor if isPython else melCmdExecutor
        success = True
        try:
            retValue = utils.executeInMainThreadWithResult(cmdExecutor, cmdStr, modulesToImport)

        # if an exception was raised, capture it and send it back to the client
        except:
            success = False
            retValue = cgitb.text(sys.exc_info())
            logger.error("Failed to execute the remote command: \"%s\"" % cmdStr, exc_info=1)

        response = success, retValue
        request.sendall(pickle.dumps(response))

def start():
    global CMD_SERVER, CMD_SERVER_THREAD
    try:
        server = SocketServer.TCPServer(('localhost', interop.PORT), MayaCmdsHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
    except:
        return

    CMD_SERVER = server
    CMD_SERVER_THREAD = server_thread

#end
