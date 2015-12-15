
import logging

from PySide.QtGui import *
from PySide.QtCore import Signal
from maya import cmds

import path
import str_utils
import filterable_list

import base_ui
import mel_utils
import mapping_utils
import apiExtensions
import maya_decorators
import reference_utils
import skeletonBuilder

from skeletonBuilder import versions
from animation import clip

logger = logging.getLogger(__name__)

def getRigMapping(rigWorld):
    rigMapping = str_utils.Mapping()
    for childPart in rigWorld.iterChildParts(True):
        thisMapping = childPart.getControlToJointMapping()

        rigMapping.srcs += thisMapping.srcs
        rigMapping.tgts += thisMapping.tgts

    # swap the sources and targets - the part implements a control to joint
    # map, we want a joint to control map
    rigMapping.srcs, rigMapping.tgts = rigMapping.tgts, rigMapping.srcs

    return rigMapping

def getRigToSkeletonMapping(rigWorld, skeletonRoot):
    rigMapping = getRigMapping(rigWorld)

    sourceJoints = cmds.listRelatives(skeletonRoot, ad=True, pa=True) or []
    sourceJoints.insert(0, skeletonRoot)

    mappedTgts = mapping_utils.matchNames(rigMapping.srcs, sourceJoints)

    rigMapping.srcs = mappedTgts.tgts

    return rigMapping

def setupPostTraceScheme(rigWorld):
    clip.autoGeneratePostTraceScheme(getRigMapping(rigWorld))

@maya_decorators.d_undoBlock
@maya_decorators.d_restoreTime
def matchPosedSkeleton(rigWorld, skeletonRoot, start=None, end=None, skip=1):
    if not isinstance(rigWorld, skeletonBuilder.RigPart):
        rigWorld = skeletonBuilder.RigPart.InitFromItem(rigWorld)

    rigMapping = getRigToSkeletonMapping(rigWorld, skeletonRoot)

    # make sure limbs are in ik mode
    for childPart in rigWorld.iterChildParts(True):
        if hasattr(childPart, 'isIk'):
            if not childPart.isIk():
                childPart.switchToIk()

    if start is None:
        start = cmds.currentTime(q=True)

    if end is None:
        end = cmds.currentTime(q=True)

    clip.Tracer(False, start=start, end=end, skip=skip).apply(rigMapping, False)

class NodeWidget(base_ui.MayaQWidget):
    nodeChanged = Signal(object)

    def __init__(self, label):
        super(NodeWidget, self).__init__()

        self._node = None

        self.setNode = QPushButton(label)
        self.setNode.clicked.connect(self.setNodeToSelection)

        self.lbl = QLabel()

        self.clear = QPushButton()
        self.clear.clicked.connect(self.clearNode)
        self.clear.setIcon(self.getIcon('remove.png'))
        self.clear.setVisible(False)

        layout = QHBoxLayout()
        layout.addWidget(self.setNode)
        layout.addWidget(self.lbl, 1)
        layout.addWidget(self.clear)
        self.setLayout(layout)

        self.updateLabel()

    @property
    def node(self):
        return self._node

    @node.setter
    def node(self, node):
        if node is None:
            self._node = None
        else:
            self._node = apiExtensions.asMObject(node)

        self.updateLabel()
        self.nodeChanged.emit(self._node)

    def updateLabel(self):
        if self._node is None:
            self.lbl.setText('<no node set>')
            self.lbl.setEnabled(False)
            self.clear.setVisible(False)
        else:
            self.lbl.setText(str(self._node))
            self.lbl.setEnabled(True)
            self.clear.setVisible(True)

    def clearNode(self):
        self.node = None

    def setNodeToSelection(self):
        nodes = cmds.ls(sl=True)
        if nodes:
            self.node = nodes[0]

class RigWidget(NodeWidget):
    def setNodeToSelection(self):
        nodes = cmds.ls(sl=True)
        if nodes:
            rigPart = skeletonBuilder.RigPart.InitFromItem(nodes[0])
            worldPart = rigPart.getWorldPart()
            self.node = worldPart.getContainer()

