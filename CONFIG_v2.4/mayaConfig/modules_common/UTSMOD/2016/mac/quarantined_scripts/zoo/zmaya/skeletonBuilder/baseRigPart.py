
import inspect

from maya.cmds import *
from maya import cmds

from ... import path
from ... import vectors
from ... import cls_types
from ... import str_utils

from .. import maya_decorators
from .. import reference_utils
from .. import apiExtensions
from .. import triggered
from .. import poseSym
from .. import mel_utils

from ..animation import clip

import rig_utils
import baseSkeletonPart
import spaceSwitching
import control

logger = baseSkeletonPart.logger
AXES = vectors.Axis.BASE_AXES

#make sure all setDrivenKeys have linear tangents
setDrivenKeyframe = lambda *a, **kw: cmds.setDrivenKeyframe(inTangentType='linear', outTangentType='linear', *a, **kw)

class RigMenuCommand(triggered.MenuCommand):

    def getCmdLocalsDict(self):
        d = super(RigMenuCommand, self).getCmdLocalsDict()
        d['thisRig'] = RigPart.InitFromItem(self._node)

        return d

def connectAttrReverse(srcAttr, destAttr, **kw):
    """
    puts a reverse node in between the two given attributes
    """
    revNode = cmds.shadingNode('reverse', asUtility=True)
    cmds.connectAttr(srcAttr, '%s.inputX' % revNode, **kw)
    cmds.connectAttr('%s.outputX' % revNode, destAttr, **kw)

    return revNode

class RigPartError(Exception): pass

def isRigPartContainer(node):
    if cmds.objectType(node, isType='objectSet'):
        return cmds.sets(node, q=True, text=True) == 'rigPrimitive'

    return False

def filterRigPartContainers(nodes):
    objectSets = cmds.ls(nodes, type='objectSet') or []

    return [node for node in objectSets if isRigPartContainer(node)]

def getRigPartContainers(compatabilityMode=False):
    existingContainers = [node for node in cmds.ls(type='objectSet', r=True) or []
                          if cmds.sets(node, q=True, text=True) == 'rigPrimitive']
    if compatabilityMode:
        existingContainers += [node.split('.')[0] for node in cmds.ls('*._rigPrimitive', r=True)]

    return existingContainers

def getNodesCreatedBy(function, *args, **kwargs):
    """
    returns a 2-tuple containing all the nodes created by the passed function, and
    the return value of said function

    NOTE: if any container nodes were created, their contents are omitted from the
    resulting node list - the container itself encapsulates them
    """

    newNodes, ret = apiExtensions.getNodesCreatedBy(function, *args, **kwargs)

    #now remove nodes from all containers from the newNodes list
    newContainers = apiExtensions.filterByType(newNodes, apiExtensions.MFn.kSet)

    #NOTE: nodes are MObject instances at this point
    newNodes = set([node for node in newNodes if node is not None])
    for c in newContainers:
        for n in cmds.sets(c, q=True) or []:
            if n in newNodes:
                newNodes.remove(n)

    # containers contained by other containers don't need to be
    # returned (as they're already contained by a parent)
    newTopLevelContainers = []
    for c in newContainers:
        parentContainer = cmds.sets(c, q=True, parentContainer=True)
        if parentContainer:
            continue

        newTopLevelContainers.append(c)
        newNodes.add(c)

    return newNodes, ret

def buildContainer(typeClass, kwDict, nodes, controls, namedNodes=()):
    """
    builds a container for the given nodes, and tags it with various attributes to record
    interesting information such as rig primitive version, and the args used to instantiate
    the rig.  it also registers control objects with attributes, so the control nodes can
    queried at a later date by their name
    """

    #if typeClass is an instance, then set its container attribute, otherwise instantiate an instance and return it
    if isinstance(typeClass, RigPart):
        theInstance = typeClass
        typeClass = type(typeClass)
    elif issubclass(typeClass, RigPart):
        theInstance = typeClass(None)

    #build the container, and add the special attribute to it to
    theContainer = cmds.sets(em=True, n='%s_%s' % (typeClass.__name__, kwDict.get('idx', 'NOIDX')), text='rigPrimitive')
    theInstance.setContainer(theContainer)

    cmds.addAttr(theContainer, ln='_rigPrimitive', attributeType='compound', numberOfChildren=7)
    cmds.addAttr(theContainer, ln='typeName', dt='string', parent='_rigPrimitive')
    cmds.addAttr(theContainer, ln='script', dt='string', parent='_rigPrimitive')
    cmds.addAttr(theContainer, ln='version', at='long', parent='_rigPrimitive')
    cmds.addAttr(theContainer, ln='skeletonPart', at='message', parent='_rigPrimitive')
    cmds.addAttr(theContainer, ln='buildKwargs', dt='string', parent='_rigPrimitive')
    cmds.addAttr(theContainer, ln='controls',
            multi=True,
            indexMatters=True,
            attributeType='message',
            parent='_rigPrimitive')
    cmds.addAttr(theContainer, ln='namedNodes',
            multi=True,
            indexMatters=True,
            attributeType='message',
            parent='_rigPrimitive')


    #now set the attribute values...
    cmds.setAttr('%s._rigPrimitive.typeName' % theContainer, typeClass.__name__, type='string')
    cmds.setAttr('%s._rigPrimitive.script' % theContainer, inspect.getfile(typeClass), type='string')
    cmds.setAttr('%s._rigPrimitive.version' % theContainer, typeClass.__version__)
    cmds.setAttr('%s._rigPrimitive.buildKwargs' % theContainer, str(kwDict), type='string')


    #now add all the nodes
    nodes = map(str, (node for node in nodes if node))
    controls = map(str, (node for node in controls if node))
    for node in set(nodes) | set(controls):
        if cmds.objectType(node, isAType='dagNode'):
            cmds.sets(node, e=True, add=theContainer)

        #if the node is a rig part container add it to this container otherwise skip it
        elif cmds.objectType(node, isAType='objectSet'):
            if isRigPartContainer(node):
                cmds.sets(node, e=True, add=theContainer)


    #and now hook up all the controls
    for idx, control in enumerate(controls):
        if control is None:
            continue

        cmds.connectAttr('%s.message' % control, '%s._rigPrimitive.controls[%d]' % (theContainer, idx), f=True)

        #set the kill state on the control if its a transform node
        if cmds.objectType(control, isAType='transform'):
            triggered.Trigger(control).setKillState(True)

    #hook up all the named nodes
    for idx, node in enumerate(namedNodes):
        if node is None:
            continue

        cmds.connectAttr('%s.message' % node, '%s._rigPrimitive.namedNodes[%d]' % (theContainer, idx), f=True)

    #lock the container
    cmds.lockNode(theContainer, lock=True)

    return theInstance

