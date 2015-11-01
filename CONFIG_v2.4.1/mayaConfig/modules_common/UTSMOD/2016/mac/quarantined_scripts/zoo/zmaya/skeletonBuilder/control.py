
import logging

from maya import cmds
from maya import mel
from maya import OpenMaya

from ... import path
from ... import vectors
from ...vectors import Vector, Axis

from ..apiExtensions import asMObject

from . import rig_utils

logger = logging.getLogger(__name__)

# we use the absolute location of this script
CONTROL_DIRECTORY = path.Path(__file__).abs().up() / 'rig_control_shapes'

AX_X, AX_Y, AX_Z, AX_X_NEG, AX_Y_NEG, AX_Z_NEG = map(Axis, range(6))
DEFAULT_AXIS = AX_X

AXIS_ROTATIONS = {AX_X: (0, 0, -90),
                  AX_Y: (0, 0, 0),
                  AX_Z: (90, 0, 0),
                  AX_X_NEG: (0, 0, 90),
                  AX_Y_NEG: (180, 0, 0),
                  AX_Z_NEG: (-90, 0, 0)}

class BreakException(Exception): pass

class ShapeDesc(object):
    '''
    store shape preferences about a control
    '''

    NULL_SHAPE = None
    SKIN = 1

    DEFAULT_TYPE = 'ring'

    def __init__(self, curveType=DEFAULT_TYPE, axis=DEFAULT_AXIS, expand=0.04, joints=None):
        '''
        curveType must be a valid control preset name - defaults to ring if none is specified
        '''
        self.curveType = curveType
        self.axis = axis

        self.expand = expand
        if joints is None:
            self.joints = []
        else:
            self.joints = joints if isinstance(joints, (tuple, list)) else [joints]

    def __repr__(self):
        return 'ShapeDesc(%r, %r)' % (self.curveType, self.axis)

    __str__ = __repr__

DEFAULT_SHAPE_DESC = ShapeDesc()
SHAPE_NULL = ShapeDesc(ShapeDesc.NULL_SHAPE)

class PlaceDesc(object):
    WORLD = None

    PLACE_OBJ = 0
    ALIGN_OBJ = 1
    PIVOT_OBJ = 2

    Place = 0
    Align = 1
    Pivot = 2

    def __init__(self, placeAtObj=WORLD, alignToObj=PLACE_OBJ, snapPivotToObj=PLACE_OBJ):
        # now convert the inputs to actual objects, if they're not already
        self._placeData = placeAtObj, alignToObj, snapPivotToObj

        self.place = self.getObj(self.Place)
        self.align = self.getObj(self.Align)
        self.pivot = self.getObj(self.Pivot)

    def getObj(self, item):
        p = self._placeData[item]
        if isinstance(p, OpenMaya.MObject):
            return p

        if p == self.PLACE_OBJ:
            p = self._placeData[0]
        elif p == self.ALIGN_OBJ:
            p = self._placeData[1]
        elif p == self.PIVOT_OBJ:
            p = self._placeData[2]

        if isinstance(p, basestring):
            return p

        if isinstance(p, int):
            return self.WORLD

        if p is None:
            return self.WORLD

        return p

    def getLocation(self, obj):
        if obj is None:
            return Vector()

        return cmds.xform(obj, q=True, ws=True, rp=True)

    placePos = property(lambda self: self.getLocation(self.place))
    alignPos = property(lambda self: self.getLocation(self.align))
    pivotPos = property(lambda self: self.getLocation(self.pivot))

DEFAULT_PLACE_DESC = PlaceDesc()

class PivotModeDesc(object):
    BASE, MID, TOP = 0, 1, 2

ColourDesc = vectors.Colour
DEFAULT_COLOUR = ColourDesc('orange')

