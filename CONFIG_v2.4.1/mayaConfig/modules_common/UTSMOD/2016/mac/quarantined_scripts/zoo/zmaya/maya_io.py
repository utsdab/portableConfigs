
import logging

from maya import cmds, OpenMaya

import path
import simple_p4
import context_utils

from studio import maya_scene

import maya_p4

logger = logging.getLogger(__name__)

_SCENE_IO_CALLBACKS_ENABLED = True

def callbacksEnabled():
    return _SCENE_IO_CALLBACKS_ENABLED

def setCallbacksEnabled(state):
    global _SCENE_IO_CALLBACKS_ENABLED
    _SCENE_IO_CALLBACKS_ENABLED = bool(state)

class SuspendCallbacksContext(context_utils.nestableContextFactory()):
    '''
    suspends the callbacks defined below within this context
    '''
    def enter(self):
        initialState = callbacksEnabled()
        setCallbacksEnabled(False)

        return initialState

    def exit(self):
        setCallbacksEnabled(self._enterState)

# decorator to suspend scene open callbacks
d_suspendCallbacks = SuspendCallbacksContext()

class PostCallbackList(list):
    def register(self, enabledCb, disabledCb=None):
        for anEnabledCb, aDisabledCb in self:
            if enabledCb is anEnabledCb:
                logger.warning("The callback %s has already been registered" % enabledCb)
                return

        self.append((enabledCb, disabledCb))

    def execute(self, data):
        enabled = callbacksEnabled()
        for enabledCb, disabledCb in self:
            cb = enabledCb if enabled else disabledCb

            # either callback can be None (I guess both of them can be too)
            if cb is None:
                continue

            try:
                cbReturnCode = cb()
            except:
                logger.error("The post callback %s failed" % cb, exc_info=1)

class PreCallbackList(PostCallbackList):
    def __init__(self, filenameGetter):
        PostCallbackList.__init__(self)
        self._filenameGetter = filenameGetter

    def execute(self, returnCode, data):
        OpenMaya.MScriptUtil.setBool(returnCode, True)
        enabled = callbacksEnabled()

        filepath = self._filenameGetter()
        for enabledCb, disabledCb in self:
            cb = enabledCb if enabled else disabledCb

            # either callback can be None (I guess both of them can be too)
            if cb is None:
                continue

            try:
                cbReturnCode = cb(filepath)

                # if the callback returns False, then tell maya to abort the operation
                if not cbReturnCode:
                    OpenMaya.MScriptUtil.setBool(returnCode, False)
                    return

            except:
                logger.error("The scene io callback %s failed" % cb, exc_info=1)

cbPreOpens = PreCallbackList(OpenMaya.MFileIO.beforeOpenFilename)
cbPreSaves = PreCallbackList(OpenMaya.MFileIO.beforeSaveFilename)
cbPreExport = PreCallbackList(OpenMaya.MFileIO.beforeExportFilename)
cbPostExport = PostCallbackList()
cbPostOpens = PostCallbackList()

def setupCallbacks():
    MSceneMsg = OpenMaya.MSceneMessage

    MSceneMsg.addCheckCallback(MSceneMsg.kBeforeOpenCheck, cbPreOpens.execute)
    MSceneMsg.addCheckCallback(MSceneMsg.kBeforeSaveCheck, cbPreSaves.execute)
    MSceneMsg.addCheckCallback(MSceneMsg.kBeforeExportCheck, cbPreExport.execute)
    MSceneMsg.addCallback(MSceneMsg.kAfterExport, cbPostExport.execute)
    MSceneMsg.addCallback(MSceneMsg.kAfterOpen, cbPostOpens.execute)

class SceneVisitor(object):
    '''
    iterator class to visit a given iterable of files, optionally opening each one when visited
    '''
    def __init__(self, filepaths, visit=True, progress=False, **progressWindowKwargs):
        self._filepaths = filepaths
        self._visit = True
        self._progress = progress
        self._progressWindowKwargs = progressWindowKwargs

        # set some sensible defaults
        if progress:
            pwKwargs = progressWindowKwargs
            pwKwargs.setdefault('title', pwKwargs.pop('t', 'Visiting scene files...'))

            # try to set the max number of files
            try:
                numFiles = len(filepaths)

            # filepaths may be a generator object though, so determining this may not be possible.  If not, set the
            # value to large
            except TypeError:
                numFiles = 999999

            pwKwargs.setdefault('maxValue', pwKwargs.pop('max', numFiles))

    def __iter__(self):
        visited = set()
        if self._progress:
            cmds.progressWindow(isInterruptable=True, **self._progressWindowKwargs)

        try:
            with SuspendCallbacksContext():
                for filepath in self._filepaths:
                    filepath = path.Path(filepath)
                    if filepath in visited:
                        continue

                    # add so we don't re-visit
                    visited.add(filepath)

                    # update progress window if we have one
                    if self._progress:
                        cmds.progressWindow(e=True, step=1, status='visiting %s' % filepath)

                        # if its been cancelled, bail
                        if cmds.progressWindow(q=True, isCancelled=True):
                            return

                    # visit the file
                    if self._visit:
                        if filepath.exists():
                            cmds.file(filepath, o=True, f=True, prompt=False)
                        else:
                            logger.warning("The file '%s' does not exist in disk - skipping!" % filepath)

                    yield filepath

        finally:
            cmds.progressWindow(endProgress=True)

def checkReferencesForNewRevisions(filepath):
    '''
    checks to see if any references used by the scene are out of date
    '''

    # first get a list of all files referenced by this one
    scene = maya_scene.MayaScene(filepath)
    allReferencedFiles = list(scene.iterReferencedFilepaths(True))
    stats = simple_p4.fstat(allReferencedFiles)

    outdatedReferences = []
    for stat in stats:
        head = stat.get(simple_p4.StatNames.HEAD_REV)
        if head is not None:
            have = stat.get(simple_p4.StatNames.HAVE_REV)
            if have != head:
                refFilepath = stat[simple_p4.StatNames.CLIENT_FILE]
                outdatedReferences.append(refFilepath)

    if outdatedReferences:
        BUTTONS = YES, NO = 'Yes', 'No'
        ret = cmds.confirmDialog(t='Referenced files out of date!',
                                 m='The following files referenced by this scene have newer\n' \
                                 'revisions in p4.  Do you want to sync them?\n\n%s' % '\n'.join(outdatedReferences),
                                 b=BUTTONS,
                                 db=YES)

        if ret == YES:
            simple_p4.sync(outdatedReferences)

    return True

#end