class RigPart(object):
    """
    base rig part class.  deals with rig part creation.

    rig parts are instantiated by passing the class a rig part container node

    to create a new rig part, simply call the RigPartClass.Create(skeletonPart, *args)
    where the skeletonPart is the SkeletonPart instance created via the skeleton builder
    """
    __metaclass__ = cls_types.trackableTypeFactory()

    __version__ = 0
    DEFAULT_SCALE = 2
    PRIORITY = 0

    # Stores the names used to refer to actual control nodes
    # using part.getControl('controlName')
    CONTROL_NAMES = None

    # Stores names for nodes that aren't controls, but need to be
    # accessible from the part. The qss on the WorldPart is an example
    # of a node that isn't a control, but needs to be easily queried
    NAMED_NODE_NAMES = None

    # Determines whether controls for this part are automatically added
    # to the rig's "allControls" qss
    ADD_CONTROLS_TO_QSS = True

    # Determines whether this part should appear in the UI or not...
    AVAILABLE_IN_UI = False

    # If defined this value is used to customize the name as it appears
    # in the UI, set this to the desired string
    DISPLAY_NAME = None

    def __new__(cls, partContainer, skeletonPart=None):
        if cls is RigPart:
            clsName = cmds.getAttr('%s._rigPrimitive.typeName' % partContainer)
            cls = cls.GetNamedSubclass(clsName)
            if cls is None:
                raise TypeError("Cannot determine the part class for the given part container!")

        return object.__new__(cls)

    def __init__(self, partContainer, skeletonPart=None):
        if partContainer is not None:
            if not isRigPartContainer(partContainer):
                raise RigPartError("Must pass a valid rig part container! (received %s - a %s)" %
                                   (partContainer, cmds.nodeType(partContainer)))

        self._container = partContainer
        self._skeletonPart = skeletonPart
        self._worldPart = None
        self._worldControl = None
        self._partsNode = None
        self._qss = None
        self._idx = None

        if partContainer:
            if skeletonPart is None:
                try:
                    self.getSkeletonPart()

                # this isn't fatal, although its not good
                except RigPartError, x:
                    logger.warning(str(x))

    def __unicode__(self):
        return u"%s_%d(%r)" % (self.__class__.__name__, self.getIdx(), self._container)

    __str__ = __unicode__

    def __repr__(self):
        return repr(unicode(self))

    def __hash__(self):
        """
        the hash for the container mobject uniquely identifies this rig control
        """
        return hash(apiExtensions.asMObject(self._container))

    def __eq__(self, other):
        return self._container == other.getContainer()

    def __ne__(self, other):
        return not self.__eq__(other)

    def __getitem__(self, idx):
        """
        returns the control at <idx>
        """
        connected = cmds.listConnections('%s._rigPrimitive.controls[%d]' % (self._container, idx), d=False)
        if connected:
            assert len(connected) == 1, "More than one control was found!!!"
            return connected[0]

        return None

    def __len__(self):
        """
        returns the number of controls registered on the rig
        """
        return cmds.getAttr('%s._rigPrimitive.controls' % self._container, size=True)

    def __iter__(self):
        """
        iterates over all controls in the rig
        """
        for n in range(len(self)):
            yield self[n]

    def getContainer(self):
        return self._container

    def setContainer(self, container):
        self._container = container

    def getNodes(self):
        """
        returns ALL the nodes that make up this rig part
        """
        return cmds.sets(self._container, q=True)

    nodes = getNodes

    def isReferenced(self):
        return cmds.referenceQuery(self._container, inr=True)

    @classmethod
    def GetPartName(cls):
        """
        can be used to get a "nice" name for the part class
        """
        if cls.DISPLAY_NAME is None:
            return str_utils.camelCaseToNice(cls.__name__)

        return cls.DISPLAY_NAME

    @classmethod
    def InitFromItem(cls, item):
        """
        inits the rigPart from a member item - the RigPart instance returned is
        cast to the most appropriate type
        """

        def getPart(item):
            typeClsStr = cmds.getAttr('%s._rigPrimitive.typeName' % item)
            typeCls = RigPart.GetNamedSubclass(typeClsStr)
            if typeCls is None:
                raise RigPartError("Cannot find rig part class %s" % typeClsStr)

            return typeCls(item)

        if isRigPartContainer(item):
            return getPart(item)

        cons = cmds.listConnections(item, s=False, type='objectSet')
        if not cons:
            raise RigPartError("Cannot find a rig container for %s" % item)

        for con in cons:
            if isRigPartContainer(con):
                return getPart(con)

        raise RigPartError("Cannot find a rig container for %s" % item)

    @classmethod
    def Iter(cls, skipSubParts=True):
        """
        iterates over all RigParts in the current scene

        NOTE: if skipSubParts is True will skip over parts that inherit from RigSubPart - these are assumed to be contained by another part
        """
        for c in getRigPartContainers():
            if cmds.objExists('%s._rigPrimitive' % c):
                thisClsName = cmds.getAttr('%s._rigPrimitive.typeName' % c)
                thisCls = RigPart.GetNamedSubclass(thisClsName)

                if thisCls is None:
                    raise RigPartError("No RigPart called %s" % thisClsName)

                if skipSubParts and issubclass(thisCls, RigSubPart):
                    continue

                if issubclass(thisCls, cls):
                    yield thisCls(c)

    @classmethod
    def IterInOrder(cls, skipSubParts=False):
        for skeletonPart in baseSkeletonPart.SkeletonPart.IterInOrder():
            rigPart = skeletonPart.getRigPart()
            if rigPart is None:
                continue

            if skipSubParts and isinstance(rigPart, RigSubPart):
                continue

            yield rigPart

    @classmethod
    def GetUniqueIdx(cls):
        """
        returns a unique index (unique against the universe of existing indices
        in the scene) for the current part class
        """
        existingIdxs = []
        for part in cls.Iter():
            idx = part.getBuildKwargs()['idx']
            existingIdxs.append(idx)

        existingIdxs.sort()
        assert len(existingIdxs) == len(set(existingIdxs)), "There is a duplicate ID! %s, %s" % (cls, existingIdxs)

        #return the first, lowest, available index
        for orderedIdx, existingIdx in enumerate(existingIdxs):
            if existingIdx != orderedIdx:
                return orderedIdx

        if existingIdxs:
            return existingIdxs[-1] + 1

        return 0

    def createSharedShape(self, name):
        return apiExtensions.asMObject(cmds.createNode('nurbsCurve', n=name + '#', p=self.sharedShapeParent))

    @classmethod
    def Create(cls, skeletonPart, *a, **kw):
        """
        you can pass in the following kwargs to control the build process
        addControlsToQss		defaults to cls.ADD_CONTROLS_TO_QSS
        """

        #check to see if the given skeleton part can actually be rigged by this method
        if not cls.CanRigThisPart(skeletonPart):
            return

        addControlsToQss = kw.get('addControlsToQss', cls.ADD_CONTROLS_TO_QSS)

        buildFunc = getattr(cls, '_build', None)
        if buildFunc is None:
            raise RigPartError("The rigPart %s has no _build method!" % cls.__name__)

        if not isinstance(skeletonPart, baseSkeletonPart.SkeletonPart):
            raise RigPartError("Need a SkeletonPart instance, got a %s instead" % skeletonPart.__class__)

        if not skeletonPart.compareAgainstHash():
            raise baseSkeletonPart.NotFinalizedError("ERROR :: %s hasn't been finalized!" % skeletonPart)

        #now turn the args passed in are a single kwargs dict
        argNames, vArgs, vKwargs, defaults = inspect.getargspec(buildFunc)
        if defaults is None:
            defaults = []

        # strip the first two args - which should be the instance
        # arg (usually self) and the skeletonPart
        argNames = argNames[2:]
        if vArgs is not None:
            raise RigPartError('cannot have *a in rig build functions')

        for argName, value in zip(argNames, a):
            kw[argName] = value

        #now explicitly add the defaults
        for argName, default in zip(argNames, defaults):
            kw.setdefault(argName, default)

        #generate an index for the rig part - each part must have a unique index
        idx = cls.GetUniqueIdx()
        kw['idx'] = idx

        #construct an empty instance - empty RigPart instances are
        # only valid inside this method...
        self = cls(None)
        self._skeletonPart = skeletonPart
        self._idx = idx

        # generate a default scale for the rig part - divide the
        # skeleton scale by 10 because controls are roughly this
        # much smaller than their controlling skeleton parts
        kw.setdefault('scale', baseSkeletonPart.getScaleFromSkeleton() / 10.0)
        self.scale = kw['scale']

        # make sure the world part is created first - if its created
        # by the part, then its nodes will be included in its container...
        self._cacheWorld(WorldPart.Create())
        qss = self.getQssSet()

        # create the shared shape transform - this is the transform
        # under which all shared shapes are temporarily parented to,
        # and all shapes under this transform are automatically added
        # to all controls returned after the build function returns
        self.sharedShapeParent = apiExtensions.asMObject(cmds.createNode('transform', n='_tmp_sharedShape'))
        defaultSharedShape = self.createSharedShape('%s_sharedAttrs' % cls.GetPartName())
        kw['sharedShape'] = defaultSharedShape

        # run the build function
        newNodes, (controls, namedNodes) = getNodesCreatedBy(self._build, skeletonPart, **kw)

        # its possible for a build function to return None in the
        # control list because it wants to preserve the length of
        # the control list returned - so construct a list of
        # controls that actually exist
        realControls = [c for c in controls if c is not None]
        if addControlsToQss:
            for c in realControls:
                cmds.sets(c, add=qss)

        # check to see if there is a layer for the rig controls and
        # add controls to it
        if controls:
            if cmds.objExists('rig_controls') and cmds.nodeType('rig_controls') == 'displayLayer':
                rigLayer = 'rig_controls'
            else:
                rigLayer = cmds.createDisplayLayer(name='rig_controls', empty=True)

            cmds.editDisplayLayerMembers(rigLayer, controls, noRecurse=True)

        # make sure there are no intermediate shapes
        for c in realControls:
            for shape in cmds.listRelatives(c, s=True, pa=True) or []:
                if cmds.getAttr('%s.intermediateObject' % shape):
                    cmds.delete(shape)

        # build the container and initialize the rigPrimtive
        buildContainer(self, kw, newNodes, controls, namedNodes)

        # add shared shapes to all controls, and remove shared
        # shapes that are empty
        sharedShapeParent = self.sharedShapeParent
        sharedShapes = cmds.listRelatives(sharedShapeParent, pa=True, s=True) or []
        for c in realControls:
            if cmds.objectType(c, isAType='transform'):
                for shape in sharedShapes:
                    cmds.parent(shape, c, add=True, s=True)

        for shape in sharedShapes:
            if not cmds.listAttr(shape, ud=True):
                cmds.delete(shape)

        cmds.delete(sharedShapeParent)
        del(self.sharedShapeParent)

        # stuff the part container into the world container - we
        # want a clean top level in the outliner
        theContainer = self._container
        cmds.sets(theContainer, e=True, add=self._worldPart.getContainer())

        # make sure the container "knows" the skeleton part - its
        # not always obvious trawling through the nodes in the
        # container which items are the skeleton part
        cmds.connectAttr('%s.message' % skeletonPart.getContainer(), '%s._rigPrimitive.skeletonPart' % theContainer)

        return self

    @classmethod
    def GetControlName(cls, control):
        """
        returns the name of the control as defined in the CONTROL_NAMES attribute
        for the part class
        """
        cons = cmds.listConnections(control.message, s=False, p=True, type='objectSet')
        for c in cons:
            typeClassStr = cmds.getAttr('%s._rigPrimitive.typeName' % c.node())
            typeClass = RigPart.GetNamedSubclass(typeClassStr)
            if typeClass.CONTROL_NAMES is None:
                return str(control)

            idx = c[c.rfind('[')+1:-1]
            try: name = typeClass.CONTROL_NAMES[idx]
            except ValueError:
                logger.error('type: %s  control: %s' % (typeClass, control))
                raise RigPartError("Doesn't have a name!")

            return name

        raise RigPartError("The control isn't associated with a rig primitive")

    @classmethod
    def CanRigThisPart(cls, skeletonPart):
        return True

    @classmethod
    def GetDefaultBuildKwargList(cls):
        """
        returns a list of 2 tuples: argName, defaultValue
        """
        buildFunc = getattr(cls, '_build', None)
        spec = inspect.getargspec(buildFunc)

        # strip the first two items because the _build method is a
        # bound method - so the first item is always the class arg
        # (usually called cls), and the second arg is always the
        # skeletonPart
        argNames = spec[0][2:]
        defaults = spec[3]

        if defaults is None:
            defaults = []

        if len(argNames) != len(defaults):
            raise RigPartError("%s has no default value set for one of its args - this is not allowed" % cls)

        kwargList = []
        for argName, default in zip(argNames, defaults):
            kwargList.append((argName, default))

        return kwargList

    def isPartContained(self):
        """
        returns whether this rig part is "contained" by another rig part.  Ie if a rig part was build from within another
        rig part, then it is contained.  Examples of this are things like the arm rig which builds upon the ikfk sub
        primitive rig - the sub-primitive is contained within the arm rig
        """
        cons = cmds.listConnections('%s.message' % self._container, s=False, type='objectSet')
        if cons:
            for con in cons:
                if isRigPartContainer(con):
                    rigPart = RigPart(con)

                    # skip world parts - all parts are contained by the world part
                    if isinstance(rigPart, WorldPart):
                        continue

                    elif rigPart == self:
                        continue

                    return True

        return False

    def iterContainedParts(self, recursive=True):
        for node in cmds.sets(self._container, q=True):
            if isRigPartContainer(node):
                part = RigPart(node)
                yield part

                if recursive:
                    for node in part.iterContainedParts():
                        yield node

    def iterChildParts(self, recursive=False, skipSubParts=True):
        for childSkeletonPart in self.getSkeletonPart().iterChildParts():
            rigContainer = childSkeletonPart.getRigContainer()
            if rigContainer:
                childRigPart = RigPart(rigContainer)
                if isinstance(childRigPart, RigSubPart):
                    continue

                yield childRigPart

                if recursive:
                    for grandChildRigPart in childRigPart.iterChildParts(True, skipSubParts):
                        yield grandChildRigPart

    def iterParentParts(self):
        for parentSkeletonPart in self.getSkeletonPart().iterParentParts():
            rigContainer = parentSkeletonPart.getRigContainer()
            if rigContainer:
                parentPart = RigPart(rigContainer)
                yield parentPart

    def getBuildKwargs(self):
        return __builtins__['eval'](cmds.getAttr('%s._rigPrimitive.buildKwargs' % self._container))

    def getIdx(self):
        """
        returns the index of the part - all parts have a unique index associated
        with them
        """
        if self._idx is None:
            if self._container is None:
                raise RigPartError('No index has been defined yet!')
            else:
                buildKwargs = self.getBuildKwargs()
                self._idx = buildKwargs['idx']

        return self._idx

    def getParity(self):
        return self.getSkeletonPart().getParity()

    def getSuffix(self):
        return self.getParity().asName()

    def getParityColour(self):
        return control.ColourDesc('green 0.7') if self.getParity() == str_utils.Parity.LEFT else control.ColourDesc('red 0.7')

    def getBuildScale(self):
        return self.getBuildKwargs().get('scale', self.PART_SCALE)

    def _cacheWorld(self, worldPart):
        self._worldPart = worldPart
        self._worldControl = worldPart.getControl('control')
        self._partsNode = worldPart.getNamedNode('parts')
        self._qss = worldPart.getNamedNode('qss')

    def getWorldPart(self):
        if self._worldPart is None:
            cons = cmds.listConnections('%s.message' % self._container, s=False, type='objectSet')
            if not cons:
                raise RigPartError("No connections to the container exist!")

            for con in cons:
                if isRigPartContainer(con):
                    rigPart = RigPart(con)
                    if isinstance(rigPart, WorldPart):
                        self._cacheWorld(rigPart)

            if self._worldPart is None:
                raise RigPartError("Failed to find an existing world part!")

        return self._worldPart

    def getWorldControl(self):
        if self._worldControl is None:
            self.getWorldPart()

        return self._worldControl

    def getPartsNode(self):
        if self._partsNode is None:
            self.getWorldPart()

        return self._partsNode

    def getQssSet(self):
        if self._qss is None:
            self.getWorldPart()

        return self._qss

    def getSkeletonPart(self):
        """
        returns the skeleton part this rig part is driving
        """

        #have we cached the skeleton part already?  if so, early out!
        if self._skeletonPart:
            return self._skeletonPart

        connected = cmds.listConnections('%s.skeletonPart' % self._container)
        if connected is None:
            raise RigPartError(
                "There is no skeleton part associated with this rig part! "
                "This can happen for a variety of reasons such as name changes "
                "on the skeleton in the model file (if you're using referencing), "
                "or a incomplete conversion from the old rig format...")

        if cmds.nodeType(connected[0]) == 'reference':
            raise RigPartError(
                "A reference node is connected to the skeletonPart attribute. "
                "This could mean the model reference isn't loaded, or a node "
                "name from the referenced file has changed - either way I can't "
                "determine the skeleton part used by this rig!")

        #cache the value so we can quickly return it on consequent calls
        self._skeletonPart = skeletonPart = baseSkeletonPart.SkeletonPart.InitFromItem(connected[0])

        return skeletonPart

    def getSkeletonPartParity(self):
        return self.getSkeletonPart().getParity()

    def getControl(self, attrName):
        """
        returns the control named <attrName>.  control "names" are defined by the CONTROL_NAMES class
        variable.  This list is asked for the index of <attrName> and the control at that index is returned
        """
        if self.CONTROL_NAMES is None:
            raise AttributeError("The %s rig primitive has no named controls" % self.__class__.__name__)

        idx = list(self.CONTROL_NAMES).index(attrName)
        if idx < 0:
            raise AttributeError("No control with the name %s" % attrName)

        connected = cmds.listConnections('%s._rigPrimitive.controls[%d]' % (self._container, idx), d=False)
        if connected:
            assert len(connected) == 1, "More than one control was found!!!"
            return connected[0]

        return None

    def getControls(self):
        return list(self)

    def getControlIdx(self, control):
        """
        returns the index of the given control - each control is plugged into a given "slot"
        """
        cons = cmds.listConnections('%s.message' % control, s=False, p=True) or []
        for c in cons:
            node = c.split('.')[0]
            if not isRigPartContainer(node):
                continue

            if cmds.objExists(node):
                if node != self._container:
                    continue

                idx = int(c[c.rfind('[')+1:-1])

                return idx

        raise RigPartError("The control %s isn't associated with this rig primitive %s" % (control, self))

    def getControlName(self, control):
        """
        returns the name of the control as defined in the CONTROL_NAMES attribute
        for the part class
        """
        if self.CONTROL_NAMES is None:
            return str(control)

        controlIdx = self.getControlIdx(control)

        try:
            return self.CONTROL_NAMES[controlIdx]
        except IndexError:
            return None

    def getNamedNode(self, nodeName):
        """
        returns the "named node" called <nodeName>.  Node "names" are defined by the NAMED_NODE_NAMES class
        variable.  This list is asked for the index of <nodeName> and the node at that index is returned
        """
        if self.NAMED_NODE_NAMES is None:
            raise AttributeError("The %s rig primitive has no named nodes" % self.__class__.__name__)

        idx = list(self.NAMED_NODE_NAMES).index(nodeName)
        if idx < 0:
            raise AttributeError("No node with the name %s" % nodeName)

        connected = cmds.listConnections('%s._rigPrimitive.namedNodes[%d]' % (self._container, idx), d=False)
        if connected:
            assert len(connected) == 1, "More than one node was found!!!"
            return connected[0]

        return None

    def getPartHierarchyControls(self):
        controls = list(self)
        for rigPart in self.iterChildParts(True):
            controls += list(rigPart)

        return controls

    def selectPartHierarchy(self):
        cmds.select(self.getPartHierarchyControls(), add=True)

    def delete(self):

        # First, store the skeleton pose
        initialPose = None
        skeletonPart = self.getSkeletonPart()
        if skeletonPart:
            initialPose = clip.storeWorldPose(skeletonPart.getItems())

        # Delete contained parts first
        for part in self.iterContainedParts(False):
            part.delete()

        # Now clean delete all nodes within this part container
        nodes = cmds.sets(self._container, q=True)
        for node in nodes:
            rig_utils.cleanDelete(node)

        # Make sure the container still exists (if it was manually
        # unlocked, maya will have deleted it already) and delete it
        if cmds.objExists(self._container):
            cmds.lockNode(self._container, lock=False)
            cmds.delete(self._container)

        # if the skeleton part is referenced, clean all reference
        # edits off skeleton part joints
        skeletonPart = self.getSkeletonPart()
        if skeletonPart and skeletonPart.isReferenced():
            skeletonPartJoints = skeletonPart.items

            # now unload the reference
            partReferenceFile = cmds.referenceQuery(skeletonPart.getContainer(), filename=True)
            cmds.file(partReferenceFile, unloadReference=True)

            # remove edits from each joint in the skeleton part
            for j in skeletonPartJoints:
                cmds.referenceEdit(j, removeEdits=True, successfulEdits=True, failedEdits=True)

            # reload the referenced file
            cmds.file(partReferenceFile, loadReference=True)

        # Restore the initial pose
        if initialPose:
            clip.restoreWorldPose(initialPose)

    def getControlToJointMapping(self):
        raise NotImplemented

    ### POSE MIRRORING/SWAPPING ###
    def getOppositePart(self):
        """
        Finds the skeleton part opposite to the one this rig part controls, and returns its rig part.

        If no rig part can be found, or if no
        """
        thisSkeletonPart = self.getSkeletonPart()
        oppositeSkeletonPart = thisSkeletonPart.getOppositePart()

        if oppositeSkeletonPart is None:
            return None

        return oppositeSkeletonPart.getRigPart()

    def getOppositeControl(self, c):
        """
        Finds the control that is most likely to be opposite the one given.  It first gets the name of
        the given control.  It then finds the opposite rig part, and then queries it for the control
        with the determined name
        """
        controlIdx = self.getControlIdx(c)
        oppositePart = self.getOppositePart()
        if oppositePart:
            return oppositePart[controlIdx]

        return None

    def setupMirroring(self):
        worldControl = self.getWorldControl()
        for c in self.getControls():
            if c is None:
                continue

            oppositeControl = self.getOppositeControl(c)
            if oppositeControl:
                poseSym.ControlPair.Create(c, oppositeControl, worldControl)