def _performOnAttr(obj, attrName, metaName, metaState):
    childAttrs = cmds.attributeQuery(attrName, n=obj, listChildren=True) or []

    if childAttrs:
        for a in childAttrs:
            cmds.setAttr('%s.%s' % (obj, a), **{metaName: metaState})
    else:
        cmds.setAttr('%s.%s' % (obj, attrName), **{metaName: metaState})

NORMAL = False, True
HIDE = None, False, False
LOCK_HIDE = True, False, False
NO_KEY = False, False, True
LOCK_SHOW = True, True, True

def attrState(objs, attrNames, lock=None, keyable=None, show=None, ignoreOnFailure=False):
    if not isinstance(objs, (list, tuple)):
        objs = [objs]

    objs = map(str, objs)

    if not isinstance(attrNames, (list, tuple)):
        attrNames = [attrNames]

    for obj in objs:
        for attrName in attrNames:

            try:
                # showInChannelBox(False) doesn't work if setKeyable is true - which is kinda dumb...
                if show is not None:
                    if not show:
                        _performOnAttr(obj, attrName, 'keyable', False)
                        keyable = None

                    _performOnAttr(obj, attrName, 'keyable', show)

                if lock is not None:
                    _performOnAttr(obj, attrName, 'lock', lock)

                if keyable is not None:
                    _performOnAttr(obj, attrName, 'keyable', keyable)
            except:

                # if we're not supposed to ignore failures, re-raise the exception
                if not ignoreOnFailure:
                    raise

AUTO_SIZE = None

DEFAULT_HIDE_ATTRS = ('scale', 'visibility')

