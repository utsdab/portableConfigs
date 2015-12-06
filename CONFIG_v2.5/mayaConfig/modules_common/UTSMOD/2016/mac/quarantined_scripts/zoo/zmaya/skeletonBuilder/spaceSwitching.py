
import re

from maya import cmds
from maya.cmds import *

from ... import vectors
from ... import str_utils

from .. import maya_decorators
from .. import apiExtensions
from .. import triggered
import control

AXES = vectors.Axis.BASE_AXES

class SpaceSwitchCommand(triggered.MenuCommand):

    def isEditable(self):
        return False

    def execute(self, *_):
        SpaceSwitchNode(self._node).switchTo(self._dict['parentIdx'])

    def menuName(self):
        return 'Parent to %s' % self._dict['name']

    def spaceName(self):
        return self._dict['name']

    def parentIdx(self):
        return self._dict['parentIdx']

    def setParentIdx(self, idx):
        self._dict['parentIdx'] = idx

CONSTRAINT_TYPES = CONSTRAINT_PARENT, CONSTRAINT_POINT, CONSTRAINT_ORIENT = 'parentConstraint', 'pointConstraint', 'orientConstraint'
CONSTRAINT_CHANNELS = { CONSTRAINT_PARENT: (['t', 'r'], ['ct', 'cr']),
                        CONSTRAINT_POINT: (['t'], ['ct']),
                        CONSTRAINT_ORIENT: (['r'], ['cr']) }

NO_TRANSLATION = { 'skipTranslationAxes': ('x', 'y', 'z') }
NO_ROTATION = { 'skipRotationAxes': ('x', 'y', 'z') }

_parentAttrname = 'parent'
_parentAttrpathTemplate = '%s.' + _parentAttrname

@maya_decorators.d_undoBlock
def add(src, tgt,
        name=None,
        space=None,
        maintainOffset=True,
        nodeWithParentAttr=None,
        skipTranslationAxes=(),
        skipRotationAxes=(),
        constraintType=CONSTRAINT_PARENT):

    if space is None:
        space = listRelatives(src, p=True, pa=True)[0]

    if nodeWithParentAttr is None:
        nodeWithParentAttr = src

    if not name:
        name = control.getNiceName(tgt)
        if name is None:
            name = str_utils.camelCaseToNice(str(tgt))


    # if there is an existing constraint, check to see if the target already exists in
    # its target list - if it does, return the condition used it uses
    control.attrState(space, ('t', 'r'), lock=False, ignoreOnFailure=True)
    existingConstraint = None
    if SpaceSwitchNode.IsA(src):
        existingConstraint = findConstraint(src)
        constraintType = nodeType(existingConstraint)
        constraintFunc = getattr(cmds, constraintType)
        targetsOnConstraint = constraintFunc(existingConstraint, q=True, tl=True)
        if tgt in targetsOnConstraint:
            idx = targetsOnConstraint.index(tgt)
            aliases = constraintFunc(existingConstraint, q=True, weightAliasList=True)
            cons = listConnections('%s.%s' % (existingConstraint, aliases[idx]), type='condition', d=False)

            return cons[0]


    # when skip axes are specified maya doesn't handle things properly - so make sure
    # ALL transform channels are connected, and remove unwanted channels at the end...
    preT, preR = getAttr('%s.t' % space)[0], getAttr('%s.r' % space)[0]
    if existingConstraint:
        chans = CONSTRAINT_CHANNELS[constraintType]
        for channel, constraintAttr in zip(*chans):
            for axis in AXES:
                spaceAttr = '%s.%s%s' %(space, channel, axis)
                conAttr = '%s.%s%s' % (existingConstraint, constraintAttr, axis)
                if not isConnected(conAttr, spaceAttr):
                    connectAttr(conAttr, spaceAttr)


    # get the names for the parents from the parent enum attribute
    cmdOptionKw = { 'mo': True } if maintainOffset else {}
    if objExists(_parentAttrpathTemplate % nodeWithParentAttr):
        srcs, names = getSpaceTargetsNames(src)
        addAttr(_parentAttrpathTemplate % nodeWithParentAttr, e=True, enumName=':'.join(list(names) + [name]))

        # if we're building a pointConstraint instead of a parent constraint AND we already
        # have spaces on the object, we need to turn the -mo flag off regardless of what the
        # user set it to, as the pointConstraint maintain offset has different behaviour to
        # the parent constraint
        if constraintType in (CONSTRAINT_POINT, CONSTRAINT_ORIENT):
            cmdOptionKw.pop('mo')
    else:
        addAttr(nodeWithParentAttr, ln=_parentAttrname, at='enum', en=name)
        setAttr(_parentAttrpathTemplate % nodeWithParentAttr, keyable=True)


    # now build the constraint
    constraintFunction = getattr(cmds, constraintType)
    constraint = constraintFunction(tgt, space, **cmdOptionKw)[0]


    weightAliasList = constraintFunction(constraint, q=True, weightAliasList=True)
    targetCount = len(weightAliasList)
    constraintAttr = weightAliasList[-1]
    condition = shadingNode('condition', asUtility=True)
    condition = rename(condition, '%s_space_%s__#' % (apiExtensions.cleanShortName(src), apiExtensions.cleanShortName(tgt)))

    setAttr('%s.secondTerm' % condition, targetCount-1)
    setAttr('%s.colorIfTrue' % condition, 1, 1, 1)
    setAttr('%s.colorIfFalse' % condition, 0, 0, 0)
    connectAttr(_parentAttrpathTemplate % nodeWithParentAttr, '%s.firstTerm' % condition)
    connectAttr('%s.outColorR' % condition, '%s.%s' % (constraint, constraintAttr))


    # find out what symbol to use to find the parent attribute
    srcTrigger = triggered.Trigger(src)
    parentAttrIdx = srcTrigger.connect(nodeWithParentAttr)


    # add the zooObjMenu commands to the object for easy space switching
    menuCmd = srcTrigger.createMenu(name, SpaceSwitchCommand)
    menuCmd.setParentIdx(targetCount - 1)


    # when skip axes are specified maya doesn't handle things properly - so make sure
    # ALL transform channels are connected, and remove unwanted channels at the end...
    for axis, value in zip(AXES, preT):
        if axis in skipTranslationAxes:
            attr = '%s.t%s' % (space, axis)
            delete(attr, icn=True)
            setAttr(attr, value)

    for axis, value in zip(AXES, preR):
        if axis in skipRotationAxes:
            attr = '%s.r%s' % (space, axis)
            delete(attr, icn=True)
            setAttr(attr, value)


    # make the space node non-keyable and lock visibility
    control.attrState(space, ('t', 'r', 's'), lock=True, ignoreOnFailure=True)
    control.attrState(space, 'v', *control.HIDE, ignoreOnFailure=True)


    return condition