def getFilePartDict():
    """
    returns a dictionary keyed by scene name containing a list of the parts contained in that scene
    """
    scenePartDict = {}

    # special case!  we want to skip parts that are of this exact
    # type - in older rigs this class was a RigSubPart, not a
    # super class for the biped limb classes
    IkFkBaseCls = RigPart.GetNamedSubclass('IkFkBase')

    for rigPart in RigPart.Iter():
        if IkFkBaseCls:
            if type(rigPart) is IkFkBaseCls:
                continue

        isReferenced = rigPart.isReferenced()
        if isReferenced:
            rigScene = cmds.referenceQuery(rigPart.getContainer(), filename=True)
        else:
            rigScene = cmds.file(q=True, sn=True)

        scenePartDict.setdefault(rigScene, [])
        partList = scenePartDict[rigScene]
        partList.append(rigPart)

    return scenePartDict

def generateNiceControlName(ctrlNode):
    niceName = control.getNiceName(ctrlNode)
    if niceName is not None:
        return niceName

    try:
        rigPart = RigPart.InitFromItem(ctrlNode)
        if rigPart is None:
            raise RigPartError("null")

        controlName = rigPart.getControlName(ctrlNode)
    except RigPartError:
        controlName = str(ctrlNode)

    parity = str_utils.NodeName(controlName).getParity()

    if parity == str_utils.Parity.LEFT:
        controlName = 'Left ' + str(str_utils.stripParity(controlName))
    if parity == str_utils.Parity.RIGHT:
        controlName = 'Right ' + str(str_utils.stripParity(controlName))
    else:
        controlName = str(controlName)

    return str_utils.camelCaseToNice(controlName)