def buildControl(name,
                 placementDesc=DEFAULT_PLACE_DESC,
                 pivotModeDesc=PivotModeDesc.MID,
                 shapeDesc=DEFAULT_SHAPE_DESC,
                 colour=DEFAULT_COLOUR,
                 constrain=True,
                 oriented=True,
                 offset=Vector((0, 0, 0)), offsetSpace=0,
                 size=Vector((1, 1, 1)), scale=1.0, autoScale=False,
                 parent=None, qss=None,
                 asJoint=False, freeze=True,
                 lockAttrs=('scale',), hideAttrs=DEFAULT_HIDE_ATTRS,
                 niceName=None,
                 displayLayer=None):
    '''
    deals with creating control objects in a variety of ways.

    the following args take "struct" like instances of the classes defined above,
    so look to them for more detail on defining those options

    displayLayer (int) will create layers (if doesn't exist) and add control shape to that layer.
    layer None or zero doesn't create.
    '''

    cmds.select(cl=True)
    if not isinstance(placementDesc, PlaceDesc):
        if isinstance(placementDesc, (list, tuple)):
            placementDesc = PlaceDesc(*placementDesc)
        else:
            placementDesc = PlaceDesc(placementDesc)

    if not isinstance(shapeDesc, ShapeDesc):
        if isinstance(shapeDesc, (list, tuple)):
            shapeDesc = ShapeDesc(*shapeDesc)
        else:
            shapeDesc = ShapeDesc(shapeDesc)

    offset = Vector(offset)


    # if we've been given a parent, cast it to be an MObject so that if its name path changes (for example if
    #parent='aNode' and we create a control called 'aNode' then the parent's name path will change to '|aNode' - yay!)
    if parent:
        parent = asMObject(parent)


    #unpack placement objects
    place, align, pivot = placementDesc.place, placementDesc.align, placementDesc.pivot


    #determine auto scale/size - if nessecary
    if autoScale:
        _scale = list(rig_utils.getJointSize([place] + (shapeDesc.joints or [])))
        _scale = sorted(_scale)[-1]
        if abs(_scale) < 1e-2:
            print 'AUTO SCALE FAILED', _scale, name, place
            _scale = scale

        scale = _scale

    if size is AUTO_SIZE:
        raise NotImplemented


    #build the curve shapes first
    if shapeDesc.curveType != ShapeDesc.NULL_SHAPE \
            and shapeDesc.curveType != ShapeDesc.SKIN:
        with open(getFileForShapeName(shapeDesc.curveType)) as f:
            createCmd = f.read()

        mel.eval(createCmd)
    else:
        cmds.select(cmds.group(em=True))

    sel = cmds.ls(sl=True)
    obj = asMObject(sel[0])


    #delete surface shapes
    surfaceShapes = cmds.listRelatives(sel, type='nurbsSurface')
    if surfaceShapes:
        cmds.delete(surfaceShapes)


    #if the joint flag is true, parent the object shapes under a joint instead of a transform node
    if asJoint:
        cmds.select(cl=True)
        j = cmds.joint()
        for s in cmds.listRelatives(obj, s=True, pa=True) or []:
            cmds.parent(s, j, add=True, s=True)

        cmds.setAttr('%s.radius' % j, keyable=False)
        cmds.setAttr('%s.radius' % j, cb=False)
        cmds.delete(obj)
        obj = asMObject(j)

    cmds.setAttr('%s.s' % obj, scale, scale, scale)

    # turn off child selection highlighting
    cmds.setAttr('%s.sech' % obj, 0)

    # rename the object - if no name has been given, call it "control".  if there is a
    # node with the name already, get maya to uniquify it
    if not name:
        name = 'control'

    if cmds.objExists(name):
        name = '%s#' % name

    cmds.rename(obj, name)


    #move the pivot - if needed
    cmds.makeIdentity(obj, a=1, s=1)
    shapeStrs = getShapeStrs(obj)
    if pivotModeDesc == PivotModeDesc.TOP:
        for s in shapeStrs:
            cmds.move(0, -scale / 2.0, 0, s, r=True)
    elif pivotModeDesc == PivotModeDesc.BASE:
        for s in shapeStrs:
            cmds.move(0, scale / 2.0, 0, s, r=True)


    #rotate it accordingly
    rot = AXIS_ROTATIONS[shapeDesc.axis]
    cmds.rotate(rot[0], rot[1], rot[2], obj, os=True)
    cmds.makeIdentity(obj, a=1, r=1)


    #if the user wants the control oriented, create the orientation group and parent the control
    grp = obj
    if oriented:
        grp = cmds.group(em=True, n="%s_space#" % obj)
        cmds.parent(obj, grp)
        attrState(grp, ['s', 'v'], *LOCK_HIDE)
        if align is not None:
            cmds.delete(cmds.parentConstraint(align, grp))


    #place and align
    if place:
        cmds.delete(cmds.pointConstraint(place, grp))

    if align:
        cmds.delete(cmds.orientConstraint(align, grp))
    else:
        cmds.rotate(0, 0, 0, grp, a=True, ws=True)


    #if the parent exists - parent the new control to the given parent
    if parent is not None:
        grp = cmds.parent(grp, parent)[0]


    #do offset
    if offset:
        for s in getShapeStrs(obj):
            cmds.move(offset[0], offset[1], offset[2], s, r=True, os=True)

    if freeze:
        cmds.makeIdentity(obj, a=1, r=1)
        cmds.makeIdentity(obj, a=1, t=1)


    #now snap the pivot to alignpivot object if it exists
    if pivot is not None and cmds.objExists(pivot):
        p = placementDesc.pivotPos
        cmds.move(p[0], p[1], p[2], '%s.rp' % obj, '%s.sp' % obj, a=True, ws=True, rpr=True)


    #constrain the target object to this control?
    if constrain:
        #check to see if the transform is constrained already - if so, bail.  buildControl doesn't do multi constraints
        if not cmds.listConnections(pivot, d=0, type='constraint'):
            if place:
                cmds.parentConstraint(obj, pivot, mo=True)
                setItemRigControl(pivot, obj)


    #add to a selection set if desired
    if qss is not None:
        cmds.sets(obj, add=qss)


    #hide and lock attributes
    attrState(obj, lockAttrs, lock=True)
    attrState(obj, hideAttrs, show=False)

    if niceName:
        setNiceName(obj, niceName)

    # display layer
    if displayLayer and not int(displayLayer) <= 0:
        layerName = 'ctrl_%d' % int(displayLayer)
        allLayers = cmds.ls(type='displayLayer')

        if layerName in allLayers:
            layer = layerName
        else:
            layer = cmds.createDisplayLayer(n=layerName, number=1, empty=True)
            cmds.setAttr('%s.color' % layer, 24 + int(displayLayer))

        for s in cmds.listRelatives(obj, s=True, pa=True) or []:
            cmds.connectAttr('%s.drawInfo.visibility' % layer, '%s.v' % s)
            cmds.connectAttr('%s.drawInfo.displayType' % layer, '%s.overrideDisplayType' % s)

    return obj