@maya_decorators.d_undoBlock
def build(src, tgts, names=None, space=None, **kw):
    if names is None:
        names = [None for t in tgts]

    conditions = []
    for tgt, name in zip(tgts, names):
        cond = add(src, tgt, name, space, **kw)
        conditions.append(cond)

    return conditions

@maya_decorators.d_undoBlock
def remove(src, tgt):
    '''
    removes a target (or space) from a "space switching" object
    '''

    tgts, names = getSpaceTargetsNames(src)
    tgt_mobject = apiExtensions.asMObject(tgt)

    name = None
    for index, (aTgt, aName) in enumerate(zip(tgts, names)):
        aTgt = apiExtensions.asMObject(aTgt)
        if aTgt == tgt_mobject:
            name = aName
            break

    if name is None:
        raise AttributeError("no such target")

    delete = False
    if len(tgts) == 1:
        delete = True

    constraint = findConstraint(src)

    parentAttrOn = findSpaceAttrNode(src)
    space = findSpace(src)

    spaceSwitch = SpaceSwitchNode(src)

    if delete:
        delete(constraint)
        deleteAttr(_parentAttrpathTemplate % src)
    else:
        constraintType = nodeType(constraint)
        constraintFunc = getattr(cmds, constraintType)
        constraintFunc(tgt, constraint, rm=True)

    for cmd in spaceSwitch.iterMenuCommands():
        if cmd.spaceName() == name:
            trigger = triggered.Trigger(spaceSwitch._node)
            trigger.deleteMenu(cmd.getIndex())

        # rebuild the parent attribute
        newNames = names[:]
        newNames.pop(index)
        addAttr(_parentAttrpathTemplate % parentAttrOn, e=True, enumName=':'.join(newNames))

    # now we need to update the indicies in the right click command - all targets that
    # were beyond the one we just removed need to have their indices decremented
    for cmd in spaceSwitch.iterMenuCommands():
        idx = cmd.parentIdx()
        if idx < index:
            continue

        cmd.setParentIdx(idx-1)