def getSpaceSwitchControls(theJoint):
    """
    walks up the joint chain and returns a list of controls that drive parent joints
    """
    parentControls = []

    for p in apiExtensions.iterParents(theJoint):
        theControl = control.getItemRigControl(p)
        if theControl is not None:
            parentControls.append(theControl)

    return parentControls

def buildDefaultSpaceSwitching(theJoint, control=None, additionalParents=(), additionalParentNames=(), reverseHierarchy=False, **buildKwargs):
    if control is None:
        control = control.getItemRigControl(theJoint)

    theWorld = WorldPart.Create()
    spaces = getSpaceSwitchControls(theJoint)
    spaces.append(theWorld.getControl('control'))

    #determine default names for the given controls
    names = []
    for s in spaces:
        names.append(generateNiceControlName(s))

    additionalParents = list(additionalParents)
    additionalParentNames = list(additionalParentNames)

    for n in range(len(additionalParentNames), len(additionalParents)):
        additionalParentNames.append(generateNiceControlName(additionalParents[n]))

    spaces += additionalParents
    names += additionalParentNames

    #we don't care about space switching if there aren't any non world spaces...
    if not spaces:
        return

    if reverseHierarchy:
        spaces.reverse()
        names.reverse()

    return spaceSwitching.build(control, spaces, names, **buildKwargs)

