
import logging
import functools
import subprocess

from maya import cmds, mel, OpenMaya

import path
import simple_p4
import studio.shader

import maya_io
import scene_dependencies

logger = logging.getLogger(__name__)

P4_GLOBAL_MENU = 'TB_perforceMainMenu'
NEVER_ASK_TO_EDIT = 'tb_neverAskToEditPriorToOpen'

@simple_p4.d_withP4Connection
def preOpenP4CB(filepath):
    stat = simple_p4.fstat(filepath)[0]

    # if the file isn't in the client view, nothing to do, just open the scene
    if not stat[simple_p4.StatNames.IN_WORKSPACE]:
        return True

    # if the file already has an action, nothing to do, just open the scene
    if stat.get(simple_p4.StatNames.ACTION) is not None:
        return True

    # check to see if head and have revisions match
    headRev = stat.get(simple_p4.StatNames.HEAD_REV, 0)
    haveRev = stat.get(simple_p4.StatNames.HAVE_REV, 0)

    outOfDate = haveRev != headRev
    if outOfDate:
        BUTS = YES, NO, CANCEL = 'Yes', 'No', 'Cancel'
        ret = cmds.confirmDialog(t="File is out of date",
                                 m="A newer version the file exists:\n%s\n\nDo you want to sync?" % filepath,
                                 b=BUTS, db=YES, cb=CANCEL, ds=CANCEL)

        # cancel the open if the user hits cancel
        if ret == CANCEL:
            return False

        # otherwise sync the scene file
        if ret == YES:
            ret = simple_p4.sync(filepath)[0]
            if ret.get(simple_p4.StatNames.ACTION) == 'failed':

                # if the file failed to sync, abort the file read and log an error.  The user can re-open and explicitly
                # choose "No" from the sync dialog
                logger.error('Failed to sync %s - p4 return value was: %s' % (filepath, ret))
                return False

    # check to see if someone else has the file open and warn appropriately
    otherEdits = stat.get(simple_p4.StatNames.OTHER_OPEN, [])
    if otherEdits:
        BUTS = YES, NO, CANCEL = 'Yes', 'No', 'Cancel'
        ret = cmds.confirmDialog(t="File opened elsewhere!",
                                 m="This file is opened for edit by:\n%s\n\nYou should talk to them "
                                 "before doing any work.\n\nDo you still want to open for edit?" % '\n'.join(otherEdits),
                                 b=BUTS, db=NO, cb=CANCEL)

        # cancel the open if the user hits cancel
        if ret == CANCEL:
            return False

        if ret == YES:
            ret = simple_p4.edit(filepath)[0]
            if ret.get(simple_p4.StatNames.ACTION) == 'failed':

                # if the file has failed to open for edit, log an error and abort scene load. The user can re-open and
                # explicitly choose "No" when asked to open for edit
                logger.error("Failed to edit %s - p4 return value was: %s" % (filepath, ret))
                return False

    # if not, ask the user if they want to open for edit before opening
    else:

        # check to see whether the user actually wants to be asked about opening for edit
        askToEdit = True
        if cmds.optionVar(ex=NEVER_ASK_TO_EDIT):
            askToEdit = not cmds.optionVar(q=NEVER_ASK_TO_EDIT)

        # if they've specified tb_neverAskToEditPriorToOpen, don't ask
        if askToEdit:
            BUTS = YES, NO, NEVER = 'Yes', 'No', 'Never'
            ret = cmds.confirmDialog(t="Edit this file in perforce?",
                                     m="Do you want to open the file for edit?",
                                     b=BUTS, db=NO, cb=NO)

            if ret == YES:
                ret = simple_p4.edit(filepath)[0]
                if ret.get(simple_p4.StatNames.ACTION) == 'failed':

                    # if the file has failed to open for edit, log an error and abort scene load. The user can re-open and
                    # explicitly choose "No" when asked to open for edit
                    logger.error("Failed to edit %s - p4 return value was: %s" % (filepath, ret))
                    return False

            elif ret == NEVER:
                cmds.optionVar(iv=(NEVER_ASK_TO_EDIT, 1))

    return True

