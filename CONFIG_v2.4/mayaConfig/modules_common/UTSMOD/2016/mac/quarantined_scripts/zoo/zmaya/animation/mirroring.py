
from maya import cmds, OpenMayaAnim

import misc
import poseSym
import apiExtensions
import maya_decorators

from ..skeletonBuilder import baseRigPart

import clip

class BakeMirrorContext(clip.BakeContext):
    def __exit__(self, *exc_info):
        oppositeNodeDict = {}
        for node in self._nodes:
            pairNode = poseSym.ControlPair.GetPairNode(node)
            if not pairNode:
                continue

            pair = poseSym.ControlPair(pairNode)
            if pair.isSingular():
                continue

            if pair.controlA in oppositeNodeDict:
                continue

            oppositeNodeDict[pair.controlA] = pair.controlB
            oppositeNodeDict[pair.controlB] = pair.controlA

        # swap key timings for nodes that have an opposite in self._nodeAttrKeyTimeDicts
        swappedDict = {}
        for attrKeyTimeDict in self._nodeAttrKeyTimeDicts:
            items = attrKeyTimeDict.items()

            if not items:
                continue

            toks = str(items[0][0]).split('.')
            node = toks[0]

            # if the node has an opposite, swap all the attr names to the opposite control
            if node in oppositeNodeDict:
                oppositeNode = oppositeNodeDict[node]

                # clear out the dict, we're going to re-populate it
                attrKeyTimeDict.clear()
                for attrpath, originalTimes in items:
                    toks = str(attrpath).split('.')
                    toks[0] = oppositeNode
                    attrpath = '.'.join(toks)

                    # if the attrpath exists, plug it back into the original key dict
                    if cmds.objExists(attrpath):
                        attrKeyTimeDict[attrpath] = originalTimes

        # now that we've re-arranged the key timing data, call exit on the super class
        super(BakeMirrorContext, self).__exit__(self, *exc_info)

def getRigControls(part):
    controls = list(part)
    for childPart in part.iterChildParts(True):
        controls += list(childPart)

    return controls

@maya_decorators.d_noAutoKey
def swapPoseForControls(controls):
    with poseSym.CommandStack() as cmdStack:
        for pair, obj in poseSym.iterPairAndObj(controls):
            pair.swap(cmdStack=cmdStack)

def swapPoseForRig(rigPart):
    swapPoseForControls(rigPart.getPartHierarchyControls())

@maya_decorators.d_noAutoKey
def swapAnimationForControls(controls, start=None, end=None):
    with BakeMirrorContext(controls, start, end) as controlKeyTimes:
        for time in controlKeyTimes:
            swapPoseForControls(controls)

            # set a key to lock the pose in
            cmds.setKeyframe(controls)

        clip.eulerFilterNodes(controls)

def swapAnimationForRig(part, start=None, end=None):
    swapAnimationForControls(getRigControls(part), start, end)

#end