def getParentAndRootControl(theJoint):
    """
    returns a 2 tuple containing the nearest control up the hierarchy, and the
    most likely control to use as the "root" control for the rig.  either of these
    may be the world control, but both values are guaranteed to be an existing
    control object
    """
    parentControl, rootControl = None, None
    for p in apiExtensions.iterParents(theJoint):
        theControl = control.getItemRigControl(p)
        if theControl is None:
            continue

        if parentControl is None:
            parentControl = theControl

        skelPart = baseSkeletonPart.SkeletonPart.InitFromItem(p)
        if isinstance(skelPart, baseSkeletonPart.Root):
            rootControl = theControl

    if parentControl is None or rootControl is None:
        world = WorldPart.Create()
        if parentControl is None:
            parentControl = world.getControl('control')

        if rootControl is None:
            rootControl = world.getControl('control')

    return parentControl, rootControl

def createLineOfActionMenu(controls, joints):
    """
    deals with adding a "draw line of action" menu to each control in the controls
    list.  the line is drawn through the list of joints passed
    """
    if not joints:
        return

    if not isinstance(controls, (list, tuple)):
        controls = [controls]

    joints = list(joints)
    jParent = baseSkeletonPart.getNodeParent(joints[0])
    if jParent:
        joints.insert(0, jParent)

    for c in controls:
        cTrigger = triggered.Trigger(c)
        for j in joints:
            cTrigger.connect(j)

        cTrigger.createMenu('draw line of action').setCmdStr("import lineOfAction; lineOfAction.create({connects});")

