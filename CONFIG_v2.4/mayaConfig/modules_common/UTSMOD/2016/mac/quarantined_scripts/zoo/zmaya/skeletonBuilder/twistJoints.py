
from maya import cmds

from ... import vectors
from .. import align_utils
from .. import apiExtensions
from .. import maya_decorators
from . import control

def placeTwistJoints(end, twists):
    endPos = vectors.Vector(cmds.getAttr('%s.t' % end)[0])
    frac = 1.0 / (len(twists) + 1)

    for n, j in enumerate(twists):
        pos = endPos * ((n + 1) * frac)
        cmds.setAttr('%s.t' % j, *pos)
        cmds.setAttr('%s.jo' % j, 0, 0, 0)

@maya_decorators.d_maintainSceneSelection
def buildTwistJoints(start, end, count=3, prefix='', suffix=''):
    nameTemplate = 'twist%d'
    if prefix:
        nameTemplate = str(prefix) + '_' + nameTemplate

    if suffix:
        nameTemplate += '_' + str(suffix)

    twists = []
    for n in range(count):
        j = apiExtensions.asMObject(
            cmds.createNode(
                'joint', name=nameTemplate % (n + 1)))

        cmds.parent(j, start, r=True)
        twists.append(j)

    placeTwistJoints(end, twists)

    return twists

@maya_decorators.d_maintainSceneSelection
def rigTwistJoints(
        serverPlacement, serverParent,
        twistPlacement, twistParent,
        twists, axis=vectors.AX_Z):

    if isinstance(axis, basestring):
        axis = vectors.Axis.FromName(axis)

    twistServer = apiExtensions.asMObject(
        cmds.createNode('joint', n='%s_twist_server' % serverParent))

    cmds.parent(twistServer, serverParent, r=True)
    align_utils.alignSimple(twistServer, serverPlacement)
    cmds.setAttr('%s.r' % twistServer, 0, 0, 0)

    tmpEnd = cmds.createNode('joint')
    cmds.parent(tmpEnd, twistServer, r=True)
    align_utils.alignSimple(tmpEnd, twistPlacement)

    # Create the ik handle
    handle, effector = cmds.ikHandle(startJoint=twistServer, endEffector=tmpEnd, solver='ikSCsolver')
    cmds.parent(handle, twistParent)

    # Disconnect the effector from the tmpEnd joint and delete tmpEnd
    for ax in ('x', 'y', 'z'):
        cmds.delete('%s.t' % effector + ax, icn=True)

    cmds.delete(tmpEnd)

    # Now create the expression to distribute twist rotations
    spread = 1.0 / len(twists)
    axisStr = axis.asName()
    expressionLines = []

    # Add the rotation distribution expression lines
    for n, joint in enumerate(twists):
        ratio = 1 - spread * n
        attr = 'twist%02d' % (n + 1)
        cmds.addAttr(twistServer, ln='twist%02d' % (n + 1), at='double', k=True)
        cmds.setAttr('%s.%s' % (twistServer, attr), ratio)
        expressionLines.append(
            '%(joint)s.r%(axisStr)s = %(twistServer)s.r%(axisStr)s * %(twistServer)s.%(attr)s;' % locals())

    cmds.expression(string='\n'.join(expressionLines), name='sb_twistExpr_%s' % serverParent)

    # lock and hide twist server attributes
    control.attrState(twistServer, ('t', 's', 'v'), *control.LOCK_HIDE)

#end
