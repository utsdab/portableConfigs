import logging

from maya import cmds
from maya import OpenMayaAnim
from maya.cmds import getAttr, setAttr, deleteAttr, objExists, createNode, xform, move, rotate, setKeyframe

from ... import str_utils

from ...vectors import Vector, Matrix

from .. import constants
from .. import mel_utils
from .. import apiExtensions
from .. import maya_decorators

logger = logging.getLogger(__name__)

class AnimLibError(Exception): pass

class MaintainAnimLayerSelectionContext(object):
    def __enter__(self):
        self._animLayers = cmds.ls(type='animLayer')
        self._animLayerSelectionStates = [cmds.animLayer(l, q=True, selected=True) for l in self._animLayers]

    def __exit__(self, exc_type, exc_info, traceback):
        # NOTE: the selection state of anim layers created within this context
        # manager is undetermined
        for layer, state in zip(self._animLayers, self._animLayerSelectionStates):
            mel_utils.MEL.animLayerEditorOnSelect(layer, state)

def keyTimesFromNodes(nodes, attrs=None, considerAnimLayers=True):
    animLayers = cmds.animLayer(nodes, q=True, affectedLayers=True)

    keyframeKwargs = {}
    if attrs:
        keyframeKwargs['at'] = attrs

    # if there are anim layers, get the union of keytimes for all layers
    if animLayers:
        times = []
        with MaintainAnimLayerSelectionContext():
            for animLayer in animLayers:
                # NOTE: this will change the anim layer selection, but the surrounding
                # context manager should handle restoring them...
                mel_utils.MEL.selectLayer(animLayer)
                times += cmds.keyframe(nodes, q=True, **keyframeKwargs) or ()
    else:
        times = cmds.keyframe(nodes, q=True) or ()

    # return the key times sorted and unique
    if times:
        return tuple(sorted(set(times)))

    return ()

def iterAtTimes(timeValues):
    """
    provides a generator that visits the given times. ie: the current time is changed
    """
    initialTime = cmds.currentTime(q=True)
    for time in timeValues:
        if time is None:
            continue

        OpenMayaAnim.MAnimControl.setCurrentFrame(time)
        yield time

    cmds.currentTime(initialTime)

class AttributeData(object):
    def __init__(self, attrPath):
        self._value = getAttr(attrPath)

    def apply(self, attrPath, sourceRange, applyStart, additive=False):
        if additive:
            setAttr(attrPath, getAttr(attrPath) + self._value)
        else:
            setAttr(attrPath, self._value)

class KeyframeData(tuple):
    DATA_IDX = TIME, VALUE, ITT, OTT, ITX, ITY, OTX, OTY, BREAKDOWN, TAN_LOCK, WEIGHT_LOCK, WEIGHTED, PRE_INF, POST_INF, CURVE_TYPE = range(
        15)

    def __new__(cls, attrPath):

        # get the anim curve node that drives this attr. We use the keyframe command
        # here because it knows how to find the right node based on the current anim
        # layer if there are any
        animCurveNode = cmds.keyframe(attrPath, q=True, name=True)
        if animCurveNode is None:
            return AttributeData(attrPath)

        animCurveNode = animCurveNode[0]
        times = getAttr('%s.ktv[*].keyTime' % animCurveNode)
        values = getAttr('%s.ktv[*].keyValue' % animCurveNode)

        itt = getAttr('%s.kit[*]' % animCurveNode)
        ott = getAttr('%s.kot[*]' % animCurveNode)

        itx = getAttr('%s.kix[*]' % animCurveNode)
        ity = getAttr('%s.kiy[*]' % animCurveNode)
        otx = getAttr('%s.kox[*]' % animCurveNode)
        oty = getAttr('%s.koy[*]' % animCurveNode)

        brk = getAttr('%s.keyBreakdown[*]' % animCurveNode)
        tlk = getAttr('%s.keyTanLocked[*]' % animCurveNode)
        wlk = getAttr('%s.keyWeightLocked[*]' % animCurveNode)

        # if there is only one value in the array attributes above, maya in its infinite wisdom returns the value as a float, not a single element list.  well done.
        if not isinstance(times, list):
            times = [times]
            values = [values]
            itt = [itt]
            ott = [ott]
            itx = [itx]
            ity = [ity]
            otx = [otx]
            oty = [oty]
            brk = [brk]
            tlk = [tlk]
            wlk = [wlk]

        weighted = getAttr('%s.wgt' % animCurveNode)
        preInf = getAttr('%s.pre' % animCurveNode)
        postInf = getAttr('%s.pst' % animCurveNode)
        curveType = cmds.nodeType(animCurveNode)

        return tuple.__new__(cls, (
            times, values, itt, ott, itx, ity, otx, oty, brk, tlk, wlk, weighted, preInf, postInf, curveType))

    def constructNode(self):
        """
        constructs an animCurve node using the data stored on the instance

        returns the node created
        """
        animCurveNode = createNode(self[self.CURVE_TYPE])

        # massage the time values
        times = self[self.TIME]
        values = self[self.VALUE]
        maxIdxVal = len(values) - 1

        setKeyframe = cmds.setKeyframe
        for time, value in zip(times, values):
            setKeyframe(animCurveNode, t=time, v=value)

        #set key data
        setAttr('%s.wgt' % animCurveNode, self[self.WEIGHTED])
        setAttr('%s.pre' % animCurveNode, self[self.PRE_INF])
        setAttr('%s.pst' % animCurveNode, self[self.POST_INF])

        setAttr('%s.keyBreakdown[0:%d]' % (animCurveNode, maxIdxVal), *self[self.BREAKDOWN])
        setAttr('%s.keyTanLocked[0:%d]' % (animCurveNode, maxIdxVal), *self[self.TAN_LOCK])
        setAttr('%s.keyWeightLocked[0:%d]' % (animCurveNode, maxIdxVal), *self[self.WEIGHT_LOCK])

        setAttr('%s.kix[0:%d]' % (animCurveNode, maxIdxVal), *self[self.ITX])
        setAttr('%s.kiy[0:%d]' % (animCurveNode, maxIdxVal), *self[self.ITY])
        setAttr('%s.kox[0:%d]' % (animCurveNode, maxIdxVal), *self[self.OTX])
        setAttr('%s.koy[0:%d]' % (animCurveNode, maxIdxVal), *self[self.OTY])

        setAttr('%s.kit[0:%d]' % (animCurveNode, maxIdxVal), *self[self.ITT])
        setAttr('%s.kot[0:%d]' % (animCurveNode, maxIdxVal), *self[self.OTT])

        return animCurveNode

    def apply(self, attrPath, sourceRange, applyStart, additive=False):
        """
        used to put the animation data on this instance to an actual attribute

        sourceRange should be a 2-tuple representing the 0-based time range of the
        animation data to apply applyStart should be the start time at which to place
        the animation
        """

        # if the attrPath isn't settable, bail - maya sometimes crashes if you try to
        # pasteKey on a non-settable attr
        if not getAttr(attrPath, se=True):
            return

        copyKwargs = dict(t=sourceRange)
        pasteKwargs = dict(t=(applyStart, applyStart + sourceRange[1] - sourceRange[0]))

        animCurveNode = self.constructNode()
        if additive:
            if cmds.keyframe(attrPath, q=True, kc=True):
                for t in cmds.keyframe(animCurveNode, q=True):
                    val = cmds.keyframe(attrPath, t=(t,), q=True, vc=True, eval=True) or [getAttr(attrPath)]
                    cmds.keyframe(animCurveNode, t=(t,), e=True, vc=val[0], relative=True)
            else:
                cmds.keyframe(animCurveNode, e=True, vc=getAttr(attrPath), relative=True)

        try:
            cmds.copyKey(animCurveNode, clipboard='api', option='keys', **copyKwargs)
            cmds.pasteKey(attrPath, option='replace', clipboard='api', **pasteKwargs)
        finally:
            cmds.delete(animCurveNode)

