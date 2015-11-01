
import sys

from maya import cmds, mel

from ... import path
from ... import misc

from .. import apiExtensions
from .. import reference_utils

import baseSkeletonPart
import baseRigPart
import rig_utils

ALWAYS_UPDATE_RIGS = 'tb_alwaysUpdateRigs'

class RigUpdateError(Exception): pass

def iterRigReferencesInScene():
    '''
    iterates over all rig references in the scene
    '''
    for refNode in reference_utils.ReferenceNode.Iter():

        # are there any rig containers in the file?  If so its a rig
        rigParts = baseRigPart.filterRigPartContainers(refNode.getNodes())
        if rigParts:
            yield refNode

class RigVersion(object):

    @classmethod
    def _Parse(cls, filename):
        toks = filename.split('_')
        version = 0

        # determine the version of this rig based on the filename
        if len(toks) > 1:
            versionTok = toks[-1]
            if versionTok.startswith('v'):
                versionTok = versionTok[1:]

            if versionTok.isdigit():
                version = int(versionTok)
            else:
                version = None

        return toks[0], version

    def __init__(self, filepath):
        self.filepath = filepath = path.Path(filepath)
        self.prefix, self.version = self._Parse(filepath.name())

    def __str__(self):
        return '%s v%02d' % (self.prefix, self.version)

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self.filepath)

    def __eq__(self, other):
        return self.filepath == other.filepath

    def __ne__(self, other):
        return not self.__eq__(other)

    def __cmp__(self, other):
        return cmp(self.version, other.version)

    def isSameRigFamily(self, otherRigVersion):
        return otherRigVersion.version is not None and \
               self.prefix == otherRigVersion.prefix

    def getAllVersions(self):
        filepath = self.filepath
        version, prefix = self._Parse(filepath.name())

        existing = []

        # determine existing versions
        for aFilepath in filepath.up().files():
            if aFilepath.getExtension().lower() in ('ma', 'mb'):
                aRigVersion = RigVersion(aFilepath)
                if self.isSameRigFamily(aRigVersion):
                    existing.append(aRigVersion)

        # sort the versions
        return sorted(existing)

    def iterNewerFilepaths(self):
        for aRigVersion in self.getAllVersions():
            if aRigVersion.version > self.version:
                yield aRigVersion

    def loadInto(self, referenceNode):
        '''
        loads this rig version into the given reference node

        referenceNode is a reference_utils.ReferenceNode instance
        '''
        referenceNode.setFilepath(self.filepath)

    def getUpdateScript(self):
        return self.filepath.setExtension('py')

    def hasUpdateScript(self):
        return self.getUpdateScript().exists()

    def getLatest(self):
        return list(self.iterNewerFilepaths())[-1]

def d_restoreSysPath(f):
    '''
    protects sys.path from being screwed up
    '''
    def wrapped(*a, **kw):

        # store the original sys.path and replace it with a copy
        originalSysPath = sys.path
        sys.path = list(originalSysPath)

        try:
            return f(*a, **kw)
        finally:
            sys.path = originalSysPath

    return wrapped

@d_restoreSysPath
def updateToVersion(referenceNode, oldRigVersion, newRigVersion):
    '''
    updates a particular reference node to the given rig version

    NOTE: referenceNode should be a reference_utils.ReferenceNode instance,
    old and newRigVersion should be RigVersion instances
    '''

    # first, check to see if there is an update script
    updateScriptFilepath = newRigVersion.getUpdateScript()
    if updateScriptFilepath.exists():
        sys.path.insert(0, updateScriptFilepath.up())

        scriptName = updateScriptFilepath.name()
        updateModule = __import__(scriptName)

        # execute the update function inside the module (PS: execfile sucks)
        # an update script has complete control over the update process.  The only requirement is that the reference
        # node handed to it points to the new rig filepath once the update function has executed.  Apart from that,
        # update can handle the update in any way it wants.
        getattr(updateModule, 'update')(referenceNode, oldRigVersion, newRigVersion)

        # make sure the update script has replaced the reference appropriately
        if referenceNode.getFilepath() != newRigVersion.filepath:
            raise RigUpdateError("The update script %s failed to update the rig to %s" % (updateScriptFilepath.name(),
                                                                                          newRigVersion.filepath))

        # delete the module from sys.modules
        del sys.modules[scriptName]

    # otherwise just replace the reference!
    else:
        newRigVersion.loadInto(referenceNode)

def iterOutdatedSceneRigs():
    '''
    yields the referenceNode, rigVersion pairs for all outdated scene rigs
    '''
    for rigRefNode in iterRigReferencesInScene():
        rigVersion = RigVersion(rigRefNode.getFilepath())
        for newRigVersion in rigVersion.iterNewerFilepaths():

            # this is a little weird - iterate over new rig filepaths and yield if there is a new one
            # then break
            yield rigRefNode, rigVersion
            break

def doesSceneHaveRigUpdates():
    '''
    returns whether any rigs in the scene have updates available
    '''
    for rigVersion in iterOutdatedSceneRigs():
        return True

    return False

