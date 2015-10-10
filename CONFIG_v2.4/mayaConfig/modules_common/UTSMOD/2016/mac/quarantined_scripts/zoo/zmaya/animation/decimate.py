
from maya import cmds

from .. import maya_decorators

TRANSLATION_ATTRNAMES = set(('translateX', 'translateY', 'translateZ'))
ROTATION_ATTRNAMES = set(('rotateX', 'rotateY', 'rotateZ'))

TRANSLATION, ROTATION, OTHER = range(3)

@maya_decorators.d_undoBlock
def decimateKeys(curve, keyTimes, tolerance):
    '''
    Given a curve or an attrpath will remove redundant keys.
    '''

    # slice off start and end keys - they need to be preserved
    keyTimes = keyTimes[1:-1]

    # now generate a list of pre values for all the key times
    # NOTE: maya expects a tuple for the t arg for some reason - hence the explicit cast
    preValues = cmds.keyframe(curve, q=True, t=(keyTimes[0], keyTimes[-1]), vc=True)

    for time, preValue in zip(keyTimes, preValues):
        cmds.cutKey(curve, t=(time,), cl=True)
        postValue = cmds.keyframe(curve, q=True, t=(time,), ev=True)[0]
        if abs(postValue - preValue) > tolerance:
            cmds.undo()

def decimateCurve(curve, tolerance):
    '''
    Given a curve or an attrpath will remove redundant keys.
    '''
    decimateKeys(curve, cmds.keyframe(curve, q=True) or [], tolerance)

@maya_decorators.d_undoBlock
def decimate(node, threshold=1e-3, translateThreshold=1e-3, rotationThreshold=0.25):
    '''
    Calls decimateCurve for all keyable attributes on the given node.

    The is automatically threshold for translation and rotation.
    '''
    attrs = set(cmds.listAttr(node, keyable=True, visible=True, scalar=True) or [])

    translates = 'translateX', 'translateY', 'translateZ'
    rotates = 'rotateX', 'rotateY', 'rotateZ'

    # treat pos and rot differently in terms of their tolerances
    for attr in translates:
        if attr in attrs:
            attrs.remove(attr)
            decimateCurve('%s.%s' % (node, attr), translateThreshold)

    for attr in rotates:
        if attr in attrs:
            attrs.remove(attr)
            decimateCurve('%s.%s' % (node, attr), rotationThreshold)

    for attr in rotates:
        if attr in attrs:
            decimateCurve('%s.%s' % (node, attr), threshold)

def curveType(curve):
    destAttrpath = cmds.listConnections(curve, s=False, p=True)[0]
    node, attr = destAttrpath.split('.')
    if cmds.objectType(node, isAType='transform'):
        if attr in TRANSLATION_ATTRNAMES:
            return TRANSLATION
        elif attr in ROTATION_ATTRNAMES:
            return ROTATION

    return OTHER

@maya_decorators.d_undoBlock
def decimateSelection():
    '''
    Calls decimate for all nodes in the selection.
    '''

    # do we have selected keys?
    selCurves = cmds.keyframe(q=True, sl=True, n=True)
    if selCurves:
        for curve in selCurves:
            keyTimes = cmds.keyframe(curve, q=True, sl=True)
            if keyTimes:
                tolerance = 1e-3
                if curveType(curve) == ROTATION:
                    tolerance = 0.25

                decimateKeys(curve, keyTimes, tolerance)

    # if not lets see if we have selected nodes
    else:
        sel = cmds.ls(sl=True) or []
        for node in sel:
            decimate(node)

#end