class NodeKeyServer(object):
    """
    implements iterator protocol to allow easy visiting of keyframes on a
    collection of nodes
    """

    def __init__(self, nodes, visitKeys=True, attrs=None, range=(None, None, None)):
        self._nodes = nodes

        # if True then each key time is actually visted during iteration.
        # Ie: cmds.currentTime is called for each key time
        self._visit = visitKeys

        # stores the attributes to key keys from
        self._attrs = attrs

        # if not None, only keys between the given range (inclusive) will be visited
        self._range = range

        # stores the objects that have a key at each time
        self._timeNodesDict = None

    def _generateTimeNodesDict(self):
        """
        generates a dict keyed by time storing a list of nodes that have keys at that
        particular time

        NOTE: this gets generated at most once for the life of this instance
        """
        if self._timeNodesDict is not None:
            return self._timeNodesDict

        self._timeNodesDict = timeNodesDict = {}

        # pre-compute and store a key set for each node
        nodeKeys = [set(keyTimesFromNodes([n], self._attrs)) for n in self._nodes]

        nodes = self._nodes
        nodesWithKeys = set()
        keyTimes = self.getKeyTimes()
        for keyTime in keyTimes:
            timeNodesDict[keyTime] = nodesAtTime = []

            for node, keys in zip(nodes, nodeKeys):
                if keyTime in keys:
                    nodesWithKeys.add(node)
                    nodesAtTime.append(node)

        timeNodesDict[None] = list(set(nodes).difference(nodesWithKeys))

        return keyTimes, timeNodesDict

    def __iter__(self):
        keyTimes, timeNodesDict = self._generateTimeNodesDict()

        # we yield None first so that if there are nodes without keys they get handled first
        self._currentTime = None
        yield None

        iterFunction = iterAtTimes if self._visit else iter
        startTime, endTime, _ = self._range
        for keyTime in iterFunction(keyTimes):
            if startTime is not None:
                if keyTime < startTime:
                    continue

            self._currentTime = keyTime
            yield keyTime

            if endTime is not None:
                if keyTime > endTime:
                    break

        del self._currentTime

    def getNodes(self):
        """
        returns the list of nodes that are at the time currently being iterated at
        """
        if not hasattr(self, '_currentTime'):
            raise TypeError("Not currently iterating!  You can only query the nodes while iterating")

        return tuple(self._timeNodesDict[self._currentTime])

    def getKeyTimes(self):
        try:
            return self._keyTimes
        except AttributeError:
            pass

        self._keyTimes = keyTimesFromNodes(self._nodes, self._attrs)

        return self._keyTimes

    def getRange(self):
        keyTimes = self.getKeyTimes()

        return keyTimes[0], keyTimes[-1]

class TimeKeyServer(NodeKeyServer):
    def getNodes(self):
        return tuple(self._nodes)

    def getKeyTimes(self):
        start, stop, skip = self._range
        return range(start, stop + 1, skip)

class AttrpathKeyServer(NodeKeyServer):
    def __init__(self, attrpaths, visitKeys=False):
        super(AttrpathKeyServer, self).__init__(attrpaths, visitKeys)

    def _get(self, idx):
        attrpaths = super(AttrpathKeyServer, self).getNodes()
        nodes = set(attrpath.split('.')[idx] for attrpath in attrpaths)

        return tuple(nodes)

    def getNodes(self):
        return self._get(0)

    def getAttrNames(self):
        return self._get(1)

def _getAttrNames(obj, attrNamesToSkip=()):
    """
    returns a list of attribute names on the given node to slurp animation data from.  Attributes will be keyable and
    visible in the channelBox
    """

    # grab attributes
    objAttrs = cmds.listAttr(obj, keyable=True, visible=True, scalar=True) or []

    #also grab alias' - its possible to pass in an alias name, so we need to test against them as well
    aliass = cmds.aliasAttr(obj, q=True) or []

    #because the aliasAttr cmd returns a list with the alias, attr pairs in a flat list, we need to iterate over the list, skipping every second entry
    itAliass = iter(aliass)
    for attr in itAliass:
        objAttrs.append(attr)
        itAliass.next()

    filteredAttrs = []
    for attr in objAttrs:
        skipAttr = False
        for skipName in attrNamesToSkip:
            if attr == skipName:
                skipAttr = True
            elif attr.startswith(skipName + '[') or attr.startswith(skipName + '.'):
                skipAttr = True

        if skipAttr:
            continue

        filteredAttrs.append(attr)

    return filteredAttrs

# defines a mapping between node type, and the function used to get a list of attributes
# from that node to save to the clip.  by default _getAttrNames(obj) is called
GET_ATTR_BY_NODE_TYPE = {
    'blendShape': lambda obj: _getAttrNames(obj, ('envelope', 'weight', 'inputTarget'))
}

def getNodeAttrNames(node):
    nodeType = cmds.nodeType(node)

    return GET_ATTR_BY_NODE_TYPE.get(nodeType, _getAttrNames)(node)

def getPlaybackRange(nodes=None):
    """
    returns a 2-tuple of startTime, endTime.  The values are taken from the visible
    playback unless there is a time selection. If there is a time selection, then
    its range is returned instead
    """
    playbackStart = cmds.playbackOptions(q=True, min=True)
    playbackEnd = cmds.playbackOptions(q=True, max=True)

    # NOTE: timeControl1 is the name of maya's default, global timeControl widget...
    if cmds.timeControl('timeControl1', q=True, rv=True):
        playbackStart, playbackEnd = cmds.timeControl('timeControl1', q=True, rangeArray=True)

    # make sure the time range isn't longer than the actual keys that we have
    if nodes:
        keyTimes = keyTimesFromNodes(nodes) or [playbackStart, playbackEnd]
        playbackStart = max(playbackStart, min(keyTimes))
        playbackEnd = min(playbackEnd, max(keyTimes))

    return playbackStart, playbackEnd