class RigSubPart(RigPart):
    """
    """

    # this attribute describes what skeleton parts the rig primitive is
    # associated with.  If the attribute's value is None, then the rig
    # primitive is considered a "hidden" primitive that has
    SKELETON_PRIM_ASSOC = None

class PrimaryRigPart(RigPart):
    """
    all subclasses of this class are exposed as available rigging methods to the user
    """

    AVAILABLE_IN_UI = True

class WorldPart(RigPart):
    """
    the world part can only be created once per scene.  if an existing world part instance is found
    when calling WorldPart.Create() it will be returned instead of creating a new instance
    """

    __version__ = 0
    CONTROL_NAMES = ('control',)
    NAMED_NODE_NAMES = ('parts', 'masterQss', 'qss')

    WORLD_OBJ_MENUS = (('toggle rig vis', ""),
                       ('draw all lines of action', ""),
                       )

    @classmethod
    def Create(cls, **kw):
        for existingWorld in cls.Iter():
            return existingWorld

        #try to determine scale - walk through all existing skeleton parts in the scene
        for skeletonPart in baseSkeletonPart.SkeletonPart.IterInOrder():
            kw.setdefault('scale', skeletonPart.getBuildScale())
            break

        worldNodes, (controls, namedNodes) = getNodesCreatedBy(cls._build, **kw)
        worldPart = buildContainer(WorldPart, { 'idx': 0 }, worldNodes, controls, namedNodes)

        #check to see if there is a layer for the rig controls and add controls to it
        if cmds.objExists('rig_controls') and cmds.nodeType('rig_controls') == 'displayLayer':
            rigLayer = 'rig_controls'
        else:
            rigLayer = cmds.createDisplayLayer(name='rig_controls', empty=True)

        cmds.editDisplayLayerMembers(rigLayer, controls, noRecurse=True)

        return worldPart

    @classmethod
    def _build(cls, **kw):
        scale = kw.get('scale', cls.DEFAULT_SCALE)

        world = control.buildControl(
            'world',
            shapeDesc=control.ShapeDesc('stump', control.AX_Z),
            oriented=False,
            scale=scale,
            niceName='The World')

        parts = cmds.group(empty=True, name='parts_grp')
        qss = cmds.sets(empty=True, text="gCharacterSet", n="body_ctrls")
        masterQss = cmds.sets(empty=True, text="gCharacterSet", n="all_ctrls")

        cmds.sets(qss, add=masterQss)

        control.attrState(world, 's', *control.NORMAL)
        cmds.connectAttr('%s.scale' % world, '%s.scale' % parts)
        cmds.connectAttr('%s.scaleX' % world, '%s.scaleY' % world)
        cmds.connectAttr('%s.scaleX' % world, '%s.scaleZ' % world)

        #add right click items to the world controller
        worldTrigger = triggered.Trigger(str(world))
        qssIdx = worldTrigger.connect(str(masterQss))
        selectMenu = worldTrigger.createMenu('Select all controls', RigMenuCommand)
        selectMenu.setCmdStr('thisRig.selectPartHierarchy()')

        mirrorPoseMenu = worldTrigger.createMenu('Mirror pose', RigMenuCommand)
        mirrorPoseMenu.setCmdStr('from animation import mirroring; mirroring.swapPoseForRig(thisRig)')

        mirrorAnimMenu = worldTrigger.createMenu('Mirror animation', RigMenuCommand)
        mirrorAnimMenu.setCmdStr('from animation import mirroring; mirroring.swapAnimationForRig(thisRig)')

        #add world control to master qss
        cmds.sets(world, add=masterQss)

        #turn unwanted transforms off, so that they are locked, and no longer keyable
        control.attrState(world, 's', *control.NO_KEY)
        control.attrState(world, ('sy', 'sz'), *control.LOCK_HIDE)
        control.attrState(parts, ['t', 'r', 's', 'v'], *control.LOCK_HIDE)

        controls = (world,)
        namedNodes = (parts, masterQss, qss)

        return controls, namedNodes

    def getWorldPart(self):
        return self

    def getSkeletonPart(self):
        #the world part has no skeleton part...
        return None

    def getControlToJointMapping(self):
        return str_utils.Mapping()

    def iterChildParts(self, recursive=False, skipSubParts=True):
        """
        this works a little different with the world part because it isn't associated with a
        skeleton part.  So iterate over all contained parts (which is usually ALL parts) and
        yield only the root parts (it may be more than 1).
        """
        rootCls = RigPart.GetNamedSubclass('Root')
        for part in self.iterContainedParts(False):
            if isinstance(part, rootCls):
                yield part

                if recursive:
                    for childPart in part.iterChildParts(True, skipSubParts):
                        yield childPart

    def setupMirroring(self):
        pair = poseSym.ControlPair.Create(self.getControl('control'))
        pair.setFlips(0)