class SpaceSwitchNode(object):
    @classmethod
    def IsA(cls, node):
        '''
        returns whether the given node has been setup to space switch
        '''
        if triggered.Trigger.IsA(node):
            for slotIdx, slotCmd in triggered.Trigger(node).iterMenus():
                if type(slotCmd) is SpaceSwitchCommand:
                    return True

        return False

    def __init__(self, node):
        self._node = node
        self._space = None
        self._constraint = None
        self._controlNode = None  # this is the node that holds the "parent" attribute (usually the same as self._node)

    def __repr__(self):
        return 'SpaceSwitchNode(%r)' % self._node
    __str__ = __repr__

    def __eq__(self, other):
        return self._node == other._node

    def __ne__(self, other):
        return not self.__eq__(other)

    @property
    def node(self):
        return self._node

    @property
    def parentAttrpath(self):
        return _parentAttrpathTemplate % self.controlNode

    @property
    def space(self):
        if self._space is None:
            constraint = self.constraint
            if constraint is None:
                return None

            cAttr = '%s.constraintParentInverseMatrix' % constraint
            spaces = listConnections(cAttr, type='transform', d=False)
            if spaces:
                self._space = spaces[0]

        return self._space

    @property
    def constraint(self):
        if self._constraint is None:
            if self.controlNode:
                parentAttrpath = self.parentAttrpath
                try:
                    conditions = listConnections(parentAttrpath, type='condition', s=False) or []
                except ValueError:
                    return None

                for condition in conditions:
                    constraints = listConnections('%s.outColorR' % condition, type='constraint', s=False)
                    if constraints:
                        self._constraint = constraints[0]
                        break

        return self._constraint

    @property
    def controlNode(self):
        if self._controlNode is None:
            if triggered.Trigger.IsA(self._node):
                if cmds.objExists(_parentAttrpathTemplate % self._node):
                    self._controlNode = self._node
                else:
                    self._controlNode = triggered.Trigger(self._node)[1]

        return self._controlNode

    def iterMenuCommands(self):
        trigger = triggered.Trigger(self._node)
        for slotIdx, slotCmd in trigger.iterMenus():
            if type(slotCmd) is SpaceSwitchCommand:
                yield slotCmd

    def getSpaceData(self):
        constraint = self.constraint
        if constraint is None:
            return (), ()

        constraintType = nodeType(constraint)
        constraintFunc = getattr(cmds, constraintType)

        targetsOnConstraint = constraintFunc(self.constraint, q=True, tl=True)
        trigger = triggered.Trigger(self._node)

        tgts, names = [], []
        for spaceSwitchCmd in self.iterMenuCommands():
            names.append(spaceSwitchCmd.spaceName())

            idx = spaceSwitchCmd.parentIdx()
            tgts.append(targetsOnConstraint[idx])

        return tgts, names

    @property
    def spaces(self):
        return self.getSpaceData()[0]

    @property
    def names(self):
        return self.getSpaceData()[1]

    @maya_decorators.d_noAutoKey
    @maya_decorators.d_undoBlock
    def switchTo(self, idx, key=False, additionalNodes=()):
        allObjs = [self._node] + list(additionalNodes)

        initialPos = [cmds.xform(o, q=True, ws=True, rp=True) for o in allObjs]
        initialRot = [cmds.xform(o, q=True, ws=True, ro=True) for o in allObjs]

        # set the destination attrpath to the approprate value
        attrpath = self.parentAttrpath
        cmds.setAttr(attrpath, idx)

        # now restore xforms
        for o, pos, rot in zip(allObjs, initialPos, initialRot):
            cmds.move(pos[0], pos[1], pos[2], o, a=True, ws=True, rpr=True)
            cmds.rotate(rot[0], rot[1], rot[2], o, a=True, ws=True)

        if key:
            cmds.setKeyframe(allObjs, at=('t', 'r'))
            cmds.setKeyframe(attrpath)

    @maya_decorators.d_undoBlock
    def delete(self):

        # delete all space switch menu items
        trigger = triggered.Trigger(self._node)
        for slotIdx, slotCmd in trigger.iterMenus():
            if type(slotCmd) is SpaceSwitchCommand:
                trigger.deleteMenu(slotIdx)

        # store the constraint
        constraint = self.constraint

        # get all downstream condition nodes of the parent attr and delete em
        conds = cmds.listConnections(self.parentAttrpath, s=False, type='condition')
        if conds:
            cmds.delete(conds)

        # delete the constraint
        if constraint is not None:
            cmds.delete(constraint)

        # delete the parent attr
        cmds.deleteAttr(self.parentAttrpath)

        # re-run init - this sets all internal vars back to their defaults
        self.__init__(self._node)

def getSpaceName(src, theTgt):
    '''
    will return the user specified name given to a particular target object
    '''
    tgts, names = getSpaceTargetsNames(src)
    for tgt, name in zip(tgts, names):
        if tgt == theTgt:
            return name

def getSpaceTargetsNames(src):
    '''
    this procedure returns a 2-tuple: a list of all targets, and a list of user
    specified names - for the right click menus
    '''
    return SpaceSwitchNode(src).getSpaceData()

def findSpace(obj, constraint=None):
    '''
    will return the node being used as the "space node" for any given space switching object
    '''
    return SpaceSwitchNode(obj).space

def findConstraint(obj):
    '''
    will return the name of the constraint node thats controlling the "space node" for any given
    space switching object
    '''
    return SpaceSwitchNode(obj).constraint

def findSpaceAttrNode(obj):
    '''
    returns the node that contains the parent attribute for the space switch
    '''
    return SpaceSwitchNode(obj).controlNode

def changeSpace(obj, attrpath, value, objs=(), key=False):
    SpaceSwitchNode(obj).switchTo(value, key, objs)

def findCandidateSpace(obj, considerTranslation=True, considerRotation=True):
    '''
    finds the first candidate parent node that has both translation and rotation
    attributes settable (and thus constrainable)

    if no match is found, None is returned
    '''
    attrs = []
    if considerTranslation:
        attrs.append('t')

    if considerRotation:
        attrs.append('r')

    axes = 'x', 'y', 'z'
    for parent in apiExtensions.iterParents(obj):
        isCandidate = True
        for a in attrs:
            if not all(cmds.getAttr('%s.%s%s' % (parent, a, ax), se=True) for ax in axes):
                isCandidate = False

        if isCandidate:
            return parent

#end