def generateKeyTransformDict(keyTimes, originalRange=(0, None), applyStart=None):
    if applyStart is None:
        applyStart = originalRange[0]

    timeOffset = applyStart - originalRange[0]

    keyTransformDict = {}
    for keyTime in sorted(keyTimes):
        keyTransformDict[keyTime + timeOffset] = keyTime

    return keyTransformDict

class BaseClip(object):
    def setMapping(self, mapping):
        """
        subclasses should implement this - it should change the key for all the data
        stored in the clip to whatever is given in the mapping.  This method should
        return a new Clip with the mapping applied
        """
        raise AnimLibError("BaseClip doesn't know how to set mapping!")

    def getMappingFromNodes(self, nodes, tryFlippedParity=False):
        """
        flipParity will look for a node with the opposite parity if there is no match
        using the actual parity
        """
        clipNodes = self.getNodes()

        # create a mapping from the given nodes to the clip nodes
        matches = str_utils.matchNames(nodes, clipNodes, tryFlippedParity=tryFlippedParity)
        mapping = str_utils.Mapping(nodes, matches)

        # swap the mapping so that it maps clip nodes to actual nodes
        mapping.swap()

        return mapping

    def getMappingFromSelection(self):
        return self.getMappingFromNodes(cmds.ls(sl=True))

    def setMappingFromNodes(self, nodes, tryFlippedParity=False):
        mapping = self.getMappingFromNodes(nodes, tryFlippedParity)
        return self.setMapping(mapping)

    def setMappingFromSelection(self):
        selection = cmds.ls(sl=True) or []
        return self.setMappingFromNodes(selection)

    def applyToNodes(self, nodes, *a, **kw):
        self.setMappingFromNodes(nodes).apply(nodes, *a, **kw)

    def applyToSelection(self, *a, **kw):
        selection = cmds.ls(sl=True) or []
        self.applyToNodes(selection, *a, **kw)

def eulerFilterNodes(nodes):
    for node in nodes:
        cmds.filterCurve('%s.rx' % node, '%s.ry' % node, '%s.rz' % node, filter='euler')

class TransformClip(BaseClip):
    """
    stores world space transform data for the given list of nodes
    """
    _ATTRS = ('t', 'r')

    @classmethod
    def Generate(cls, nodes):
        originalRange = getPlaybackRange(nodes)
        keyTimeDataDict = {}

        nodesWithKeys = set()

        attrs = cls._ATTRS
        keyServer = NodeKeyServer(nodes, attrs=attrs)
        for keyTime in keyServer:
            nodesAtTime = keyServer.getNodes()
            keyTimeDataDict[keyTime] = nodeDataDict = {}
            for node in nodesAtTime:
                nodesWithKeys.add(node)

                # skip non-transform nodes...  duh
                if not cmds.objectType(node, isAType='transform'):
                    continue

                pos = xform(node, q=True, ws=True, rp=True)
                rot = xform(node, q=True, ws=True, ro=True)
                nodeDataDict[node] = pos, rot, getAttr('%s.ro' % node)

        return cls(keyTimeDataDict, originalRange)

    def __init__(self, keyTimeDataDict, originalRange):
        self._originalRange = originalRange
        self._keyTimeDataDict = keyTimeDataDict

    def getNodes(self):
        nodes = set()
        for _x, nodeDataDict in self._keyTimeDataDict.iteritems():
            nodes.update(set(nodeDataDict.keys()))

        return list(nodes)

    def getPostProcessCmdDict(self):
        cmdDict = {}
        for node in self.getNodes():
            postProcessCmdAttrpath = '%s.xferPostTraceCmd' % node
            if objExists(postProcessCmdAttrpath):
                cmdDict[node] = getAttr(postProcessCmdAttrpath)

        return cmdDict

    def setMapping(self, mapping):
        newKeyTimeDataDict = {}
        for _t, nodeDict in self._keyTimeDataDict.iteritems():
            newNodeDict = {}
            for src, tgt in mapping.iteritems():
                if not tgt:
                    continue

                if src in nodeDict:
                    newNodeDict[tgt] = nodeDict[src]

            if newNodeDict:
                newKeyTimeDataDict[_t] = newNodeDict

        return TransformClip(newKeyTimeDataDict, self._originalRange)

    @maya_decorators.d_noAutoKey
    @maya_decorators.d_maintainSceneSelection
    def apply(self, nodes=None, applyStart=None, additive=False):
        if nodes is None:
            nodes = self.getNodes()

        if applyStart is None:
            applyStart = cmds.currentTime(q=True)

        if not nodes:
            return

        # this is a touch ugly - but we want to make a copy of the keyTimeDict because
        # we want to pop out the None value before transforming the key times
        keyTimeDataDict = {}
        keyTimeDataDict.update(self._keyTimeDataDict)

        nodesWithoutKeys = keyTimeDataDict.pop(None, [])

        attrs = self._ATTRS
        keyTimes = sorted(keyTimeDataDict.keys())

        postCmdDict = self.getPostProcessCmdDict()

        # ok so this is a little ugly - not sure how to make it cleaner however.  Anyhoo,
        # here we need to transform the key times but we need the original key times
        # because we use them as a lookup to the nodes with keys at that time...  so we
        # build a dictionary to store the mapping
        transformedKeyTimes = generateKeyTransformDict(keyTimes, self._originalRange, applyStart)
        sortedKeyTimes = sorted(transformedKeyTimes.keys())

        for transformedKeyTime in iterAtTimes(sortedKeyTimes):
            keyTime = transformedKeyTimes[transformedKeyTime]
            nodesAtTimeDict = self._keyTimeDataDict[keyTime]
            for node, (pos, rot, storedRotateOrder) in nodesAtTimeDict.iteritems():
                move(pos[0], pos[1], pos[2], node, ws=True, a=True, rpr=True)

                roAttrpath = '%s.ro' % node
                initialRotateOrder = getAttr(roAttrpath)
                rotateOrderMatches = initialRotateOrder == storedRotateOrder

                # if the rotation order is different, we need to compensate. we check
                # because its faster if we don't have to compensate
                if rotateOrderMatches:
                    rotate(rot[0], rot[1], rot[2], node, ws=True, a=True)
                else:
                    setAttr('%s.ro' % node, storedRotateOrder)
                    rotate(rot[0], rot[1], rot[2], node, ws=True, a=True)
                    xform(node, rotateOrder=constants.MAYA_ROTATE_ORDER_STRS[initialRotateOrder], preserve=True)

                if keyTime is not None:
                    setKeyframe(node, t=(transformedKeyTime,), at=attrs)

        # make sure to filter rotation curves
        eulerFilterNodes(nodes)