@simple_p4.d_withP4Connection
def preSaveP4CB(filepath):
    stat = simple_p4.fstat(filepath)[0]

    # if the file isn't in the client view, nothing to do, just open the scene
    if not stat[simple_p4.StatNames.IN_WORKSPACE]:
        return True

    # if the file is already open for something, nothing to do
    if stat.get(simple_p4.StatNames.ACTION):
        return True

    # check to see if someone else has the file open and warn appropriately
    otherEdits = stat.get('otherOpen', [])
    if otherEdits:
        BUTS = YES, NO, CANCEL = 'Yes', 'No', 'Cancel'
        ret = cmds.confirmDialog(t="File opened elsewhere!",
                                 m="This file is opened for edit by:\n\n%s\n\nYou should talk to these people "
                                 "before checking anything in.\n\nDo you still want to open for edit?" % '\n'.join(otherEdits),
                                 b=BUTS, db=NO, cb=CANCEL)

        # cancel the open if the user hits cancel
        if ret == CANCEL:
            return False

        if ret == YES:
            ret = simple_p4.edit(filepath)[0]
            if ret.get(simple_p4.StatNames.ACTION) == 'failed':

                # if the file has failed to open for edit, log an error and abort scene load. The user can re-open and
                # explicitly choose "No" when asked to open for edit
                logger.error("Failed to edit %s - p4 return value was: %s" % (filepath, ret))
                return False

    # if the file isn't in the client view, nothing to do, just open the scene
    if stat[simple_p4.StatNames.IN_DEPOT]:
        ret = simple_p4.edit(filepath)[0]
    else:
        ret = simple_p4.add(filepath)[0]

    return True

def save():
    filepath = cmds.file(q=True, sn=True)
    with simple_p4.EditAddContext(filepath) as p4Ctx:
        openedBy = p4Ctx.stat.get(simple_p4.StatNames.OTHER_OPEN, [])
        if openedBy:
            logger.warning("File %s is open for edit by %s - aborting save!" % (filepath, openedBy))
        else:
            cmds.file(save=True, f=True)

def createP4Menu():

    # this awkward idiom queries the MEL global that stores the maya UI top level window name
    # needed for parenting menus to
    mainWindow = mel.eval('string $x=$gMainWindow;')
    if not cmds.menu(P4_GLOBAL_MENU, q=True, ex=True):
        cmds.menu(P4_GLOBAL_MENU, p=mainWindow, l='Perforce', tearOff=True, pmc=buildP4Menu)