def updateSceneRigs():
    '''
    updates all rigs in the scene
    '''
    updated = False
    for rigRefNode, rigVersion in iterOutdatedSceneRigs():
        for newRigVersion in rigVersion.iterNewerFilepaths():
            updateToVersion(rigRefNode, rigVersion, newRigVersion)
            updated = True

    return updated

def updateSceneSkeleton(skeletonFilepath):
    '''
    updating skeletons is a little different from updating rigs

    Skeletons are imported in, not referenced.  So there is only ever one skeleton file.  There are
    a variety of reasons for this, but mainly it comes back to the fact that the game runs the
    skeleton directly so it only makes sense to have one version.  The rig on the other hand drives
    a skeleton, so it is both valid and possible to have 2 rigs drive the same skeleton.  In other
    words, it is possible to have different animations using different rig versions but it isn't
    possible to have different animations using different skeletons.
    '''

    # this process is pretty straight forward - its basically just duplicating the geo, skinning it
    # to the new skeleton and copying skin weights
    oldSkeleton = next(baseSkeletonPart.Root.Iter())
    oldGeometry = []

    oldJoints = [oldSkeleton.root] + (cmds.listRelatives(oldSkeleton.root, ad=True, pa=True, type='joint') or [])
    oldSkinClusters = cmds.listConnections(oldJoints, type='skinCluster', s=False) or []
    for skinCluster in oldSkinClusters:
        oldGeometry += cmds.skinCluster(skinCluster, q=True, g=True)

    oldGeometry = misc.removeDupes(oldGeometry)

    # import the new skeleton
    cmds.file(skeletonFilepath, i=True, namespace='skeleton')
    newSkeleton = None
    newGeometry = []

    for part in baseSkeletonPart.Root.Iter():
        if part != oldSkeleton:
            newSkeleton = part
            break

    oldSkeletonParent = cmds.listRelatives(oldSkeleton.root, p=True, pa=True)
    if oldSkeletonParent:
        cmds.parent(newSkeleton.root, oldSkeletonParent[0])

    # ok now this is a bit of a hack - we want to ensure the wrists are aligned properly. the easiest
    # way to do this is to force world alignment
    armCls = baseSkeletonPart.SkeletonPart.GetNamedSubclass('Arm')
    for armPart in armCls.Iter():
        rig_utils.getWristToWorldRotation(armPart.wrist, True)

    # now duplicate the geometry and skin to the new skeleton
    for oldGeo in oldGeometry:
        newGeo = cmds.duplicate(oldGeo, returnRootsOnly=True, renameChildren=True)[0]
        newGeo = apiExtensions.asMObject(newGeo)

        newGeometry.append(newGeo)

        # delete any children and intermediate shapes
        children = cmds.listRelatives(newGeo, pa=True, type='transform')
        if children:
            cmds.delete(children)

        for shape in cmds.listRelatives(newGeo, pa=True, type='mesh'):
            if cmds.getAttr('%s.intermediateObject' % shape):
                cmds.delete(shape)

        # is the old geo plugged into any exportable?  If so, make sure to replace the connection
        # with the dupe
        geoExportables = export_manager.exportablesFromNode(oldGeo)

        # now skin it to the new skeleton
        oldSkin = mel.eval('findRelatedSkinCluster %s' % oldGeo)
        newSkin = cmds.skinCluster(newSkeleton.base, newGeo)[0]
        cmds.copySkinWeights(ss=oldSkin, ds=newSkin, noMirror=True,
                             influenceAssociation='closestJoint', surfaceAssociation='closestPoint')

        # delete the old geometry and rename the duplicate
        cmds.delete(oldGeo)
        newGeo.rename(oldGeo)

        # re-hook up any exportables
        for exportable in geoExportables:
            exportable.setNodes(exportable.nodes() + [newGeo])

    # delete the old skeleton
    for part in oldSkeleton.iterChildParts():
        part.delete()

    # rename the new skeleton to remove the namespace
    for item in cmds.listRelatives(newSkeleton.root, pa=True, ad=True):
        cmds.rename(item, str(item).replace('skeleton:', ''))

    export_manager.exportAll()

def checkSceneRigForUpdates():
    '''
    checks the scene for various things such as current units
    '''
    if doesSceneHaveRigUpdates():

        # if the user has set the always update rigs pref, then just do it without asking
        if cmds.optionVar(q=ALWAYS_UPDATE_RIGS):
            updateSceneRigs()

        # otherwise notify the user that an update is available and ask them what they want to do
        else:
            BUTTONS = YES, NO, ALWAYS = 'Yes', 'No', 'Always'
            ret = cmds.confirmDialog(t='Scene has old rigs',
                                     m='This scene contains rigs that are out of date\n\n' \
                                     'Do you want to update the outdated rigs?',
                                     b=BUTTONS,
                                     db=YES)

            # if the user hits 'Always', set the pref and continue as if the user had hit 'Yes'
            if ret == ALWAYS:
                cmds.optionVar(iv=(ALWAYS_UPDATE_RIGS, 1))
                ret = YES

            # update the rigs!
            if ret == YES:
                updateSceneRigs()

#end