class AttrMask(object):
    def __init__(self, attrNames, inclusive=True):
        self._attrNames = set(attrNames)
        self._inclusive = inclusive

    def __contains__(self, attrName):
        return (attrName in self._attrNames) == self._inclusive

class ChannelClip(BaseClip):
    """
    stores raw keyframe data for all animated channels on the given list of nodes
    """

    @classmethod
    def Generate(cls, nodes):
        """
        generates a new AnimClip instance from the given list of nodes
        """
        originalRange = getPlaybackRange(nodes)
        nodeDict = {}
        for node in nodes:
            nodeDict[node] = dataDict = {}
            for attrName in getNodeAttrNames(node):
                dataDict[attrName] = KeyframeData('%s.%s' % (node, attrName))

        return cls(nodeDict, originalRange)

    def __init__(self, nodeDict, originalRange):
        self._originalRange = originalRange
        self._nodeDict = nodeDict

    def getNodes(self):
        return self._nodeDict.keys()

    def getChannels(self):
        """
        returns a list of channel names in the clip
        """
        channels = set()
        for node, data in self._nodeDict.iteritems():
            for attrname in data.iterkeys():
                channels.add(attrname)

        return channels

    def setMapping(self, mapping):
        newNodeDict = {}
        for src, tgt in mapping.iteritems():
            if src in self._nodeDict:
                newNodeDict[tgt] = self._nodeDict[src]

        return ChannelClip(newNodeDict, self._originalRange)

    @maya_decorators.d_noAutoKey
    @maya_decorators.d_maintainSceneSelection
    def apply(self, nodes=None, applyStart=None, additive=False, attrMask=None):
        """
        will apply the animation data stored in this clip to the given mapping targets

        applySettings expects an AnimClip.ApplySettings instance or None
        """
        if nodes is None:
            nodes = self._nodeDict.keys()

        if applyStart is None:
            applyStart = cmds.currentTime(q=True)

        for node in nodes:
            if node in self._nodeDict:
                dataDict = self._nodeDict[node]
                for attrName, keyData in dataDict.iteritems():

                    # check to see if the attribute is in the attribute mask
                    if attrMask is not None:
                        if attrName not in attrMask:
                            continue

                    attrPath = '%s.%s' % (node, attrName)
                    try:
                        keyData.apply(attrPath, self._originalRange, applyStart, additive)

                    # usually happens if the attrPath doesn't exist or is locked...
                    except RuntimeError:
                        continue

def getKeyedRange(nodes):
    keyTimes = keyTimesFromNodes(nodes)
    if keyTimes:
        return min(keyTimes), max(keyTimes)

    t = cmds.currentTime(q=True)

    return t, t

class AnimClip(BaseClip):
    """
    stores both a ChannelClip instance and a TransformClip instance for the given list of nodes
    """

    @classmethod
    def Generate(cls, nodes, worldSpace=True):

        # without the merge anim layer context here, only animation for the current
        # anim layer will be written to the clip. Of course, if there are no anim
        # layers, then everything just works
        with MergeAnimLayerContext():
            with BakeConstrainedContext(nodes):
                channelClip = ChannelClip.Generate(nodes)
                transformClip = None
                if worldSpace:
                    transformClip = TransformClip.Generate(
                        [node for node in nodes if cmds.objectType(node, isAType='transform')])

                return cls(channelClip, transformClip)

    def __init__(self, channelClip, transformClip):
        self._channelClip = channelClip
        self._transformClip = transformClip

    @property
    def hasWorldSpaceData(self):
        return bool(self._transformClip)

    def getNodes(self):
        nodes = self._channelClip.getNodes()
        if self._transformClip:
            nodes += self._transformClip.getNodes()

        return list(set(nodes))

    def getChannels(self):
        """
        returns a list of channel names in the clip
        """
        return self._channelClip.getChannels()

    def getClipRange(self):
        times = []
        for data in self._channelClip._nodeDict.itervalues():
            for keyData in data.itervalues():
                if isinstance(keyData, KeyframeData):
                    times.extend(keyData[0])

        if times:
            return min(times), max(times)

        # happens if the "anim clip" was saved using nodes with no keys...
        return 0, 0

    def getFrameCount(self):
        rng = self.getClipRange()

        return rng[1] - rng[0]

    def setMapping(self, mapping):
        cc = self._channelClip.setMapping(mapping)
        if self._transformClip:
            return AnimClip(cc, self._transformClip.setMapping(mapping))

        return AnimClip(cc, None)

    def apply(self, nodes=None, applyStart=None, worldSpace=False, additive=False):
        if applyStart is None:
            applyStart = cmds.currentTime(q=True)

        self._channelClip.apply(nodes, applyStart, additive)
        if worldSpace and self._transformClip:
            self._transformClip.apply(nodes, applyStart, additive)

