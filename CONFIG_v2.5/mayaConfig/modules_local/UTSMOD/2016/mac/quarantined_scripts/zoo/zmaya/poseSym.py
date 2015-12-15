
import logging

from maya import cmds
from maya.cmds import *

from .. import str_utils

from ..vectors import Vector, Matrix, Axis, AX_X, AX_Y, AX_Z

import constants
import apiExtensions

logger = logging.getLogger(__name__)
AXES = Axis.BASE_AXES

# try to load the zooMirror.py plugin
cmds.loadPlugin('zooMirror.py', quiet=True)

def getMatrix(node, attributeName):
    unit = cmds.currentUnit(q=True, l=True)
    matrix = Matrix(cmds.getAttr('%s.%s' % (node, attributeName)), 4)
    if unit == 'cm':
        return matrix

    # Otherwise we need to adjust the position
    if unit == 'm':
        matrix.set_position(matrix.get_position() * 0.01)
    elif unit == 'mm':
        matrix.set_position(matrix.get_position() * 10)
    else:
        raise Exception('Unsupported units!')

    return matrix

def getLocalMatrix(obj):
    return getMatrix(obj, 'matrix')

def getLocalRotMatrix(obj):
    '''
    returns the local matrix for the given obj
    '''
    localMatrix = getMatrix(obj, 'matrix')
    localMatrix.set_position((0, 0, 0))

    return localMatrix

def getWorldRotMatrix(obj):
    '''
    returns the world matrix for the given obj
    '''
    worldMatrix = getMatrix(obj, 'worldMatrix')
    worldMatrix.set_position((0, 0, 0))

    return worldMatrix

def setWorldRotMatrix(obj, matrix):
    '''
    given a world matrix, will set the transforms of the object
    '''
    parentInvMatrix = getMatrix(obj, 'parentInverseMatrix')
    localMatrix = matrix * parentInvMatrix

    setLocalRotMatrix(obj, localMatrix)

def setLocalRotMatrix(obj, matrix):
    '''
    given a world matrix, will set the transforms of the object
    '''

    # factor out any joint orient if applicable
    if cmds.objExists('%s.jo' % obj):
        jo = cmds.getAttr('%s.jo' % obj)[0]
        joMatrix = Matrix.FromEulerXYZ(*jo, degrees=True).expand(4)
        matrix = matrix * joMatrix.inverse()

    roo = cmds.getAttr('%s.rotateOrder' % obj)
    rot = constants.MATRIX_ROTATION_ORDER_CONVERSIONS_TO[roo](matrix, True)

    # try to set the rotation - check whether all the rotation channels are settable
    if cmds.getAttr('%s.r' % obj, se=True):
        cmds.setAttr('%s.r' % obj, *rot)

def worldToRelative(worldMatrix, other):
    if other is None:
        return worldMatrix

    otherInvMatrix = getMatrix(other, 'worldInverseMatrix')
    relativeMatrix = worldMatrix * otherInvMatrix

    return relativeMatrix

def relativeToWorld(relativeMatrix, other):
    if other is None:
        return relativeMatrix

    # We know from the getRelativeRotMatrix that (with R as relativeMatrix)
    # R = worldMatrix * otherInvMatrix
    # Therefore, to get the world matrix we use:
    # R * otherMatrix = worldMatrix * otherInvMatrix * otherMatrix
    # worldMatrix = R * otherMatrix
    otherMatrix = getMatrix(other, 'worldMatrix')
    return relativeMatrix * otherMatrix

def getRelativeMatrix(obj, other):
    '''
    returns the matrix for the given obj relative to another
    '''
    return worldToRelative(
        getMatrix(obj, 'worldMatrix'),
        other)

def setRelativeMatrix(obj, relativeMatrix, other):
    '''
    returns the matrix for the given obj relative to another
    '''
    print 'rel rots', Matrix.ToEulerXYZ(relativeMatrix, True)
    worldMatrix = relativeToWorld(relativeMatrix, other)
    print 'www rots', Matrix.ToEulerXYZ(worldMatrix, True)
    setWorldRotMatrix(obj, worldMatrix)

