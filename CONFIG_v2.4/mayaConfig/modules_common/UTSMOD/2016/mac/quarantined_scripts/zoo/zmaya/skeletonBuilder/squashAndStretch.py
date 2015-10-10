
from maya import cmds

from ... import vectors
from .. import mesh_utils
from . import control

def createSNSJoint(joint):
    """
    Creates the joint that hold the squash and stretch. Normally
    when a joint is non-uniformly scaled, its children shear. So
    to implement SNS we need to create a sibling joint with no
    children to hold the scale. The skinning data also needs to
    be transferred to this SNS joint
    :param joint: The joints to setup SNS joints
    """
    snsJoint = cmds.createNode('joint', n='%s_SNS' % joint)
    cmds.parent(snsJoint, joint, r=True)
    control.attrState(snsJoint, ('t', 'r'), lock=True, show=False)

    # Transfer weights from the original joint to the SNS joint
    mesh_utils.weightsToOther(joint, snsJoint)

    return snsJoint

def createSNSRig(snsJoint, driverJoint, axis=vectors.AX_X, maxScale=2, existingExpression=None):
    """
    Sets up the expression for squash and stretch
    :param snsJoint: The joint to scale
    :param driverJoint: This is the joint that drives the SNS
    :param axis: The translate axis on the driver
    :param maxScale: The maximum scale the SNS joint gets to
    :param existingExpression: If specified, this expression gets appended
    :return: The expression created
    """
    xprNode = existingExpression or cmds.createNode('expression')
    if isinstance(axis, basestring):
        axis = vectors.Axis.FromName(axis)

    axisStr = axis.asName()
    initValue = cmds.getAttr('%s.t%s' % (driverJoint, axisStr))
    gradient = (1 - maxScale) / initValue

    line = 'float $s = 1;\n' \
           'if(%(driverJoint)s.t%(axisStr)s <= %(initValue)s)\n' \
           '\t$s = min(%(gradient)s * %(driverJoint)s.t%(axisStr)s + %(maxScale)s, %(maxScale)s);\n' \
           'else\n\t$s = %(initValue)s / %(driverJoint)s.t%(axisStr)s;\n' \
           '%(snsJoint)s.sy = %(snsJoint)s.sz = $s;\n' \
           '%(snsJoint)s.sx = 1.0 / $s;\n' % locals()

    cmds.expression(xprNode, e=True, string=cmds.expression(xprNode, q=True, string=True) + line)

    return xprNode

def setupSNS(joints, drivers, axis=vectors.AX_X, maxScale=2):
    xpr = None
    for joint, driver in zip(joints, drivers):
        snsJoint = createSNSJoint(joint)
        xpr = createSNSRig(snsJoint, driver, axis, maxScale, xpr)

#end