### <CHEEKY!> ###
'''
these functions get added to the SkeletonPart class as a way of implementing functionality that relies on
the RigPart class - which isn't available in the baseSkeletonPart script (otherwise you'd have a circular
import dependency)
'''

def _getRigContainer(self):
    """
    returns the container for the rig part - if this part is rigged.  None is returned otherwise

    NOTE: the container is returned instead of the rig instance because this script can't import
    the RigPart base class without causing circular import statements - there is a getRigPart
    method that is implemented in the baseRigPrimitive script that gets added to this class
    """
    rigContainerAttrpath = '%s.rigContainer' % self.getContainer()
    if cmds.objExists(rigContainerAttrpath):
        cons = cmds.listConnections(rigContainerAttrpath, d=False)
        if cons:
            return cons[0]

    cons = cmds.listConnections('%s.message' % self.getContainer(), s=False, type='objectSet')
    if cons:
        connectedRigParts = []
        for con in cons:
            if isRigPartContainer(con):
                connectedRigParts.append(RigPart(con))

        # now we have a list of connected rig parts - lets figure
        # out which ones are "top level" parts - ie don't belong
        # to another part
        if connectedRigParts:
            for rigPart in connectedRigParts:
                if not rigPart.isPartContained():
                    return rigPart

    return None

