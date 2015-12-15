import logging

from maya import cmds, mel

from .. import context_utils

logger = logging.getLogger(__name__)
VERSION = int(mel.eval('getApplicationVersionAsFloat'))

class JobId(int):
    def kill(self):
        from maya import cmds

        idx = int(self)
        cmds.evalDeferred("if cmds.scriptJob(exists=%(idx)d): cmds.scriptJob(kill=%(idx)d, force=True)" % dict(idx=idx))

    def __del__(self):
        logger.debug('Killing scriptjob %d because the JobId object has been deleted' % self)
        self.kill()

class ApiCb(object):
    def __init__(self, cbId):
        self.cbId = cbId

    def kill(self):
        from maya import OpenMaya

        try:
            OpenMaya.MMessage.removeCallback(self.cbId)
        except:
            pass

    def __del__(self):
        self.kill()

class NoAutokeyContext(context_utils.nestableContextFactory()):
    def enter(self):
        initialState = cmds.autoKeyframe(q=True, state=True)
        cmds.autoKeyframe(state=False)

        return initialState

    def exit(self):
        if self._enterState:
            cmds.autoKeyframe(state=True)

class NoUndoContext(context_utils.nestableContextFactory()):
    def enter(self):
        initialState = cmds.undoInfo(q=True, state=True)
        cmds.undoInfo(stateWithoutFlush=False)

        return initialState

    def exit(self):
        if self._enterState:
            cmds.undoInfo(stateWithoutFlush=True)

class MaintainSelectionContext(context_utils.nestableContextFactory()):
    def enter(self):
        return cmds.ls(sl=True) or []

    def exit(self):
        if cmds.ls(sl=True) != self._enterState:
            initialState = [o for o in self._enterState if cmds.objExists(o)]
            if initialState:
                cmds.select(initialState)
            else:
                cmds.select(clear=True)

class RestoreTimeContext(context_utils.nestableContextFactory()):
    def enter(self):
        return cmds.currentTime(q=True)

    def exit(self):
        cmds.currentTime(self._enterState, e=True)

class WaitCursorContext(context_utils.nestableContextFactory()):
    def enter(self):
        cmds.waitCursor(state=True)

    def exit(self):
        cmds.waitCursor(state=False)

class UndoBlockContext(context_utils.nestableContextFactory()):
    def enter(self):
        cmds.undoInfo(openChunk=True)

    def exit(self):
        cmds.undoInfo(closeChunk=True)

d_showWaitCursor = WaitCursorContext()

d_noAutoKey = NoAutokeyContext()

d_restoreTime = RestoreTimeContext()

d_noUndo = NoUndoContext()

d_undoBlock = UndoBlockContext()

def d_disableViews(f):
    '''
    disables all viewports before, and re-enables them after
    '''

    def wrapped(*args, **kwargs):
        modelPanels = cmds.getPanel(vis=True)
        emptySelConn = cmds.selectionConnection()

        for panel in modelPanels:
            if cmds.getPanel(to=panel) == 'modelPanel':
                cmds.isolateSelect(panel, state=True)
                cmds.modelEditor(panel, e=True, mlc=emptySelConn)

        try:
            return f(*args, **kwargs)
        finally:
            for panel in modelPanels:
                if cmds.getPanel(to=panel) == 'modelPanel':
                    cmds.isolateSelect(panel, state=False)

            cmds.deleteUI(emptySelConn)

    wrapped.__name__ = f.__name__
    wrapped.__doc__ = f.__doc__

    return wrapped

def d_progress(**dec_kwargs):
    '''
    deals with progress window...  any kwargs given to the decorator on init are passed to the progressWindow init method
    '''

    def decorator(f):
        def wrapped(*args, **kwargs):
            try:
                cmds.progressWindow(**dec_kwargs)
            except:
                logger.error('error init-ing the progressWindow', exc_info=1)

            try:
                return f(*args, **kwargs)
            finally:
                cmds.progressWindow(ep=True)

        wrapped.__name__ = f.__name__
        wrapped.__doc__ = f.__doc__

        return wrapped

    return decorator

d_maintainSceneSelection = MaintainSelectionContext()

# end
