
from maya import cmds

from .. import maya_decorators
from .. import constants
import clip

def onlyTransforms(nodes):
    """
    Returns a list containing only transform nodes
    """
    return [n for n in nodes if cmds.objectType(n, isAType='transform')]

from ..skeletonBuilder import baseRigPart, spaceSwitching

@maya_decorators.d_noAutoKey
@maya_decorators.d_restoreTime
@maya_decorators.d_undoBlock
def switchParentForAnimatedControls(nodes, parentIdx):
    with clip.BakeContext(nodes) as bakeCtx:
        spaceSwitchNodes = [spaceSwitching.SpaceSwitchNode(node) for node in nodes]
        for time in bakeCtx:
            for spaceSwitchNode in spaceSwitchNodes:
                spaceSwitchNode.switchTo(parentIdx, key=True)

        # filter rotations
        clip.eulerFilterNodes(nodes)

@maya_decorators.d_noAutoKey
@maya_decorators.d_restoreTime
@maya_decorators.d_undoBlock
def switchToFkForAnimatedPart(part):

    # get the source controls - these are the nodes we're getting keys from.  Ie the ik controls
    # if we're switching to fk or vice-versa
    ikNodes = part.getIkControls()

    # grab the main ik control - we need it while we're switching
    ikControl = ikNodes[0]
    blendAttrpath = '%s.%s' % (ikControl, part.IK_BLEND_ATTRNAME)

    # just trace frames where the main ik control is keyed
    with clip.BakeContext([ikControl]) as bakeCtx:

        # get the fk controls
        fkNodes = part.getFkControls()

        # now remove any keys that are on the fk controls between the start and end
        # NOTE: we have to do this within the BakeContext so the start and end times are defined
        cmds.cutKey(fkNodes, t=(bakeCtx.startKeyTime, bakeCtx.endKeyTime), cl=True)

        # now do the switch
        for time in bakeCtx:

            # set ik to be on before switching - remember, we're switching FROM ik so we need to
            # make sure its on before doing the switch
            cmds.setAttr(blendAttrpath, 0)

            part.switchToFk(key=True)

    # filter rotations
    clip.eulerFilterNodes(fkNodes)

def switchToFkForAnimatedControl(node):

    # get the rig part
    part = baseRigPart.RigPart.InitFromItem(node)

    switchToFkForAnimatedControl(part)

@maya_decorators.d_noAutoKey
@maya_decorators.d_restoreTime
@maya_decorators.d_undoBlock
def switchToIkForAnimatedPart(part):

    # get the fk controls
    fkNodes = part.getFkControls()

    with clip.BakeContext(fkNodes) as bakeCtx:

        # get the fk controls
        ikNodes = part.getIkControls()

        # grab the main ik control - we need it while we're switching
        ikControl = ikNodes[0]
        blendAttrpath = '%s.%s' % (ikControl, part.IK_BLEND_ATTRNAME)

        # now remove any keys that are on the fk controls between the start and end
        # NOTE: we have to do this within the BakeContext so the start and end times are defined
        cmds.cutKey(ikNodes, t=(bakeCtx.startKeyTime, bakeCtx.endKeyTime), cl=True)

        # now do the switch
        for time in bakeCtx:

            # set ik to be off before switching - remember, we're switching FROM fk so we need to
            # make sure ik is on before doing the switch
            cmds.setAttr(blendAttrpath, 0)

            # now perform the switch
            part.switchToIk(key=True)

    # filter rotations
    clip.eulerFilterNodes(ikNodes)

def switchToIkForAnimatedControl(node):

    # get the rig part
    part = baseRigPart.RigPart.InitFromItem(node)

    switchToIkForAnimatedPart(part)

@maya_decorators.d_noAutoKey
@maya_decorators.d_restoreTime
@maya_decorators.d_undoBlock
def placePoleForAnimatedPart(part):
    poleControl = part.getControl('poleControl')
    with clip.BakeContext([poleControl]) as bakeCtx:
        for time in bakeCtx:
            part.placePole(True)

@maya_decorators.d_noAutoKey
@maya_decorators.d_restoreTime
@maya_decorators.d_undoBlock
def switchRooForAnimatedControls(nodes, newRoo):
    rooStrs = constants.MAYA_ROTATE_ORDER_STRS

    # Filter out non-transform nodes and bail if the list is empty
    nodes = onlyTransforms(nodes)
    if not nodes:
        return

    # Ensure we have the ro as a string (that is what the xform command expects)
    newRooStr = newRoo
    if isinstance(newRoo, int):
        newRooStr = rooStrs[newRoo]

    # Anchor rotation keys
    clip.anchorRotationKeys(nodes)

    # Store initial rotation orders
    initialRooStrs = dict((n, rooStrs[cmds.getAttr('%s.ro' % n)]) for n in nodes)

    with clip.BakeContext(nodes) as bakeCtx:
        for time in bakeCtx:
            for node in nodes:

                # Switch to initial rotation order (ie: the ro the key was set at)
                cmds.xform(node, roo=initialRooStrs[node], p=False)

                # Now switch to the desired ro and set a key
                cmds.xform(node, roo=newRooStr, p=True)
                cmds.setKeyframe(node, attribute='r')

    # Filter rotations
    clip.eulerFilterNodes(nodes)

#end
