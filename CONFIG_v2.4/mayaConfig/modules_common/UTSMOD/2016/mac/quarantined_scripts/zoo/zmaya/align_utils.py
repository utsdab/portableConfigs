
from maya import cmds

from .. import vectors
from .. import misc
from . import apiExtensions
from . import constants
from . import maya_decorators

def alignSimple__(objToAlign, src):

    # try position first
    pos = cmds.xform(src, q=True, ws=True, rp=True)
    try:
        cmds.move(pos[0], pos[1], pos[2], objToAlign, a=True, ws=True, rpr=True)
    except RuntimeError:
        pass

    # rotation is a bit special because when querying the rotation we get back xyz world
    # rotations - so we need to change the rotation order to xyz, set the global rotation
    # then modify the rotation order while preserving orientation
    roAttrpath = '%s.ro' % objToAlign
    initialRo = cmds.getAttr(roAttrpath)
    rot = cmds.xform(src, q=True, ws=True, ro=True)
    try:
        cmds.setAttr(roAttrpath, 0)
        cmds.rotate(rot[0], rot[1], rot[2], objToAlign, a=True, ws=True)
        cmds.xform(objToAlign, p=True, roo=constants.MAYA_ROTATE_ORDER_STRS[initialRo])
    except RuntimeError:
        pass

def alignSimple(objToAlign, src):
    destMatrix = vectors.Matrix(cmds.getAttr('%s.worldMatrix' % src))
    objParentInvMatrix = vectors.Matrix.Identity(4)
    parent = cmds.listRelatives(objToAlign, p=True, pa=True)
    if parent:
        objParentInvMatrix = vectors.Matrix(cmds.getAttr('%s.worldInverseMatrix' % parent[0]))

    matrix = destMatrix * objParentInvMatrix

    # try to set translation - check whether all channels are settable
    pos = matrix.get_position()
    if cmds.getAttr('%s.t' % objToAlign, se=True):
        cmds.setAttr('%s.t' % objToAlign, *pos)

    # factor out any joint orient if applicable
    if cmds.objExists('%s.jo' % objToAlign):
        jo = cmds.getAttr('%s.jo' % objToAlign)[0]
        joMatrix = vectors.Matrix.FromEulerXYZ(*jo, degrees=True).expand(4)
        matrix = matrix * joMatrix.inverse()

    roo = cmds.getAttr('%s.rotateOrder' % objToAlign)
    rot = constants.MATRIX_ROTATION_ORDER_CONVERSIONS_TO[roo](matrix, True)

    # try to set rotation - check whether all channels are settable
    if cmds.getAttr('%s.r' % objToAlign, se=True):
        cmds.setAttr('%s.r' % objToAlign, *rot)

def alignSelection():
    sel = cmds.ls(sl=True, type='transform') or []
    if sel:
        src = sel[0]
        for obj in sel[1:]:
            alignSimple(obj, src)

@maya_decorators.d_undoBlock
def parentConstraint(parent, obj, maintainOffset=False):
    """
    Attempts to constrain obj to parent even if obj has locked attributes or
    some attributes are connected already
    :param obj: The node being constrained
    :return: Returns the parent constraint node created
    """

    # Try to perform a normal parent constraint. If that fails, then
    # try to create a tmp object and switch connections over one by one
    try:
        return cmds.parentConstraint(parent, obj, mo=maintainOffset)[0]
    except RuntimeError:
        pass

    tmp = cmds.createNode('transform')

    objParent = cmds.listRelatives(obj, parent=True)
    if objParent:
        cmds.parent(tmp, objParent)

    # Match rotate order
    cmds.setAttr('%s.ro' % tmp, cmds.getAttr('%s.ro' % obj))

    # Match transform
    alignSimple(tmp, obj)

    # Create the constraint
    constraintNode = cmds.parentConstraint(parent, tmp, mo=maintainOffset)

    # Parent the constraint node to the target
    cmds.parent(constraintNode, obj)

    def replaceInAttrPath(attrpath, node, replacementNode):
        splitIdx = attrpath.find('.')
        attrpathNode = attrpath[:splitIdx]

        if apiExtensions.cmpNodes(attrpathNode, node):
            return '%s%s' % (replacementNode, attrpath[splitIdx:])

        return attrpath

    # Now swap the connections
    cons = cmds.listConnections(constraintNode, plugs=True, connections=True, skipConversionNodes=True)
    for src, dest in misc.iterBy(cons, 2):
        srcAlt = replaceInAttrPath(src, tmp, obj)
        destAlt = replaceInAttrPath(dest, tmp, obj)

        if src != srcAlt or dest != destAlt:
            try:
                cmds.connectAttr(srcAlt, destAlt, f=True)
            except RuntimeError:
                pass

    # Delete the temporary transform
    cmds.delete(tmp)

    return constraintNode

#end
