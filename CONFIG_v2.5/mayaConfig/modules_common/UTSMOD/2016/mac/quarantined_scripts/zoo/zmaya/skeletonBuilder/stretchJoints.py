
from maya import cmds

from baseRigPart import *
from . import constants
from . import control

def rigTwistStretch(limbSectionBase, limbSectionEnd, twists):
    axis = constants.BONE_AIM_AXIS
    axisStr = axis.asName()

    basePos = vectors.Vector(cmds.xform(limbSectionBase, q=True, ws=True, rp=True))
    endPos = vectors.Vector(cmds.xform(limbSectionEnd, q=True, ws=True, rp=True))
    initialLength = (endPos - basePos).length()

    expressionLines = []
    for j in twists:
        ratio = cmds.getAttr('%(j)s.t%(axisStr)s' % locals()) / initialLength
        expressionLines.append('%(j)s.t%(axisStr)s = %(limbSectionEnd)s.t%(axisStr)s * %(ratio)s;' % locals())

    return cmds.expression(string='\n'.join(expressionLines), n='%s_stretchExpression' % limbSectionBase)

def rigLimbStretch(ctrlNode, limbJoints, parity=str_utils.Parity.LEFT):
    """
    :param ctrlNode: the rig control that ultimately drives stretch
    :param limbJoints: the joints that define the limb (typically the bicep, elbow, wrist)
    :param parity:
    """

    ikFkAttrpath = '%s.ikBlend' % ctrlNode
    axis = constants.BONE_AIM_AXIS

    # setup some current unit variables, and take parity into account
    stretchAuto = "autoStretch"
    stretchName = "stretch"
    parityFactor = parity.asMultiplier()

    cmds.addAttr(ctrlNode, ln=stretchAuto, at='double', min=0, max=1, dv=1)
    cmds.addAttr(ctrlNode, ln=stretchName, at='double', min=0, max=10, dv=0)
    control.attrState(ctrlNode, (stretchAuto, ), keyable=True)

    # Determine the length of the limb
    clientLengths = [0]
    initialLimbLength = 0
    for n, c in enumerate(limbJoints[:-1]):
        thisPos = vectors.Vector(cmds.xform(c, q=True, ws=True, rp=True))
        nextPos = vectors.Vector(cmds.xform(limbJoints[n + 1], q=True, ws=True, rp=True))
        l = (thisPos - nextPos).length()
        clientLengths.append(l)
        initialLimbLength += l

    # Build the network to measure limb length
    grp_a = cmds.createNode('transform', name='%s_measureStart' % ctrlNode)
    loc_a = cmds.createNode('locator', parent=grp_a, name='%s_limbStart' % ctrlNode)
    loc_b = cmds.createNode('locator', parent=ctrlNode, name='%s_limbEnd' % ctrlNode)
    measure = cmds.createNode('distanceDimShape', parent=ctrlNode, name='%s_limbLength' % ctrlNode)

    cmds.parent(grp_a, ctrlNode)
    cmds.pointConstraint(limbJoints[0], grp_a)
    cmds.connectAttr('%s.worldPosition[0]' % loc_a, '%s.startPoint' % measure)
    cmds.connectAttr('%s.worldPosition[0]' % loc_b, '%s.endPoint' % measure)

    # Hide the above nodes
    for n in (loc_a, loc_b, measure):
        cmds.setAttr('%s.v' % n, 0)

    # Unlock the translation
    axisStr = axis.asName()
    control.attrState(limbJoints, 't' + axisStr, lock=False, show=True)

    # Build the stretch expression
    expressionLines = [
        'float $naturalLength = %s;' % initialLimbLength,
        'float $manualStretchLength = $naturalLength * %(ctrlNode)s.%(stretchName)s / 10;' % locals(),
        'float $autoStretchLength = %(measure)s.distance * %(ctrlNode)s.%(stretchAuto)s;' % locals(),

        # Clamp to the natural limb length
        'float $resultingLength = max($autoStretchLength + $manualStretchLength, $naturalLength);',

        # Blend to initial length if in fk mode
        '$resultingLength = %(ikFkAttrpath)s * $resultingLength + (1 - %(ikFkAttrpath)s) * $naturalLength;' % locals(),
    ]

    # Add stretch to the limb joints
    for j, l in zip(limbJoints, clientLengths)[1:]:
        initialT = cmds.getAttr('%s.t%s' % (j, axisStr))
        ratio = l / initialLimbLength
        expressionLines.append(
            '%(j)s.t%(axisStr)s = $resultingLength * %(ratio)s;' % locals())

    cmds.expression(string='\n'.join(expressionLines), name='%s_stretchExpression' % ctrlNode)

    # Lock and hide the translation again...
    control.attrState(limbJoints, 't' + axisStr, lock=True, show=False)

#end
