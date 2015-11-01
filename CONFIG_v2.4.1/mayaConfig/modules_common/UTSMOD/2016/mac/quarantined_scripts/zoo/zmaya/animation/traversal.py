
import logging

from PySide.QtGui import *
from maya import cmds

from ... import vectors
from .. import base_ui
from .. import maya_decorators
from .. import skeletonBuilder
from . import clip

logger = logging.getLogger(__name__)

def zip(*iterables):
    """
    This zip generator emulates python's builtin zip which isn't a generator
    """
    iterables = [iter(iterable) for iterable in iterables]
    while True:
        toYield = []
        try:
            for iterable in iterables:
                toYield.append(next(iterable))

            yield toYield
        except StopIteration:
            break

def rootAndControlsFromWorld(rigWorld):
    """
    returns the root part and
    """
    rootCls = skeletonBuilder.RigPart.GetNamedSubclass('Root')
    ikFkCls = skeletonBuilder.RigPart.GetNamedSubclass('IkFkBase')

    # first get all the relevant rig parts
    rootPart = None
    limbs = []
    for part in rigWorld.iterChildParts(True):
        if isinstance(part, rootCls):
            rootPart = part
        elif isinstance(part, ikFkCls):
            limbs.append(part)

    # now grab the root control - this is the control we're extracting the traversal from
    rootControl = rootPart.getControl('control')
    trajControl = rootPart.getControl('trajectory')

    # now we need to create a bake context - we want to preserve keys
    controls = [rootControl]
    for part in limbs:
        controls.append(part.getControl('control'))
        controls.append(part.getControl('poleControl'))

    controls.append(trajControl)

    return rootControl, controls

@maya_decorators.d_undoBlock
@maya_decorators.d_noAutoKey
def toWorld(rigWorld, rotation=True):
    if not isinstance(rigWorld, skeletonBuilder.RigPart):
        rigWorld = skeletonBuilder.RigPart.InitFromItem(rigWorld)

    # get the world control
    worldControl = rigWorld.getControl('control')

    # grab root control and the controls we want to snapshot
    rootControl, controls = rootAndControlsFromWorld(rigWorld)

    bakeContext = clip.BakeContext(controls)
    with bakeContext:
        poses = [clip.storeWorldPose(controls) for keyTime in bakeContext]
        for poseData, keyTime in zip(poses, bakeContext):
            _, rootPos, rootRot = poseData[0]

            # transfer the motion from the root to the world control
            cmds.move(rootPos[0], 0, rootPos[2], worldControl, a=True, ws=True, rpr=True)
            if rotation:
                cmds.rotate(0, rootRot[1], 0, worldControl, a=True, ws=True)
                cmds.setKeyframe(worldControl, at=('t', 'r'))
            else:
                cmds.setKeyframe(worldControl, at=('t',))

            # restore the pose
            clip.restoreWorldPose(poseData)
            cmds.setKeyframe(controls, at=('t', 'r'))

    clip.eulerFilterNodes([worldControl] + controls)

TO_ORIGIN, TO_INITIAL = range(2)

@maya_decorators.d_undoBlock
@maya_decorators.d_noAutoKey
def fromWorld(rigWorld, resetTo=TO_ORIGIN):
    if not isinstance(rigWorld, skeletonBuilder.RigPart):
        rigWorld = skeletonBuilder.RigPart.InitFromItem(rigWorld)

    # get the world control
    worldControl = rigWorld.getControl('control')

    # grab root control and the controls we want to snapshot
    rootPart, controls = rootAndControlsFromWorld(rigWorld)

    bakeContext = clip.BakeContext(controls)
    with bakeContext:
        poses = [clip.storeWorldPose(controls) for keyTime in bakeContext]

        # set the time to the start time
        cmds.currentTime(bakeContext.startKeyTime, e=True)
        initialT = 0, 0, 0
        initialR = 0, 0, 0
        if resetTo == TO_INITIAL:
            initialT = cmds.getAttr('%s.t' % worldControl)[0]
            initialR = cmds.getAttr('%s.r' % worldControl)[0]

        # grab the initial position in case we need it
        for ax in ('x', 'y', 'z'):
            cmds.cutKey('%s.t%s' % (worldControl, ax), cl=True)
            cmds.cutKey('%s.r%s' % (worldControl, ax), cl=True)

        cmds.setAttr('%s.t' % worldControl, *initialT)
        cmds.setAttr('%s.r' % worldControl, *initialR)

        for poseData, keyTime in zip(poses, bakeContext):
            clip.restoreWorldPose(poseData)
            cmds.setKeyframe(controls, at=('t', 'r'))

    clip.eulerFilterNodes([worldControl] + controls)

