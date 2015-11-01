
import logging
import functools

from PySide.QtGui import *
import shiboken

from maya import cmds
from maya import OpenMaya
from maya import OpenMayaUI

from .. import ui_utils
from .. import str_utils
from . import maya_decorators

logger = logging.getLogger(__name__)

def printCallstack():
    import inspect
    outerFrameInfos = inspect.getouterframes(inspect.currentframe())[1:]
    for n, frameData in enumerate(outerFrameInfos):
        print '-' * n + '>', inspect.getframeinfo(frameData[0])[2]

def iterChildren(widget):
    """
    Yields all descendant widgets depth-first
    """
    for child in widget.children():
        yield child

        for grandchild in iterChildren(child):
            yield grandchild

def killScriptJobs(self):
    """
    deletes any script jobs that were setup - this emulates maya's ability to
    parent scriptjob's to UI and makes job scoping nice and simple
    """
    if hasattr(self, '_scriptJobIds'):
        logger.info('\tKilling scriptJob ids: %s' % self._scriptJobIds)
        for jobId in self._scriptJobIds:
            jobId.kill()

        del self._scriptJobIds

    if hasattr(self, '_apiCBs'):
        logger.info('\tKilling %d API callbacks' % len(self._apiCBs))
        for cbId in self._apiCBs:
            cbId.kill()

        del self._apiCBs

    # Recurse for children
    for child in self.children():
        if isinstance(child, QWidget):
            killScriptJobs(child)

class CommonMixin(ui_utils.CommonMixin):
    """
    Mixin class to add shared functionality to Qt subclasses

    Provides functionality to emulate maya ability to parent script jobs to pieces of native UI
    """

    @property
    def logger(self):
        try:
            return self._logger
        except AttributeError:
            try:
                thisModuleName = type(self).__module__
            except AttributeError:
                thisModuleName = 'UNNAMED'

            self._logger = logging.getLogger(thisModuleName)

        return self._logger

    def _createScriptJob(self, **kw):

        # ugh...  this is kinda nasty, but such is the nature of mixin classes.  This way
        # seemed less nasty than defining a constructor
        if not hasattr(self, '_scriptJobIds'):
            self._scriptJobIds = []

        jobId = maya_decorators.JobId(cmds.scriptJob(**kw))
        self._scriptJobIds.append(jobId)

        return jobId

    def _appendApiCB(self, cbId):

        # ugh...  this is kinda nasty, but such is the nature of mixin classes.  This way
        # seemed less nasty than defining a constructor
        if not hasattr(self, '_apiCBs'):
            self._apiCBs = []

        if not isinstance(cbId, maya_decorators.ApiCb):
            cbId = maya_decorators.ApiCb(cbId)

        self._apiCBs.append(cbId)

    def _safeCallback(self, cb):
        def cbWrapper():
            try:
                return cb()

            except RuntimeError, x:
                # in this case the widget has almost certainly been deleted, so ignore the error and
                # kill any scriptjobs on the instance
                if 'already deleted' in str(x):
                    self.killScriptJobs()

                # but it may also be a runtime error for a failed call to a mel command...
                else:
                    self.logger.error('Runtime error in callback', exc_info=1)

            # otherwise log the error
            except:
                self.logger.error('Scriptjob callback failed', exc_info=1)

        cbWrapper.__name__ = cb.__name__
        cbWrapper.__doc__ = cb.__doc__

        return cbWrapper

    def _safeApiCallback(self, cb):
        def cbWrapper(*a):
            try:
                return cb(*a)
            except:
                self.logger.error('API callback failed', exc_info=1)

        cbWrapper.__name__ = cb.__name__
        cbWrapper.__doc__ = cb.__doc__

        return cbWrapper

    def setCB(self, eventName, cb, compressUndo=True, **kw):
        cb = self._safeCallback(cb)
        return self._createScriptJob(compressUndo=compressUndo, event=(eventName, cb), **kw)

    def setSelectionChangeCB(self, cb, **kw):
        """
        creates a scriptJob to monitor selection, and fires the given callback when the selection changes
        the scriptJob is parented to this widget so it dies when the UI is closed

        NOTE: selection callbacks don't take any args
        """
        return self.setCB('SelectionChanged', cb, **kw)

    def setSceneChangeCB(self, cb, **kw):
        """
        creates a scriptJob which will fire when the currently open scene changes
        the scriptJob is parented to this widget so it dies when the UI is closed

        NOTE: scene change callbacks don't take any args
        """
        return self.setCB('SceneOpened', cb, **kw)

    def setAttributeChangeCB(self, attrpath, cb, compressUndo=True, allChildren=False, disregardIndex=False, **kw):
        """
        creates a scriptjob which will fire when the given attribute gets changed
        """
        cb = self._safeCallback(cb)
        return self._createScriptJob(compressUndo=compressUndo, attributeChange=(attrpath, cb), allChildren=allChildren, disregardIndex=disregardIndex, **kw)

    def setRenameCB(self, cb, **kw):
        """
        creates a scriptJob which will fire when the current time changes
        the scriptJob is parented to this widget so it dies when the UI is closed

        NOTE: time change callbacks don't take any args
        """
        return self.setCB('NameChanged', cb, **kw)

    def setUndoCB(self, cb, **kw):
        """
        define a callback that gets triggered when an undo event is issued
        """
        return self.setCB('Undo', cb, **kw)

    def setPlaybackRangeCB(self, cb, **kw):
        # playbackRangeSliderChanged - fired when playbackOptions(ast/aet) change
        # playbackRangeChanged - fired when playbackOptions(min/max) change
        return self.setCB('playbackRangeChanged', cb, **kw)

    def setTimeChangeCB(self, cb):
        """
        creates a scriptJob which will fire when the current time changes
        the scriptJob is parented to this widget so it dies when the UI is closed

        NOTE: the callback must take the form
        def cb(time, clientData): ...

        the clientData as far as I can tell is always None
        """
        cb = self._safeApiCallback(cb)
        cbId = OpenMaya.MDGMessage.addTimeChangeCallback(cb)
        self._appendApiCB(cbId)

    def setNodeDeleteCB(self, cb):
        """
        define a callback that is executed when a node is deleted

        NOTE: the callback must take the form
        def cb(node, clientData): ...

        the clientData as far as I can tell is always None
        """
        cb = self._safeApiCallback(cb)
        cbId = OpenMaya.MDGMessage.addNodeRemovedCallback(cb)
        self._appendApiCB(cbId)

    def killScriptJobs(self):
        killScriptJobs(self)