class SkeletonWidget(NodeWidget):
    def setNodeToSelection(self):
        nodes = cmds.ls(sl=True)
        if nodes:
            self.node = apiExtensions.getHierarchyRoot(nodes[0])

class PoseTracerWidget(base_ui.MayaQWidget):
    def __init__(self):
        super(PoseTracerWidget, self).__init__()

        self._rig = RigWidget('Set Rig->')
        self._rig.nodeChanged.connect(self.updateUIState)

        self._skeleton = SkeletonWidget('Set Skeleton->')
        self._skeleton.nodeChanged.connect(self.updateUIState)

        self._traceSingle = QPushButton('Trace this frame')
        self._traceSingle.clicked.connect(self.traceFrame)

        validator = QDoubleValidator()

        self._start = QLineEdit(str(cmds.playbackOptions(q=True, min=True)))
        self._start.setValidator(validator)

        self._end = QLineEdit(str(cmds.playbackOptions(q=True, max=True)))
        self._end.setValidator(validator)

        self._skip = QLineEdit('1')
        self._skip.setValidator(validator)

        self._traceMany = QPushButton('Batch trace frames')
        self._traceMany.clicked.connect(self.traceMany)

        dataLayout = QHBoxLayout()
        dataLayout.addWidget(self._rig, 1)
        dataLayout.addWidget(self._skeleton, 1)

        manyLayout = QHBoxLayout()
        manyLayout.addWidget(QLabel('Start'))
        manyLayout.addWidget(self._start, 1)
        manyLayout.addWidget(QLabel('End'))
        manyLayout.addWidget(self._end, 1)
        manyLayout.addWidget(QLabel('Frame Skip'))
        manyLayout.addWidget(self._skip, 1)

        vlayout = QVBoxLayout()
        vlayout.addLayout(dataLayout)
        vlayout.addWidget(self._traceSingle)
        vlayout.addWidget(base_ui.createSeparator())
        vlayout.addLayout(manyLayout)
        vlayout.addWidget(self._traceMany)
        vlayout.addStretch()

        self.setLayout(vlayout)

        self.populate()
        self.setSceneChangeCB(self.populate)

    def populate(self):
        self._rig.node = None
        self._skeleton.node = None

        # if there is only one world part in the scene, use it
        worldParts = list(skeletonBuilder.WorldPart.Iter())
        if len(worldParts) == 1:
            worldPart = worldParts[0]
            self._rig.node = worldPart.getContainer()

            childParts = list(worldPart.iterChildParts())
            rigSkeleton = apiExtensions.getHierarchyRoot(childParts[0].getSkeletonPart()[0])
            rigSkeleton = apiExtensions.asMObject(rigSkeleton)

            # now try to find the skeleton
            joints = cmds.ls(type='joint')
            if joints:
                roots = apiExtensions.castToMObjects(apiExtensions.getHierarchyRoot(j) for j in joints)
                if rigSkeleton in roots:
                    roots.remove(rigSkeleton)

                if len(roots) == 1:
                    self._skeleton.node = roots[0]

    def updateUIState(self, _):
        enableState = self._rig.node is not None and \
            self._skeleton.node is not None

        self._traceSingle.setEnabled(enableState)
        self._traceMany.setEnabled(enableState)

    def traceFrame(self):
        matchPosedSkeleton(str(self._rig.node), str(self._skeleton.node))

    def traceMany(self):
        start = float(self._start.text())
        end = float(self._end.text())
        skip = float(self._skip.text())
        matchPosedSkeleton(str(self._rig.node), str(self._skeleton.node), start, end, skip)

PoseTracer = PoseTracerWidget.Show

def referenceLatestRig():
    '''
    References in the latest rig.

    The reference node encapsulating the rig is returned.
    '''

    # figure out the filepath for the latest rig...
    baseRig = versions.RigVersion(path.TB_DATA / 'animation/male/rig.ma')

    # now reference in that rig
    refFilepath = cmds.file(baseRig.getLatest().filepath, ns='rig', reference=True, prompt=False)
    referenceFile = reference_utils.ReferencedFile(refFilepath)
    referenceNode = referenceFile.getReferenceNode()

    return referenceNode