def mirrorMatrix(matrix, axis=AX_X, orientAxis=AX_X):
    '''
    axis is the axis things are flipped across
    orientAxis is the axis that gets flipped when mirroring orientations
    '''
    assert isinstance(matrix, Matrix)
    mirroredMatrix = Matrix(matrix)

    # make sure we've been given a Axis instances...  don't bother testing, just do it, and
    # make it absolute (non-negative - mirroring in -x is the same as mirroring in x)
    mirrorAxis = abs(Axis(axis))
    axisA = abs(Axis(orientAxis))

    # flip all axes
    axisB, axisC = axisA.otherAxes()
    mirroredMatrix[axisB][mirrorAxis] = -matrix[axisB][mirrorAxis]
    mirroredMatrix[axisC][mirrorAxis] = -matrix[axisC][mirrorAxis]

    # the above flipped all axes - but this results in a changing of coordinate system
    # handed-ness, so flip one of the axes back
    nonMirrorAxisA, nonMirrorAxisB = mirrorAxis.otherAxes()
    mirroredMatrix[axisA][nonMirrorAxisA] = -mirroredMatrix[axisA][nonMirrorAxisA]
    mirroredMatrix[axisA][nonMirrorAxisB] = -mirroredMatrix[axisA][nonMirrorAxisB]

    # if the input matrix was a 4x4 then mirror translation
    if matrix.size == 4:
        mirroredMatrix[3][mirrorAxis] = -matrix[3][mirrorAxis]

    return mirroredMatrix

def getKeyableAttrs(obj):
    attrs = cmds.listAttr(obj, keyable=True)
    if attrs is None:
        return []

    for attrToRemove in ('translate', 'translateX', 'translateY', 'translateZ', \
                         'rotate', 'rotateX', 'rotateY', 'rotateZ'):
        try:
            attrs.remove(attrToRemove)
        except ValueError: pass

    return attrs

class CommandStack(list):
    def append(self, func, *a, **kw):
        list.append(self, (func, a, kw))

    def execute(self):
        for func, a, kw in self:
            func(*a, **kw)
            # try:func(*a, **kw)
            # except: print func, a, kw

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.execute()