class PoseClip(BaseClip):
    @classmethod
    def Generate(cls, nodes, worldSpace=True):
        """
        generates a new AnimClip instance from the given list of nodes
        """
        nodeDict = {}
        worldNodeDict = {}
        for node in nodes:
            nodeDict[node] = dataDict = {}
            for attrName in getNodeAttrNames(node):
                dataDict[attrName] = getAttr('%s.%s' % (node, attrName))

            if worldSpace:
                if cmds.objectType(node, isAType='transform'):
                    pos = xform(node, q=True, ws=True, rp=True)
                    rot = xform(node, q=True, ws=True, ro=True)
                    worldNodeDict[node] = pos, rot, getAttr('%s.ro' % node)

        return cls(nodeDict, worldNodeDict)

    def __init__(self, attrDict, worldAttrDict):
        self._nodeAttrDict = attrDict
        self._nodeWorldDict = worldAttrDict

    @property
    def hasWorldSpaceData(self):
        return bool(self._nodeWorldDict)

    def getNodes(self):
        return self._nodeAttrDict.keys()

    def getChannels(self):
        """
        returns a list of channel names in the clip
        """
        channels = set()
        for node, data in self._nodeAttrDict.iteritems():
            for attrname in data.iterkeys():
                channels.add(attrname)

        return channels

    def setMapping(self, mapping):
        assert isinstance(mapping, str_utils.Mapping)
        newNodeAttrDict = {}
        newNodeWorldDict = {}
        for src, tgt in mapping.iteritems():
            if not tgt:
                continue

            if src in self._nodeAttrDict:
                newNodeAttrDict[tgt] = self._nodeAttrDict[src]

            if src in self._nodeWorldDict:
                newNodeWorldDict[tgt] = self._nodeWorldDict[src]

        return PoseClip(newNodeAttrDict, newNodeWorldDict)

    @maya_decorators.d_maintainSceneSelection
    def apply(self, nodes=None, applyStart=None, worldSpace=False, additive=False, attrMask=None):
        if nodes is None:
            nodes = self._nodeAttrDict.iterkeys()

        for node in nodes:
            if node in self._nodeAttrDict:
                for attrName, value in self._nodeAttrDict[node].iteritems():

                    # check to see if the attribute is in the attribute mask
                    if attrMask is not None:
                        if attrName not in attrMask:
                            continue

                    attrpath = '%s.%s' % (node, attrName)
                    if objExists(attrpath) and not getAttr(attrpath, lock=True):
                        if additive:
                            value += getAttr(attrpath)

                        setAttr(attrpath, value, clamp=True)

            if worldSpace:
                if node in self._nodeWorldDict:
                    if cmds.objectType(node, isAType='transform'):
                        pos, rot, rotateOrder = self._nodeWorldDict[node]
                        if additive:
                            pos = Vector(pos) + Vector(xform(node, q=True, ws=True, rp=True))

                        move(pos[0], pos[1], pos[2], node, ws=True, a=True, rpr=True)

                        roAttrpath = '%s.ro' % node
                        initialRotateOrder = getAttr(roAttrpath)
                        rotateOrderMatches = initialRotateOrder == rotateOrder

                        if rotateOrderMatches:
                            if additive:
                                rot = Vector(rot) + Vector(xform(node, q=True, ws=True, ro=True))

                            rotate(rot[0], rot[1], rot[2], node, ws=True, a=True)
                        else:
                            if additive:
                                xform(node, ro=constants.MAYA_ROTATE_ORDER_STRS[rotateOrder], p=True)
                                rot = Vector(rot) + Vector(xform(node, q=True, ws=True, ro=True))

                            setAttr(roAttrpath, rotateOrder)
                            rotate(rot[0], rot[1], rot[2], node, ws=True, a=True)
                            xform(node, ro=constants.MAYA_ROTATE_ORDER_STRS[initialRotateOrder], p=True)

    def blend(self, other, amount, additive=False):
        if not isinstance(other, PoseClip):
            raise TypeError("Can only blend to another PoseClip instance")

        # this simplifies the code below as we don't have to check which values exist in one dict and not the other
        for key, value in self._nodeAttrDict.iteritems():
            other._nodeAttrDict.setdefault(key, value)

        for key, value in other._nodeAttrDict.iteritems():
            self._nodeAttrDict.setdefault(key, value)

        # build new dicts by blending values from the two clips
        newNodeAttrDict = {}
        for node, nodeAttrDict in self._nodeAttrDict.iteritems():
            otherNodeAttrDict = other._nodeAttrDict[node]
            newNodeAttrDict[node] = newAttrDict = {}
            for attr, value in nodeAttrDict.iteritems():
                if attr in otherNodeAttrDict:
                    otherValue = otherNodeAttrDict[attr]
                else:
                    otherValue = value

                if additive:
                    newAttrDict[attr] = value + (otherValue * amount)
                else:
                    newAttrDict[attr] = (value * (1 - amount)) + (otherValue * amount)

        newWorldAttrDict = {}
        for node, (pos, rot, ro) in self._nodeWorldDict.iteritems():
            if node in other._nodeWorldDict:
                otherPos, otherRot, otherRo = other._nodeWorldDict[node]
                # if ro != otherRo things get a bit more complicated...
                if additive:
                    blendedPos = Vector(pos) + (Vector(otherPos) * amount)

                    # NOTE: this does a simple lerp toward the other rotation in euler
                    # space. This is obviously a shit way to do it. Consider converting
                    # this to use quats a TODO
                    blendedRot = Vector(rot) + (Vector(otherRot) * amount)
                else:
                    blendedPos = (Vector(pos) * (1 - amount)) + (Vector(otherPos) * amount)

                    # NOTE: like the note above, this rotation blend is being done in
                    # euler space. TODO: use quats!
                    blendedRot = (Vector(rot) * (1 - amount)) + (Vector(otherRot) * amount)

                newWorldAttrDict[node] = list(blendedPos), list(blendedRot), ro

        return PoseClip(newNodeAttrDict, newWorldAttrDict)

def generateClipFromSelection(clipType=AnimClip, worldSpace=False):
    return clipType.Generate(cmds.ls(sl=True), worldSpace)

class TangencyCopier(object):
    """
    manages copying tangency information from one animCurve to another.  It refers to keys using key times
    not key indices so it works to some degree even if the two animCurves are quite different
    """

    def __init__(self, srcAttrpath, tgtAttrpath):
        srcAnimCurve, tgtAnimCurve = None, None
        srcCurves = cmds.listConnections(srcAttrpath, type='animCurve', d=False)
        if srcCurves:
            srcAnimCurve = srcCurves[0]

        tgtCurves = cmds.listConnections(tgtAttrpath, type='animCurve', d=False)
        if tgtCurves:
            tgtAnimCurve = tgtCurves[0]

        self._src = srcAnimCurve
        self._tgt = tgtAnimCurve

    def iterSrcTgtKeyIndices(self, start=None, end=None):
        src, tgt = self._src, self._tgt
        srcIndices = getAttr('%s.keyTimeValue' % src, multiIndices=True) or []
        tgtIndices = getAttr('%s.keyTimeValue' % tgt, multiIndices=True) or []

        srcTimeValues = getAttr('%s.keyTimeValue[*]' % src) or []
        tgtTimeValues = getAttr('%s.keyTimeValue[*]' % tgt) or []

        tgtDataDict = {}
        for tgtIdx, (tgtTime, tgtValue) in zip(tgtIndices, tgtTimeValues):
            tgtDataDict[tgtTime] = tgtIdx, tgtValue

        for srcIdx, (srcTime, srcValue) in zip(srcIndices, srcTimeValues):

            # keep looping if a start time has been specified AND the time being visited comes before this time
            if start is not None and srcTime < start:
                continue

            #break out of the loop if an end time has been specified AND the time being visited comes after this time
            if end is not None and srcTime > end:
                break

            #check to see if a key exists on the tgt at the time being visited
            if srcTime in tgtDataDict:
                yield (srcIdx, srcValue), tgtDataDict[srcTime]

    def copy(self, start=None, end=None):
        src, tgt = self._src, self._tgt
        if src is None or tgt is None:
            return

        setAttr('%s.weightedTangents' % tgt, getAttr('%s.weightedTangents' % src))
        for srcData, tgtData in self.iterSrcTgtKeyIndices(start, end):
            srcIdx, srcValue = srcData
            tgtIdx, tgtValue = tgtData

            setAttr('%s.keyTanLocked[%d]' % (tgt, tgtIdx), getAttr('%s.keyTanLocked[%d]' % (src, srcIdx)))
            setAttr('%s.keyWeightLocked[%d]' % (tgt, tgtIdx), getAttr('%s.keyWeightLocked[%d]' % (src, srcIdx)))
            setAttr('%s.keyTanInX[%d]' % (tgt, tgtIdx), getAttr('%s.keyTanInX[%d]' % (src, srcIdx)))
            setAttr('%s.keyTanInY[%d]' % (tgt, tgtIdx), getAttr('%s.keyTanInY[%d]' % (src, srcIdx)))
            setAttr('%s.keyTanOutX[%d]' % (tgt, tgtIdx), getAttr('%s.keyTanOutX[%d]' % (src, srcIdx)))
            setAttr('%s.keyTanOutY[%d]' % (tgt, tgtIdx), getAttr('%s.keyTanOutY[%d]' % (src, srcIdx)))
            setAttr('%s.keyTanInType[%d]' % (tgt, tgtIdx), getAttr('%s.keyTanInType[%d]' % (src, srcIdx)))
            setAttr('%s.keyTanOutType[%d]' % (tgt, tgtIdx), getAttr('%s.keyTanOutType[%d]' % (src, srcIdx)))
            setAttr('%s.keyBreakdown[%d]' % (tgt, tgtIdx), getAttr('%s.keyBreakdown[%d]' % (src, srcIdx)))