def worldPartsFrom(nodes):
    parts = set()
    if nodes:
        for node in nodes:
            part = skeletonBuilder.RigPart.InitFromItem(node)
            parts.add(part)
    else:
        for part in skeletonBuilder.RigPart.Iter():
            parts.add(part)

    worldParts = set()
    for part in parts:
        worldPart = part.getWorldPart()
        worldParts.add(worldPart)

    return worldParts

def selectionToWorld(rotation=True):
    worldParts = worldPartsFrom(cmds.ls(sl=True))
    for worldPart in worldParts:
        toWorld(worldPart, rotation)

def selectionFromWorld(resetTo=TO_ORIGIN):
    worldParts = worldPartsFrom(cmds.ls(sl=True))
    for worldPart in worldParts:
        fromWorld(worldPart, resetTo)

class RootMotion(base_ui.MayaQWidget):
    def __init__(self):
        super(RootMotion, self).__init__()

        self.doRotation = QCheckBox('Transfer Rotation')
        self.doRotation.setChecked(True)

        toWorld = QPushButton('Root Motion TO World')
        toWorld.clicked.connect(self.toWorld)

        self.resetTo = QCheckBox('Reset To Initial')
        self.resetTo.setChecked(True)

        fromWorld = QPushButton('Root Motion FROM World')
        fromWorld.clicked.connect(self.fromWorld)

        tolayout = QHBoxLayout()
        tolayout.addWidget(self.doRotation)
        tolayout.addWidget(toWorld, 1)

        fromlayout = QHBoxLayout()
        fromlayout.addWidget(self.resetTo)
        fromlayout.addWidget(fromWorld, 1)

        layout = QVBoxLayout()
        layout.addLayout(tolayout)
        layout.addLayout(fromlayout)
        layout.addStretch()

        self.setLayout(layout)

    def toWorld(self):
        rotation = self.doRotation.isChecked()
        selectionToWorld(rotation)

    def fromWorld(self):
        resetTo = TO_INITIAL if self.resetTo.isChecked() else TO_ORIGIN
        selectionFromWorld(resetTo)

def rootPartFromWorld(worldPart):
    """
    returns the root part
    """
    rootCls = skeletonBuilder.RigPart.GetNamedSubclass('Root')
    for part in worldPart.iterChildParts(True):
        if isinstance(part, rootCls):
            return part

def printOffsetFromSelectedTrajectory():
    sel = cmds.ls(sl=True) or []
    if not sel:
        logger.error("Please select part of the attacker's rig")
        return

    worldParts = worldPartsFrom(sel)
    if len(worldParts) != 1:
        logger.error("Please make sure only controls from the attacker's rig are selected")
        return

    attackerWorldPart = list(worldParts)[0]

    worldParts = list(skeletonBuilder.WorldPart.Iter())
    worldParts.remove(attackerWorldPart)

    attackerRootPart = rootPartFromWorld(attackerWorldPart)
    attackerTrajControl = attackerRootPart.getControl('trajectory')
    attackerTrajControlInvMatrix = vectors.Matrix(cmds.getAttr('%s.worldInverseMatrix' % attackerTrajControl))
    for aWorldPart in worldParts:
        aRootPart = rootPartFromWorld(aWorldPart)
        aTrajControl = aRootPart.getControl('trajectory')
        aTrajControlMatrix = vectors.Matrix(cmds.getAttr('%s.worldMatrix' % aTrajControl))
        relativeToAttackerMatrix = aTrajControlMatrix * attackerTrajControlInvMatrix

        # divide by 100 so that the units are meters
        offsetVector = relativeToAttackerMatrix.get_position() / 100.0
        logger.info('The offset vector between "%s" and "%s" is (is a 2-vector <x,z> in meters):' % (attackerTrajControl, aTrajControl))
        logger.info('<Vec2 name="Offset">%0.2f, %0.2f</Vec2>' % (offsetVector.x, offsetVector.z))

#end