class ControlPair(object):
    '''
    sets up a relationship between two controls so that they can mirror/swap/match one
    another's poses.

    NOTE: when you construct a ControlPair setup (using the Create classmethod)
    '''

    # NOTE: these values are copied from the zooMirror script - they're copied because
    # the plugin generally doesn't exist on the pythonpath so we can't rely on an
    # import working....
    FLIP_AXES = (), (AX_X, AX_Y), (AX_X, AX_Z), (AX_Y, AX_Z)

    @classmethod
    def GetPairNode(cls, obj):
        '''
        given a transform will return the pair node the control is part of
        '''

        if obj is None:
            return None

        if cmds.objectType(obj, isAType='transform'):
            cons = cmds.listConnections('%s.message' % obj, s=False, type='controlPair')
            if not cons:
                return None

            return cons[0]

        if cmds.nodeType(obj) == 'controlPair':
            return obj

        return None

    @classmethod
    def Create(cls, controlA, controlB=None, mirrorPlane=None, axis=None):
        '''
        given two controls will setup the relationship between them

        NOTE: if controlB isn't given then it will only be able to mirror its current
        pose.  This is usually desirable on "central" controls like spine, head and
        neck controls
        '''

        # make sure we've been given transforms - mirroring doesn't make a whole lotta
        # sense on non-transforms
        if not cmds.objectType(controlA, isAType='transform'):
            return None

        if controlB:

            # if controlA is the same node as controlB then set controlB to None - this
            # makes it more obvious the pair is singular
            # NOTE: cmpNodes compares the actual MObjects, not the node names - just in
            # case we've been handed a full path and a partial path that are the same node...
            if apiExtensions.cmpNodes(controlA, controlB):
                controlB = None
            elif not cmds.objectType(controlB, isAType='transform'):
                return None

        # see if we have a pair node for the controls already
        pairNode = cls.GetPairNode(controlA)
        if pairNode:
            # if no controlB has been given see whether the pairNode we've already got
            # also has no controlB - if so, we're done
            if not controlB:
                new = cls(pairNode)
                if not new.controlB:
                    return new

            # if controlB HAS been given, check whether to see whether it has the same
            # pairNode - if so, we're done
            if controlB:
                pairNodeB = cls.GetPairNode(controlB)
                if pairNode == pairNodeB:
                    return cls(pairNode)

        # otherwise create a new one
        pairNode = cmds.createNode('controlPair')
        cmds.connectAttr('%s.message' % controlA, '%s.controlA' % pairNode)
        if controlB:
            cmds.connectAttr('%s.message' % controlB, '%s.controlB' % pairNode)

        # is there a mirror plane?
        if mirrorPlane is not None:
            cmds.connectAttr('%s.message' % mirrorPlane, '%s.mirrorPlane' % pairNode)

        # name the node
        nodeName = '%s_mirrorConfig' if controlB is None else '%s_%s_exchangeConfig' % (controlA, controlB)
        pairNode = cmds.rename(pairNode, nodeName)

        # instantiate it and run the initial setup code over it
        new = cls(pairNode)
        new.setup(axis)

        return new

    def __init__(self, pairNodeOrControl):
        self.node = pairNode = self.GetPairNode(pairNodeOrControl)
        self.controlA = None
        self.controlB = None
        self.mirrorPlane = None

        cons = cmds.listConnections('%s.controlA' % pairNode, d=False)
        if cons:
            self.controlA = cons[0]

        cons = cmds.listConnections('%s.controlB' % pairNode, d=False)
        if cons:
            self.controlB = cons[0]

        cons = cmds.listConnections('%s.mirrorPlane' % pairNode, d=False)
        if cons:
            self.mirrorPlane = cons[0]

        # make sure we have a control A
        if self.controlA is None:
            raise TypeError("Could not find controlA - need to!")

    def __eq__(self, other):
        if isinstance(other, ControlPair):
            other

        return self.node == other.node

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.node)

    def getAxis(self):
        return Axis(cmds.getAttr('%s.axis' % self.node))

    def setAxis(self, axis):
        cmds.setAttr('%s.axis' % self.node, axis)

    def getFlips(self):
        axes = cmds.getAttr('%s.flipAxes' % self.node)
        return list(self.FLIP_AXES[axes])

    def setFlips(self, flips):
        if isinstance(flips, int):
            cmds.setAttr('%s.flipAxes' % self.node, flips)

    def getWorldSpace(self):
        return cmds.getAttr('%s.worldSpace' % self.node)

    def setWorldSpace(self, state):
        cmds.setAttr('%s.worldSpace' % self.node, state)

    def isSingular(self):
        if self.controlB is None:
            return True

        # a pair is also singular if controlA is the same as controlB
        # NOTE: cmpNodes does a rigorous comparison so it will catch a fullpath
        # and a partial path that point to the same node
        if apiExtensions.cmpNodes(self.controlA, self.controlB):
            return True

        return False

    def neverDoT(self):
        return cmds.getAttr('%s.neverDoT' % self.node)

    def neverDoR(self):
        return cmds.getAttr('%s.neverDoR' % self.node)

    def neverDoOther(self):
        return cmds.getAttr('%s.neverDoOther' % self.node)

    def setup(self, axis=None):
        '''
        sets up the initial state of the pair node
        '''

        if axis:
            axis = abs(Axis(axis))
            cmds.setAttr('%s.axis' % self.node, axis)

        # if we have two controls try to auto determine the orientAxis and the flipAxes
        if self.controlA and self.controlB:
            worldMatrixA = getWorldRotMatrix(self.controlA)
            worldMatrixB = getWorldRotMatrix(self.controlB)

            # so restPoseB = restPoseA * offsetMatrix
            # restPoseAInv * restPoseB = restPoseAInv * restPoseA * offsetMatrix
            # restPoseAInv * restPoseB = I * offsetMatrix
            # thus offsetMatrix = restPoseAInv * restPoseB
            offsetMatrix = worldMatrixA.inverse() * worldMatrixB

            AXES = AX_X.asVector(), AX_Y.asVector(), AX_Z.asVector()
            flippedAxes = []
            for n in range(3):
                axisNVector = Vector(offsetMatrix[n][:3])

                # if the axes are close to being opposite, then consider it a flipped axis...
                if axisNVector.dot(AXES[n]) < -0.8:
                    flippedAxes.append(n)

            for n, flipAxes in enumerate(self.FLIP_AXES):
                if tuple(flippedAxes) == flipAxes:
                    cmds.setAttr('%s.flipAxes' % self.node, n)
                    break

        # this is a bit of a hack - and not always true, but generally singular controls built
        # by skeleton builder will work with this value
        elif self.controlA:
            cmds.setAttr('%s.flipAxes' % self.node, 0)
            self.setWorldSpace(False)

    def mirrorMatrix(self, matrix):
        matrix = mirrorMatrix(matrix, self.getAxis())
        for flipAxis in self.getFlips():
            matrix.setRow(flipAxis, -Vector(matrix.getRow(flipAxis)))

        return matrix

    def swap(self, t=True, r=True, other=True, cmdStack=None):
        '''
        mirrors the pose of each control, and swaps them

        NOTE: the cmdStack is needed because the mirroring needs to be computed on all controls
        BEFORE ANY OF THEM are transformed
        '''
        executeImmediately = False
        if cmdStack is None:
            cmdStack = CommandStack()
            executeImmediately = True

        # if there is no controlB, then perform a mirror instead...
        if not self.controlB:
            self.mirror(cmdStack=cmdStack)
            return

        # do the other attributes first - the parent attribute for example will
        # change the position so we need to set it before setting transforms
        if other and not self.neverDoOther():
            if not self.isSingular():
                for attr in getKeyableAttrs(self.controlA):
                    attrPathA = '%s.%s' % (self.controlA, attr)
                    attrPathB = '%s.%s' % (self.controlB, attr)
                    if cmds.objExists(attrPathA) and cmds.objExists(attrPathB):
                        attrValA = cmds.getAttr(attrPathA)
                        attrValB = cmds.getAttr(attrPathB)

                        # make sure the attributes are settable before trying setAttr
                        if cmds.getAttr(attrPathA, se=True):
                            cmdStack.append(cmds.setAttr, attrPathA, attrValB)

                        if cmds.getAttr(attrPathB, se=True):
                            cmdStack.append(cmds.setAttr, attrPathB, attrValA)

        doR = r and not self.neverDoR()
        doT = t and not self.neverDoT()
        if not doR and not doT:
            return

        worldSpace = self.getWorldSpace()
        matrixA = getRelativeMatrix(self.controlA, self.mirrorPlane) if worldSpace \
            else getLocalMatrix(self.controlA)

        matrixB = getRelativeMatrix(self.controlB, self.mirrorPlane) if worldSpace \
            else getLocalMatrix(self.controlB)

        # Note the swap here
        mirroredMatrixA = self.mirrorMatrix(matrixB)
        mirroredMatrixB = self.mirrorMatrix(matrixA)

        if self.mirrorPlane:
            mirroredMatrixA = relativeToWorld(mirroredMatrixA, self.mirrorPlane)
            mirroredMatrixB = relativeToWorld(mirroredMatrixB, self.mirrorPlane)

        # Do rotation
        if doR:
            if worldSpace:
                cmdStack.append(setWorldRotMatrix, self.controlA, mirroredMatrixA)
                cmdStack.append(setWorldRotMatrix, self.controlB, mirroredMatrixB)
            else:
                cmdStack.append(setLocalRotMatrix, self.controlA, mirroredMatrixA)
                cmdStack.append(setLocalRotMatrix, self.controlB, mirroredMatrixB)

        # Do position
        if doT:
            posA = mirroredMatrixA.get_position()
            posB = mirroredMatrixB.get_position()
            if worldSpace:
                if cmds.getAttr('%s.t' % self.controlA, se=True):
                    cmdStack.append(cmds.move, posA[0], posA[1], posA[2], self.controlA, ws=True, rpr=True)

                if cmds.getAttr('%s.t' % self.controlB, se=True):
                    cmdStack.append(cmds.move, posB[0], posB[1], posB[2], self.controlB, ws=True, rpr=True)
            else:
                if cmds.getAttr('%s.t' % self.controlA, se=True):
                    cmdStack.append(cmds.setAttr, '%s.t' % self.controlA, *posA)

                if cmds.getAttr('%s.t' % self.controlB, se=True):
                    cmdStack.append(cmds.setAttr, '%s.t' % self.controlB, *posB)

        if executeImmediately:
            cmdStack.execute()

    def mirror(self, controlAIsSource=True, t=True, r=True, other=True, cmdStack=None):
        '''
        mirrors the pose of controlA (or controlB if controlAIsSource is False) and
        puts it on the "other" control

        NOTE: if controlAIsSource is True, then the pose of controlA is mirrored
        and put on to controlB, otherwise the reverse is done
        '''
        executeImmediately = False
        if cmdStack is None:
            cmdStack = CommandStack()
            executeImmediately = True

        if self.isSingular():
            control = otherControl = self.controlA
        else:
            if controlAIsSource:
                control = self.controlB
                otherControl = self.controlA
            else:
                control = self.controlA
                otherControl = self.controlB

        # do the other attributes first - the parent attribute for example will change
        # the position so we need to set it before setting transforms
        if other:
            if not self.neverDoOther():
                if not self.isSingular():
                    for attr in getKeyableAttrs(otherControl):
                        attrPath = '%s.%s' % (control, attr)
                        otherAttrPath = '%s.%s' % (otherControl, attr)

                        if cmds.objExists(attrPath):
                            if cmds.getAttr(attrPath, se=True):
                                cmdStack.append(cmds.setAttr, attrPath, cmds.getAttr(otherAttrPath))

        # If we're not doing both rotation and translation, bail at this point
        if not r and not t:
            return

        # Otherwise, figure out the matrices
        worldSpace = self.getWorldSpace()
        matrix = getRelativeMatrix(otherControl, self.mirrorPlane) if worldSpace \
            else getLocalRotMatrix(otherControl)

        mirroredMatrix = self.mirrorMatrix(matrix)
        if self.mirrorPlane:
            mirroredMatrix = relativeToWorld(mirroredMatrix, self.mirrorPlane)

        # Do rotation
        if r and not self.neverDoR():
            if worldSpace:
                cmdStack.append(setWorldRotMatrix, control, mirroredMatrix)
            else:
                cmdStack.append(setLocalRotMatrix, control, mirroredMatrix)

        # Do position
        if t and not self.neverDoT():
            if cmds.getAttr('%s.t' % control, se=True):
                pos = mirroredMatrix.get_position()
                if worldSpace:
                    cmdStack.append(cmds.move, pos[0], pos[1], pos[2], control, ws=True, rpr=True)
                else:
                    cmdStack.append(cmds.setAttr, '%s.t' % control, *pos)

        if executeImmediately:
            cmdStack.execute()

    def match(self, controlAIsSource=True, t=True, r=True, other=True):
        '''
        pushes the pose of controlA (or controlB if controlAIsSource is False) to the
        "other" control

        NOTE: if controlAIsSource is True, then the pose of controlA is mirrored and
        copied and put on to controlB, otherwise the reverse is done
        '''

        # if this is a singular pair, bail - there's nothing to do
        if self.isSingular():
            return

        # NOTE:
        # restPoseB = restPoseA * offsetMatrix
        # and similarly:
        # so restPoseB * offsetMatrixInv = restPoseA

        if controlAIsSource:
            worldMatrix = getWorldRotMatrix(self.controlA)
            control = self.controlB
        else:
            worldMatrix = getWorldRotMatrix(self.controlB)
            control = self.controlA

        newControlMatrix = self.mirrorMatrix(worldMatrix)

        setWorldRotMatrix(control, newControlMatrix, t=False)
        setWorldRotMatrix(control, worldMatrix, r=False)

    def getOppositeControl(self, control):
        control = apiExtensions.asMObject(control)
        if apiExtensions.cmpNodes(control, self.controlA):
            return self.controlB
        elif apiExtensions.cmpNodes(control, self.controlB):
            return self.controlA

        raise ValueError("The node '%s' isn't part of this control pair!" % control)