class Tracer(object):
    """
    does intra-scene tracing
    """

    def __init__(self, keysOnly=True, processPostCmds=True, start=None, end=None, skip=1):

        # if start and end haven't been specified, then we assume the user wants the
        # current timeline baked
        if start is None:
            start = cmds.playbackOptions(q=True, min=True)

        if end is None:
            end = cmds.playbackOptions(q=True, max=True)

        self._keysOnly = keysOnly
        self._processPostCmds = processPostCmds
        self._start = int(start)
        self._end = int(end)
        self._skip = int(skip)

    def _getTargetNodeInitialRotateOrderDict(self, mapping, traceSourceMap=None):
        targetNodeInitialRotateOrderDict = {}

        # pre-lookup this data - otherwise we have to do a maya query within the loop below
        for node, targetNode in mapping.iteritems():
            if traceSourceMap:
                sourceNode = traceSourceMap[node]
                if sourceNode:
                    node = sourceNode[0]

            storedRotateOrder = getAttr('%s.ro' % node)
            targetRotateOrder = getAttr('%s.ro' % targetNode)
            rotateOrderMatches = storedRotateOrder == targetRotateOrder
            targetNodeInitialRotateOrderDict[targetNode] = rotateOrderMatches, storedRotateOrder, \
                                                           constants.MAYA_ROTATE_ORDER_STRS[targetRotateOrder]

        return targetNodeInitialRotateOrderDict

    @maya_decorators.d_noAutoKey
    @maya_decorators.d_maintainSceneSelection
    def apply(self, mapping, copyTangencyData=True, traceSourceMap=None):
        """
        If a keyMapping is passed then it is used to determine keytimes on which to trace.

        The use case here - say you want to trace skeletal animation to a rig.  The skeleton doesn't have keys
        on it directly because its being driven procedurally, or by some other rig.  You can use the keyMapping
        to provide the
        """
        if not isinstance(mapping, str_utils.Mapping):
            mapping = str_utils.Mapping(*mapping)

        targetNodeInitialRotateOrderDict = self._getTargetNodeInitialRotateOrderDict(mapping, traceSourceMap)
        postCmdDict = {}
        if self._processPostCmds:
            for tgt in mapping.tgts:
                postCmdDict[tgt] = PostTraceNode(tgt)

        keyServer = TimeKeyServer(mapping.keys(), range=(self._start, self._end, self._skip))

        startTime = None
        for keyTime in keyServer:
            if startTime is None:
                startTime = keyTime

            nodesAtTime = keyServer.getNodes()
            for node in nodesAtTime:
                targetNodes = mapping[node]

                if traceSourceMap is not None:
                    sourceNode = traceSourceMap[node]
                    if sourceNode:
                        node = sourceNode[0]

                if not targetNodes:
                    continue

                pos = xform(node, q=True, ws=True, rp=True)
                rot = xform(node, q=True, ws=True, ro=True)
                for targetNode in targetNodes:
                    move(pos[0], pos[1], pos[2], targetNode, ws=True, a=True, rpr=True)

                    rotateOrderMatches, storedRotateOrder, targetRotateOrderStr = targetNodeInitialRotateOrderDict[
                        targetNode]

                    # if the rotation order is different, we need to compensate - we check because its faster if we don't have to compensate
                    if rotateOrderMatches:
                        rotate(rot[0], rot[1], rot[2], targetNode, ws=True, a=True)
                    else:
                        setAttr('%s.ro' % targetNode, storedRotateOrder)
                        rotate(rot[0], rot[1], rot[2], targetNode, ws=True, a=True)
                        xform(targetNode, rotateOrder=targetRotateOrderStr, preserve=True)

                    if targetNode in postCmdDict:
                        postCmdDict[targetNode].execute(node)

                if keyTime is not None:
                    setKeyframe(targetNodes, time=keyTime, at=TransformClip._ATTRS)

        # filter the traced curves
        for src, tgt in mapping.iteritems():
            cmds.filterCurve(tgt + '.rx', tgt + '.ry', tgt + '.rz')

        if self._keysOnly:
            keyTimes = keyServer.getKeyTimes()
            _, timeNodesDict = NodeKeyServer(mapping.keys(), False)._generateTimeNodesDict()
            targetNodes = set(mapping.values())
            for keyTime in keyTimes:
                if keyTime is None:
                    continue

                nodesWithKeysAtThisTime = []
                for srcNode in timeNodesDict.get(keyTime, []):
                    nodesWithKeysAtThisTime += mapping[srcNode]

                nodesWithoutKeys = targetNodes.difference(set(nodesWithKeysAtThisTime))
                if nodesWithoutKeys:
                    cmds.cutKey(list(nodesWithoutKeys), t=(keyTime,), cl=True)

        endTime = keyTime
        if copyTangencyData:
            for src, tgt in mapping.iteritems():

                if traceSourceMap is not None:
                    sourceNode = traceSourceMap[node]
                    if sourceNode:
                        src = sourceNode[0]

                srcCurves = cmds.listConnections(src, type='animCurve', d=False, c=True) or []
                iterSrcCurves = iter(srcCurves)
                for srcAttrpath in iterSrcCurves:
                    srcCurve = iterSrcCurves.next()
                    attrname = '.'.join(srcAttrpath.split('.')[1:])
                    destAttrpath = '%s.%s' % (tgt, attrname)
                    if cmds.objExists(destAttrpath):
                        TangencyCopier(srcAttrpath, destAttrpath).copy(startTime, endTime)