def _getRigPart(self):
    rigContainer = self.getRigContainer()
    if rigContainer:
        return RigPart(self.getRigContainer())

    return None

baseSkeletonPart.SkeletonPart.getRigContainer = _getRigContainer
baseSkeletonPart.SkeletonPart.getRigPart = _getRigPart

def _deleteRig(self):
    rigPart = self.getRigPart()
    rigPart.delete()

baseSkeletonPart.SkeletonPart.deleteRig = _deleteRig

### </CHEEKY!> ###

def setupMirroring():
    """
    sets up all controls in the scene for mirroring
    """
    for rigPart in RigPart.Iter():
        rigPart.setupMirroring()

@maya_decorators.d_showWaitCursor
@maya_decorators.d_undoBlock
def buildRigForModel(scene=None, referenceModel=False, deletePlacers=False):
    """
    given a model scene whose skeleton is assumed to have been built by the
    skeletonBuilder tool, this function will create a rig scene by referencing
    in said model, creating the rig as best it knows how, saving the scene in
    the appropriate spot etc...
    """

    #if no scene was passed, assume we're acting on the current scene
    if scene is None:
        scene = path.Path(cmds.file(q=True, sn=True))
    #if the scene WAS passed in, open the desired scene if it isn't already open
    else:
        scene = path.Path(scene)
        curScene = path.Path(cmds.file(q=True, sn=True))
        if curScene:
            if scene != curScene:
                mel_utils.MEL.saveChanges('file -f -open "%s"' % scene)
        else:
            cmds.file(scene, f=True, open=True)

    #if the scene is still none bail...
    if not scene and referenceModel:
        raise baseSkeletonPart.SceneNotSavedError(
            "Uh oh, your scene hasn't been saved - Please "
            "save it somewhere on disk so I know where to "
            "put the rig.  Thanks!")

    #backup the current state of the scene, just in case something goes south...
    if scene.exists():
        backupFilename = scene.up() / ('%s_backup.%s' % (scene.name(), scene.getExtension()))
        if backupFilename.exists():
            backupFilename.delete()

        cmds.file(rename=backupFilename)
        cmds.file(save=True, force=True)
        cmds.file(rename=scene)

    #finalize
    failedParts = baseSkeletonPart.finalizeAllParts()
    if failedParts:
        cmds.confirmDialog(
            t='Finalization Failure',
            m='The following parts failed to finalize properly:\n\n%s' % '\n'.join(map(str, failedParts)),
            b='OK',
            db='OK')
        return

    # delete placers if desired - NOTE: this should be done after after
    # finalization because placers are often used to define alignment
    # for end joints
    if deletePlacers:
        for part in baseSkeletonPart.SkeletonPart.Iter():
            placers = part.getPlacers()
            if placers:
                cmds.delete(placers)

    #if desired, create a new scene and reference in the model
    if referenceModel:

        # remove any unknown nodes in the scene - these cause maya to
        # barf when trying to save
        unknownNodes = cmds.ls(type='unknown')
        if unknownNodes:
            cmds.delete(unknownNodes)

        cmds.file(f=True, save=True)
        cmds.file(f=True, new=True)

        reference_utils.referenceFile(scene, 'model')

        #rename the scene to the rig
        rigSceneName = '%s_rig.ma' % scene.name()
        rigScene = scene.up() / rigSceneName
        cmds.file(rename=rigScene)
        cmds.file(f=True, save=True, typ='mayaAscii')
    else:
        rigScene = scene

    buildRigForAllParts()
    setupMirroring()

    return rigScene

def buildRigForAllParts():
    for part in baseSkeletonPart.SkeletonPart.IterInOrder():
        part.rig()

def deleteRigForAllParts():
    parts = list(RigPart.IterInOrder())
    parts.reverse()

    for part in parts:
        part.delete()

    for part in WorldPart.Iter():
        part.delete()

def setupSkeletonPartRigMethods():
    """
    sets up the rig method associations on the skeleton parts.  This
    is a list on each skeleton part containing the rigging methods
    that are compatible with that skeleton part
    """

    _rigMethodDict = {}
    for cls in RigPart.GetSubclasses():
        try:
            assoc = cls.SKELETON_PRIM_ASSOC
        except AttributeError:
            continue

        if assoc is None:
            continue

        for partCls in assoc:
            if partCls is None:
                continue

            try:
                _rigMethodDict[partCls].append((cls.PRIORITY, cls))
            except KeyError:
                _rigMethodDict[partCls] = [(cls.PRIORITY, cls)]

    for partCls, rigTypes in _rigMethodDict.iteritems():
        rigTypes.sort()
        rigTypes = [rigType for priority, rigType in rigTypes]
        partCls.RigTypes = rigTypes

#end