def iterWorldFromReference(refNode):
    rigPartNodes = skeletonBuilder.baseRigPart.filterRigPartContainers(refNode.getNodes())
    if rigPartNodes:
        for node in rigPartNodes:
            part = skeletonBuilder.RigPart(node)
            if isinstance(part, skeletonBuilder.WorldPart):
                yield part

def getWorldFromReference(refNode):
    for part in iterWorldFromReference(refNode):
        return part

def autoMapMocapToRig(frameskip=6):
    sel = cmds.ls(sl=True)
    rootNodes = []

    # figure out the root nodes for things in the scene
    if sel:
        for node in sel:
            for node in apiExtensions.iterUp(node):
                if node.endswith('geo'):
                    rootNodes.append(node)
                    break
    else:
        rootNodes = cmds.ls('geo', r=True)

    if not rootNodes:
        return

    for mocapRoot in rootNodes:

        # determine frame ranges from the mocap
        joints = cmds.listRelatives(mocapRoot, type='joint', ad=True, pa=True)
        keys = cmds.keyframe(joints, q=True)
        keys.sort()
        start = keys[0]
        end = keys[-1]

        rigReference = referenceLatestRig()
        rigWorld = getWorldFromReference(rigReference)

        # turn auto on for the trajectory node
        rootCls = skeletonBuilder.RigPart.GetNamedSubclass('Root')
        for part in rigWorld.iterChildParts():
            if type(part) is rootCls:
                trajControl = part.getControl('trajectory')
                cmds.setAttr('%s.auto' % trajControl, True)
                break

        # do the trace
        matchPosedSkeleton(rigWorld, mocapRoot, start, end, frameskip)

        # turn auto off
        pos = cmds.xform(trajControl, q=True, ws=True, rp=True)
        cmds.setAttr('%s.auto' % trajControl, False)
        cmds.move(pos[0], pos[1], pos[2], trajControl, a=True, ws=True, rpr=True)

def setTimelineFromMocap():
    '''
    Pulls all keys to the first frame of the scene - mocap often comes in
    with keys offset at weird times
    '''
    animCurves = cmds.ls(type='animCurve')
    if not animCurves:
        return

    keyTimes = cmds.keyframe(animCurves, q=True)
    if not keyTimes:
        return

    keyTimes.sort()

    # set the start time to zero
    cmds.playbackOptions(e=True, min=0, ast=0)

    # now adjust keys so everything starts at zero
    sceneStartTime = cmds.playbackOptions(q=True, min=True)
    delta = keyTimes[0] - sceneStartTime

    cmds.keyframe(animCurves, e=True, relative=True, tc=-delta)

    # now adjust the timeline
    endTime = keyTimes[-1] - delta
    cmds.playbackOptions(e=True, max=int(endTime), aet=int(endTime))

def newFile():
    mel_utils.MEL.saveChanges('file -f -new')

class MocapImporter(filterable_list.FilterableListWidget):
    def __init__(self):
        super(MocapImporter, self).__init__()

        self.dir = path.Path('w:/woto/verticalSlice/Delivery')
        self.populate()

        self.itemOpened.connect(self.importMocap)

    def _candidateTest(self, filepath):
        return filepath.hasExtension('fbx')

    def populate(self):
        self.clear()
        filterStr = self._filter.text()
        files = sorted(self.dir._list_filesystem_items(self._candidateTest, True))
        for f in files:
            self.append(f)

    def importMocap(self, filepath):
        newFile()
        cmds.playbackOptions(e=True, min=0)

        # set the framerate to 60 - all the mocap is at this rate
        cmds.currentUnit(time='ntscf')

        # import the file
        cmds.file(filepath, i=True)

        # set the timeline
        setTimelineFromMocap()

def AutoTrace():
    frameskip, proceed = QInputDialog.getInt(None, "Frameskip?", "Trace the mocap skeleton every n frames:", value=6, minValue=1, maxValue=20, step=1)
    if proceed:
        autoMapMocapToRig(frameskip)

#end