def bakeManualRotateDelta(src, ctrl, presetStr):
    """
    When you need to apply motion from a skeleton that is completely different from a skeleton driven
    by the rig you're working with (transferring motion from old assets to newer assets for example)
    you can manually align the control to the joint and then use this function to generate offset
    rotations and bake a post trace cmds.
    """
    srcInvMat = Matrix(getAttr('%s.worldInverseMatrix' % src))
    ctrlMat = Matrix(getAttr('%s.worldMatrix' % ctrl))

    # generate the offset matrix as
    mat_o = ctrlMat * srcInvMat

    #now figure out the euler rotations for the offset
    ro = getAttr('%s.ro' % ctrl)
    rotDelta = constants.MATRIX_ROTATION_ORDER_CONVERSIONS_TO[ro](mat_o, True)

    #now get the positional delta
    posDelta = Vector(xform(src, q=True, ws=True, rp=True)) - Vector(xform(ctrl, q=True, ws=True, rp=True))
    posDelta *= -1
    ctrlParentInvMat = Matrix(getAttr('%s.parentInverseMatrix' % ctrl))
    posDelta = posDelta * ctrlParentInvMat

    #construct a list to use for the format str
    formatArgs = tuple(rotDelta) + tuple(posDelta)

    #build the post trace cmd str only if any of the values are non-zero
    if any(formatArgs):
        PostTraceNode(ctrl).setCmd(presetStr % formatArgs)

    return rotDelta

def autoGeneratePostTraceScheme(mapping):
    cmdStr = '''try: cmds.rotate(%0.2f, %0.2f, %0.2f, "{self}", r=True, os=True)
except: pass
try: cmds.move(%0.5f, %0.5f, %0.5f, "{self}", r=True, os=True)
except: pass'''

    cmdFunc = bakeManualRotateDelta

    for src, tgt in mapping.iteritems():
        cmdFunc(src, tgt, cmdStr)

def anchorRotationKeys(nodes):
    """
    Ensures all rotation channels have keys if any of them have keys. That is to
    say that if rx has a key at time 10, this function will ensure that ry and rz
    also have keys at that time. This is useful when manipulating rotations
    """
    for node in nodes:
        attrpath = '%s.r' % node
        if cmds.objExists(attrpath):
            keyTimes = set(cmds.keyframe(attrpath, q=True))
            for t in keyTimes:
                cmds.setKeyframe(attrpath, t=t, insert=True)

class PostTraceNode(unicode):
    _POST_TRACE_ATTR_NAME = 'xferPostTraceCmd'

    def __new__(cls, node):
        new = unicode.__new__(cls, node)
        try:
            new._cmdStr = getAttr('%s.%s' % (node, cls._POST_TRACE_ATTR_NAME))
        except ValueError:
            new._cmdStr = ''

        return new

    def getCmd(self):
        return self._cmdStr

    def setCmd(self, cmdStr):
        self._cmdStr = cmdStr
        attrpath = '%s.%s' % (self, self._POST_TRACE_ATTR_NAME)
        if not cmds.objExists(attrpath):
            cmds.addAttr(self, ln=self._POST_TRACE_ATTR_NAME, dt='string')

        setAttr(attrpath, cmdStr, typ='string')

    def execute(self, destinationNode, connects=()):
        if self._cmdStr:
            cmdStr = self._cmdStr.format(*connects, self=self, dest=destinationNode, connects=connects)
            logger.debug('Executing selection cmd %r: %s' % (self, cmdStr))

            try:
                exec cmdStr
            except:
                logger.error("Failed to execute post trace command on %r" % self, exc_info=True)

    def clear(self):
        deleteAttr('%s.%s' % (self, self._POST_TRACE_ATTR_NAME))

class AnimCurveDuplicator(object):
    """
    deals with duplicating anim curves
    """

    def __init__(self, instanceCurves=False, matchRotateOrder=True):
        self._instance = instanceCurves
        self._matchRo = matchRotateOrder

    @maya_decorators.d_maintainSceneSelection
    def apply(self, mapping):
        for src, tgt in mapping.iteritems():
            for attrname in getNodeAttrNames(src):
                tgtAttrpath = '%s.%s' % (tgt, attrname)
                if objExists(tgtAttrpath):
                    srcAttrpath = '%s.%s' % (src, attrname)
                    srcCurve = cmds.listConnections(srcAttrpath, type='animCurve', d=False)
                    if srcCurve:
                        srcCurve = srcCurve[0]
                        if not self._instance:
                            srcCurve = cmds.duplicate(srcCurve)[0]

                        cmds.connectAttr('%s.output' % srcCurve, tgtAttrpath, f=True)

            if self._matchRo:
                tgtRoAttrpath = '%s.ro' % tgt
                if objExists(tgtRoAttrpath):
                    srcRoAttrpath = '%s.ro' % tgt
                    if objExists(srcRoAttrpath):
                        setAttr(tgtRoAttrpath, getAttr(srcRoAttrpath))