def buildControlAt(name, *a, **kw):
    kw['constrain'] = False
    return buildControl(name, *a, **kw)

def buildNullControl(name, *a, **kw):
    kw['shapeDesc'] = SHAPE_NULL
    kw['oriented'] = False
    kw['constrain'] = False

    return buildControl(name, *a, **kw)

def buildAlignedNull(alignTo, name=None, *a, **kw):
    if name is None:
        name = 'alignedNull'

    # Set the default kwargs dict
    defaultKw = dict(shapeDesc=SHAPE_NULL, constrain=False, oriented=False, freeze=False)
    defaultKw.update(kw)

    return buildControl(name, alignTo, *a, **defaultKw)

def setItemRigControl(item, control):
    '''
    used to associate an item within a skeleton part with a rig control
    '''
    attrPath = '%s._skeletonPartRigControl' % item
    if not cmds.objExists(attrPath):
        cmds.addAttr(item, ln='_skeletonPartRigControl', at='message')

    cmds.connectAttr('%s.message' % control, attrPath, f=True)

    return True

def getItemRigControl(item):
    '''
    returns the control associated with the item within a skeleton part, or None
    if there is no control driving the item
    '''
    attrPath = '%s._skeletonPartRigControl' % item
    if cmds.objExists(attrPath):
        cons = cmds.listConnections(attrPath, d=False)
        if cons:
            return cons[0]

    return None

def getNiceName(obj):
    attrPath = '%s._NICE_NAME' % obj
    if cmds.objExists(attrPath):
        return cmds.getAttr(attrPath)

    return None

def setNiceName(obj, niceName):
    attrPath = '%s._NICE_NAME' % obj
    if not cmds.objExists(attrPath):
        cmds.addAttr(obj, ln='_NICE_NAME', dt='string')

    cmds.setAttr(attrPath, niceName, type='string')

SHAPE_TO_COMPONENT_NAME = {'nurbsSurface': 'cv',
                           'nurbsCurve': 'cv',
                           'mesh': 'vtx',
}

def getShapeStrs(obj):
    '''
    returns a list of names to refer to all components for all shapes
    under the given object
    '''
    global SHAPE_TO_COMPONENT_NAME

    geo = []
    shapes = cmds.listRelatives(obj, s=True, pa=True) or []
    for s in shapes:
        nType = str(cmds.nodeType(s))
        cName = SHAPE_TO_COMPONENT_NAME[nType]
        geo.append("%s.%s[*]" % (s, cName))

    return geo

def getControlShapeFiles():
    shapes = []
    if CONTROL_DIRECTORY.exists():
        shapes = [f for f in CONTROL_DIRECTORY.files() if f.hasExtension('shape')]

    return shapes

CONTROL_SHAPE_DICT = {}
for f in getControlShapeFiles():
    CONTROL_SHAPE_DICT[f.name().split('.')[-1].lower()] = f

def getFileForShapeName(shapeName):
    try:
        return CONTROL_SHAPE_DICT[shapeName.lower()]
    except KeyError:
        raise ValueError("No such shape file (%s) exists!" % shapeName)

#end