class MayaQWidget(QWidget, CommonMixin):

    @classmethod
    def Show(cls):
        return showWidgetInDock(cls)

    def close(self):
        topMayaQWidget = self
        for p in ui_utils.iterParents(self):
            if isinstance(p, MayaQWidget):
                topMayaQWidget = p

        windowName = _getWidgetName(type(p))
        if cmds.window(windowName, q=True, exists=True):
            cmds.deleteUI(windowName)
        else:

            # Ok so we have the top most maya qwidget, now grab its parent and close
            topMayaQWidget.parentWidget().close()

def getMayaWindow():

    # Check to see if we've previously stored it
    try:
        return getMayaWindow._TOP
    except AttributeError: pass

    ptr = OpenMayaUI.MQtUtil.mainWindow()
    mainWindowWidget = shiboken.wrapInstance(long(ptr), QWidget)

    # The maya window widget is static for the session, so store it as a sneaky global
    getMayaWindow._TOP = mainWindowWidget

    return mainWindowWidget

def createSeparator():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)

    return line

def _getWidgetName(cls):
    widgetName = cls.__name__
    if cmds.control(widgetName, exists=True):
        cmds.deleteUI(widgetName)

    return widgetName

def showWidgetInDock(widgetCls, *a, **kw):
    widgetName = _getWidgetName(widgetCls)
    title = str_utils.camelCaseToNice(widgetName)

    c = cmds.window()
    cc = cmds.formLayout(parent=c)
    dock = cmds.dockControl(
        widgetName,
        content=c, area='left', floating=True, label=title)

    # Find the QWidget for the dock control
    ptr = OpenMayaUI.MQtUtil.findControl(dock)
    self = shiboken.wrapInstance(long(ptr), QDockWidget)
    widget = widgetCls(*a, **kw)

    # Schedule a command to kill script jobs when the UI is "hidden"
    def kill(_):
        from maya import cmds
        if not cmds.control(dock, q=True, visible=True):
            killScriptJobs(widget)

    cmds.dockControl(dock, e=True, visibleChangeCommand=kill)

    def callDockChanged():
        if hasattr(widget, 'dockChanged'):
            widget.dockChanged()

        for child in iterChildren(widget):
            if hasattr(child, 'dockChanged'):
                child.dockChanged()

    # Hook up the dockChanged callback and call it
    cmds.dockControl(dock, e=True, floatChangeCommand=callDockChanged)
    callDockChanged()

    # Now instantiate and set the actual widget we want hosted
    self.setWidget(widget)

    # Delete the dummy control we created initially
    cmds.deleteUI(c)

    return self

def showWidget(widgetCls, *a, **kw):
    return showWidgetInDock(widgetCls, *a, **kw)

#end