class BakeContext(object):
    """
    bakes animation for nodes on context enter and restores original key times on exit

    This allows clients to perform complex rig transforms without having to worry
    about key micro-management
    """

    def __init__(self, nodes, start=None, end=None):
        self._nodes = apiExtensions.castToMObjects(nodes)
        self._start = start
        self._end = end
        self._allKeyTimes = None
        self._excludeOnExit = []

    def cropKeyTimes(self, times):

        # sort and remove duplicate times
        times = list(set(times))
        times.sort()

        start = self._start
        end = self._end

        croppedTimes = []
        for time in times:
            if start is not None and time < start:
                continue

            # because times are sorted, break if the key time is greater than the end time
            if end is not None and time > end:
                break

            croppedTimes.append(time)

        return croppedTimes

    def getKeyTimes(self, attrpath):
        return self.cropKeyTimes(cmds.keyframe(str(attrpath), q=True) or [])

    def exclude(self, node):
        self._excludeOnExit.append(node)

    def __iter__(self):
        return iterAtTimes(self._allKeyTimes)

    def __enter__(self):
        self._nodeAttrKeyTimeDicts = nodeAttrKeyTimeDicts = []
        for node in self._nodes:
            attrKeyTimeDict = {}
            nodeAttrKeyTimeDicts.append(attrKeyTimeDict)

            attrs = node.iterAttrs(True, True, settable=True)
            for attr in attrs:
                times = self.getKeyTimes(attr)
                attrKeyTimeDict[attr] = times

        # Query all the key times and crop them to the desired range
        self._allKeyTimes = self.cropKeyTimes(cmds.keyframe(self._nodes, q=True) or [])

        # If no keys are present, operate on the current time
        if not self._allKeyTimes:
            self._allKeyTimes = [cmds.currentTime(q=True)]

        # now that we have stored the original key times, put a key on all controls
        # for any frame that any control has a key on.
        # ie: if any has a key on a frame, make sure ALL controls have a key on that
        # frame
        for time in self._allKeyTimes:
            cmds.setKeyframe(self._nodes, insert=True)

        return self

    def __exit__(self, *exc_info):
        for attrKeyTimeDict in self._nodeAttrKeyTimeDicts:
            for attr, originalTimes in attrKeyTimeDict.iteritems():
                attrpath = str(attr)
                node, attrname = attrpath.split('.')
                if node in self._excludeOnExit:
                    continue

                originalTimes = set(originalTimes)
                currentKeyTimes = self.getKeyTimes(attrpath)

                # ok so this is weird - seems like a maya bug.  But if there were no keys on the attribute
                # on context entry, then this set will be empty.  When all the keys are removed from it
                # using the cutKey command, maya for some reason sets the value to 0 instead of keeping
                # its value...  so we have to handle this case ourselves
                # NOTE: we need to do this on context exit because the initial value of the attribute may
                # have changed within the context scope
                originalValue = None
                if not originalTimes:
                    originalValue = cmds.getAttr(attrpath)

                for time in currentKeyTimes:
                    if time not in originalTimes:
                        cmds.cutKey(attrpath, t=(time,), cl=True)

                if originalValue is not None:
                    cmds.setAttr(attrpath, originalValue)

    @property
    def startKeyTime(self):
        return self._allKeyTimes[0]

    @property
    def endKeyTime(self):
        return self._allKeyTimes[-1]

def mergeAnimLayers(animLayers):
    """
    merges all anim layers in the scene

    returns the name of the layer everything was merged into
    """

    # we never want the original layers deleted - it would be polite to restore
    # this option var afterwards but... fuck it
    cmds.optionVar(iv=('animLayerMergeDeleteLayers', False))
    cmds.optionVar(fv=('animLayerMergeByTime', 1))

    # store all the layers before doing the merge so we can figure out which layer
    # is the merged one...
    allLayers = set(cmds.ls(type='animLayer'))

    # call the anim layers merge mel command (ugh!)
    mel_utils.MEL.Source('performAnimLayerMerge')
    mel_utils.MEL.animLayerMerge(animLayers)

    newLayers = set(cmds.ls(type='animLayer')).difference(allLayers)
    if len(newLayers) != 1:
        raise AnimLibError("Weird - this shouldn't happen...")

    return newLayers.pop()

class MergeAnimLayerContext(object):
    """
    merges all anim layers to a temp layer on entry and removes on exit
    """
    _layerName = '__zooMergeAnimLayerContext'

    def __enter__(self):

        # check to see if the merged layer exists - if it does, this instance is
        # probably nested within another MergeAnimLayerContext
        self._skipDelete = cmds.objExists(self._layerName)

        animLayers = cmds.ls(type='animLayer')
        if not animLayers:
            self._skipDelete = True

        if self._skipDelete:
            return

        # before merging, grab the layer mute states. Merging mutes existing layers
        # so we need to restore the entry states on exit
        self._initialMuteStates = dict((l, cmds.animLayer(l, q=True, mute=True)) for l in animLayers)

        # perform the merge and rename the merged layer appropriately
        mergedLayer = mergeAnimLayers(animLayers)
        cmds.rename(mergedLayer, self._layerName)

        mel_utils.MEL.Source('buildSetAnimLayerMenu')
        mel_utils.MEL.selectLayer(self._layerName)

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            logger.error('failure in %s exit method' % type(self).__name__, exc_info=True)

        # only delete the layer if skip isn't True
        if not self._skipDelete:
            if cmds.objExists(self._layerName):
                cmds.delete(self._layerName)

            for l, state in self._initialMuteStates.iteritems():
                cmds.animLayer(l, e=True, mute=state)

        return True

def _shouldBake(node, attrname):
    attrpath = '%s.%s' % (node, attrname)

    # if the attrpath isn't settable then bake it
    if not cmds.getAttr(attrpath, se=True):
        return attrpath

    # if the attrpath is constrained then bake it
    if cmds.listConnections(attrpath, d=False, type='constraint'):
        return attrpath

class BakeConstrainedContext(object):
    """
    bakes animation for any node that is constrained and restores the result of
    the bake on exit
    """

    def __init__(self, nodes):
        self._nodes = nodes

    @maya_decorators.d_undoBlock
    def __enter__(self):

        # store the attrpaths that we need to bake here
        self._attrpathsToBake = []

        # store the original connections to the above attrpaths so we can restore
        # on exit
        self._originalConnections = []

        # now find the list of attrpaths to bake
        for n in self._nodes:
            shouldBakeTest = lambda attrpath: _shouldBake(n, attrpath)

            # for all keyable attrs, see if any aren't settable
            self._attrpathsToBake += filter(
                lambda p: p,
                map(shouldBakeTest, getNodeAttrNames(n)))

        if self._attrpathsToBake:

            # store the original connections for each attrpath
            for attrpath in self._attrpathsToBake:
                cons = cmds.listConnections(attrpath, d=False, p=True, skipConversionNodes=True)
                if cons:
                    self._originalConnections += cons

            # get the time range that we need to bake
            timeRange = getPlaybackRange(self._nodes)

            # call the bakeResults command
            cmds.bakeResults(
                self._attrpathsToBake,
                t=timeRange,
                smart=(True, 0.05),
                )

    def __exit__(self, exc_type, exc_value, traceback):
        # cmds.undo()
        for attrpath, originalConnection in zip(self._attrpathsToBake, self._originalConnections):

            # this should always work - the bake should have created an anim curve on
            # each attrpath, so we don't need to check anything here... I think
            cmds.delete(cmds.keyframe(attrpath, q=True, name=True))

            # re-connect the original connection and we're done!
            cmds.connectAttr(originalConnection, attrpath)

        # delete the instance attrs
        del self._attrpathsToBake
        del self._originalConnections

def storeWorldPose(controls):
    poseXformData = []
    for control in controls:
        pos = cmds.xform(control, q=True, ws=True, rp=True)
        rot = cmds.xform(control, q=True, ws=True, ro=True)
        poseXformData.append((control, pos, rot))

    return poseXformData

def restoreWorldPose(poseData):
    for control, pos, rot in poseData:
        cmds.move(pos[0], pos[1], pos[2], control, ws=True, rpr=True)
        cmds.rotate(rot[0], rot[1], rot[2], control, ws=True)

#end