def getPairNodesFromObjs(objs):
    '''
    given a list of objects, will return a minimal list of pair nodes
    '''
    pairs = set()
    for obj in objs:
        pairNode = ControlPair.GetPairNode(obj)
        if pairNode:
            pairs.add(pairNode)

    return list(pairs)

def getPairsFromObjs(objs):
    return [ControlPair(pair) for pair in getPairNodesFromObjs(objs)]

def getPairsFromSelection():
    return getPairsFromObjs(cmds.ls(sl=True))

def iterPairAndObj(objs, sort=False):
    '''
    yields a 2-tuple containing the pair node and the initializing object
    '''
    pairNodesVisited = set()
    if sort:
        objs = apiExtensions.sortByHierarchy(objs)

    for obj in objs:
        pairNode = ControlPair.GetPairNode(obj)
        if pairNode:
            if pairNode in pairNodesVisited:
                continue

            pairNodesVisited.add(pairNode)
            pair = ControlPair(pairNode)

            yield pair, obj

def setupMirroringFromNames(mandatoryTokens=('control', 'ctrl')):
    '''
    sets up control pairs for all parity based controls in the scene as determined by their names.
    '''

    # stick the tokens in a set and ensure they're lower-case
    mandatoryTokens = set([tok.lower() for tok in mandatoryTokens])

    visitedTransforms = set()
    for t in cmds.ls(type='transform'):
        if t in visitedTransforms:
            continue

        visitedTransforms.add(t)

        asNodeName = str_utils.NodeName(t)
        nameToks = asNodeName.split()
        if str_utils.getParityAndToken(nameToks)[0] is str_utils.Parity.NONE:
            continue

        containsMandatoryToken = False
        for tok in nameToks:
            if tok.lower() in mandatoryTokens:
                containsMandatoryToken = True
                break

        if not containsMandatoryToken:
            continue

        otherT = str_utils.swapParity(t)
        if otherT:
            otherAsNodeName = str_utils.NodeName(otherT)
            if cmds.objExists(str(otherT)):
                visitedTransforms.add(str(otherT))

                # Sort the controls into left and right - we want the left to be controlA and right to be controlB
                controlPairs = [(asNodeName.getParity(), asNodeName), (otherAsNodeName.get_parity(), otherAsNodeName)]
                controlPairs.sort()

                leftT, rightT = str(controlPairs[0][1]), str(controlPairs[1][1])

                ControlPair.Create(leftT, rightT)
                logger.info('creating a control pair on %s -> %s' % (leftT, rightT))

#end