def buildP4Menu(*a):
    cmds.menu(P4_GLOBAL_MENU, e=True, dai=True)

    cmds.setParent(P4_GLOBAL_MENU, m=True)
    thisScene = cmds.file(q=True, sn=True)

    if thisScene:

        # now grab a p4 stat on the file
        stat = simple_p4.fstat(thisScene)[0]

        # is the file in the user's clientspec?
        if not stat.get(simple_p4.StatNames.IN_WORKSPACE):
            cmds.menuItem(l='Scene not under clientspec!',
                          ann="This scene doesn't fall within your p4 workspace (AKA clientspec)")
            return

        # check to see if others have the file open
        others = stat.get(simple_p4.StatNames.OTHER_OPEN, [])
        if others:
            for other in others:
                cmds.menuItem(l='Also opened by: %s' % other,
                              ann="This file is also opened for edit by %s - go talk to them to see what they're doing" % other)

            cmds.menuItem(divider=True)

        # has the user already got the file open?
        isOpen = stat.get(simple_p4.StatNames.ACTION)
        if stat[simple_p4.StatNames.IN_DEPOT]:
            cmds.menuItem(l='Open for Edit',
                          cb=bool(isOpen),
                          ann="Will open this file for edit.  If it is already open for edit, it will be checked",
                          c=lambda _: simple_p4.edit(thisScene))

            # is the file up to date?
            have, head = stat.get(simple_p4.StatNames.HAVE_REV), stat.get(simple_p4.StatNames.HEAD_REV)
            if head is not None:
                have, head = int(have), int(head)

                @maya_io.d_suspendCallbacks
                def doSyncTo(version, _):
                    simple_p4.sync('%s#%d' % (thisScene, version))

                    # ask the user if they want the file reloaded
                    BUTS = YES, NO = 'Yes', 'NO!'
                    ret = cmds.confirmDialog(t='Re-load file?', m='Do you want to reload this file?', b=BUTS, db=NO)
                    if ret == YES:
                        cmds.file(thisScene, o=True, f=True)

                cmds.menuItem(l='Sync to Head(%s/%s)' % (have, head),
                              en=have!=head,
                              ann="Will sync this scene file to the head revision and prompt you to reload",
                              c=functools.partial(doSyncTo, head))

                previousMenu = cmds.menuItem(l='Sync to previous',
                                             ann="Select sub menu items to sync to previous revisions of this scene",
                                             sm=True)

                cmds.setParent(P4_GLOBAL_MENU, m=True)

                # now build the previous versions menu
                head = int(head)
                if head > 1:
                    for rev in xrange(head-1, max(head-10, 0), -1):
                        cmds.menuItem(l='Sync to revision %s' % rev,
                                      en=rev!=have,
                                      p=previousMenu,
                                      ann="Syncs this scene to revision %s and prompts to reload" % rev,
                                      c=functools.partial(doSyncTo, rev))
                else:
                    cmds.menuItem(previousMenu, e=True, en=False)
        else:
            cmds.menuItem(l='Open for Add',
                          cb=bool(isOpen),
                          ann="Will open this scene for add.  If the scene file is already open for Add it will be checked",
                          c=lambda _: simple_p4.add(thisScene))

        # if the file is open in some fashion, add a revert menu item
        if isOpen:
            cmds.menuItem(divider=True)
            def doRevert(_):
                BUTS = YES, NO = 'Yes', 'NO!'

                # ask for confirmation first!
                ret = cmds.confirmDialog(t='Really revert?', m='Do you want to revert this scene?', b=BUTS, db=NO)
                if ret == YES:
                    # now revert the file
                    simple_p4.runOnSingleOrMultiple('revert', thisScene)

                    # ask the user if they want the file reloaded now that its been reverted
                    ret = cmds.confirmDialog(t='Re-load file?', m='Do you want to reload this file now that it has been reverted?', b=BUTS, db=NO)
                    if ret == YES:
                        cmds.file(thisScene, o=True, f=True)

            cmds.menuItem(l='Revert',
                          ann='Reverts this scene and asks whether you want the scene reloaded or not',
                          c=doRevert)

        # gathers all scene dependencies into a changelist
        def doSpew(*_):
            for f in scene_dependencies.iterSceneDependencies():
                print f

        cmds.menuItem(divider=1)
        cmds.menuItem(l='Spew dependencies to script editor',
                      ann="Spews this scene's up-stream dependencies to the script editor",
                      c=doSpew)

        cmds.menuItem(l='Gather dependencies into changelist',
                      ann='Gathers all file dependencies in this scene into a single changelist',
                      c=lambda *_: scene_dependencies.gatherSceneDependenciesIntoChangelist())

    # if the scene hasn't been saved, let the user know
    else:
        cmds.menuItem(l='Scene not saved!', en=False)

    cmds.menuItem(divider=1)

    def toggleCB(*a):
        maya_io.setCallbacksEnabled(not maya_io.callbacksEnabled())

    cmds.menuItem(l="P4 callbacks enabled", cb=maya_io.callbacksEnabled(), c=toggleCB)

    def toggleAsk(*a):
        cmds.optionVar(iv=(NEVER_ASK_TO_EDIT, not cmds.optionVar(q=NEVER_ASK_TO_EDIT)))

    askToEdit = not cmds.optionVar(q=NEVER_ASK_TO_EDIT)
    cmds.menuItem(l="Ask to edit on open", cb=askToEdit, c=toggleAsk)

    def openInExplorer(*a):
        proc = subprocess.Popen('explorer /e,/select,%s' % thisScene.replace('/', '\\'))

    cmds.menuItem(d=True)
    cmds.menuItem(l="Explore to file", en=bool(thisScene), c=openInExplorer)

@simple_p4.d_withP4Connection
def preExportP4CB(filepath):
    '''
    ensures that all the scene dependencies are also opened for add
    '''

    # bail on the callback if its not an mdl
    filepath = path.Path(filepath)
    if not filepath.hasExtension('mdl'):
        return True

    # ensure tangent space attribute is set properly
    for meshNode in cmds.ls(type='mesh'):
        cmds.setAttr('%s.tangentSpace' % meshNode, 0)

    # save the file if it has been modified
    if cmds.file(q=True, modified=True):
        cmds.file(save=True, f=True)

    try:

        # grab fstat dicts for scene dependencies
        dependencyFilepaths = list(scene_dependencies.iterSceneDependencies())
        stats = simple_p4.fstat(dependencyFilepaths)

        dependencyFilepathsToAdd = []
        for stat in stats:
            inDepot = stat.get(simple_p4.StatNames.IN_DEPOT, False)

            # if the file isn't in the depot but IS under the workspace, then add it
            if not inDepot:
                inWorkspace = stat.get(simple_p4.StatNames.IN_WORKSPACE, False)
                if inWorkspace:
                    dependencyFilepathsToAdd.append(stat[simple_p4.StatNames.CLIENT_FILE])

        if dependencyFilepathsToAdd:
            simple_p4.add(dependencyFilepathsToAdd)

        cmds.evalDeferred(scene_dependencies.gatherSceneDependenciesIntoChangelist)

    except Exception, x:
        cmds.confirmDialog(t='Export Error', m="An error occurred while preparing the file for export:\n\n%s\n\nAborting export..." % x, b=('Ok',))
        return False

    return True

#end
