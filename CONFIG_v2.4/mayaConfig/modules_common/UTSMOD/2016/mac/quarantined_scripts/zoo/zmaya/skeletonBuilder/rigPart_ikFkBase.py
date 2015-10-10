from maya import cmds

from .. import align_utils
from .. import maya_decorators
from baseRigPart import *

ARM_NAMING_SCHEME = 'arm', 'bicep', 'elbow', 'wrist'
LEG_NAMING_SCHEME = 'leg', 'thigh', 'knee', 'ankle'

class SwitchableMixin(object):
    """
    NOTE: we can't make this an interface class because rig part classes already have a pre-defined
    metaclass...  :(
    """

    def __notimplemented(self):
        raise NotImplemented("This baseclass method hasn't been implemented on the %s class" % type(self).__name__)

    def switchToFk(self, key=False):
        """
        should implement the logic to switch this chain from IK to FK
        """
        self.__notimplemented()

    def switchToIk(self, key=False):
        """
        should implement the logic to switch this chain from FK to IK
        """
        self.__notimplemented()

    def isIk(self):
        """
        should implement the logic to determine whether this chain is in IK mode or not
        """
        self.__notimplemented()

    def placePole(self, key=False):
        """
        should implement the logic to place the pole vector at a sensible location without affecting the pose
        """
        self.__notimplemented()

class IkFkBase(PrimaryRigPart, SwitchableMixin):
    """
    super class functionality for biped limb rigs - legs, arms and even some quadruped rigs inherit
    from this class
    """
    NAMED_NODE_NAMES = 'ikSpace', 'fkSpace', 'ikHandle', 'endOrient', 'poleTrigger'
    IK_BLEND_ATTRNAME = 'ikBlend'
    IK_ON_VALUE = 1
    IK_OFF_VALUE = 0

    def buildAllPurposeLocator(self, nodePrefix):
        allPurposeObj = cmds.spaceLocator(name="%s_all_purpose_loc%s" % (nodePrefix, self.getSuffix()))[0]
        control.attrState(allPurposeObj, 's', *control.LOCK_HIDE)
        control.attrState(allPurposeObj, 'v', *control.HIDE)
        cmds.parent(allPurposeObj, WorldPart.Create().getControl('control'))

        return allPurposeObj

    def getIkHandle(self):
        return self.getControl('ikHandle')

    def getFkControls(self):
        return self.getControl('fkUpper'), self.getControl('fkMid'), self.getControl('fkLower')

    def getIkControls(self):
        return self.getControl('control'), self.getControl('poleControl'), self.getIkHandle()

    def switchToFk(self, key=False):
        control, poleControl, handle = self.getIkControls()
        joints = self.getFkControls()

        if handle is None or not cmds.objExists(handle):
            logger.error('No ikHandle specified')
            return

        # make sure ik is on before querying rotations
        cmds.setAttr('%s.%s' % (control, self.IK_BLEND_ATTRNAME), self.IK_ON_VALUE)
        rots = []
        for j in joints:
            rot = cmds.getAttr("%s.r" % j)[0]
            rots.append(rot)

        #now turn ik off and set rotations for the joints
        cmds.setAttr('%s.%s' % (control, self.IK_BLEND_ATTRNAME), self.IK_OFF_VALUE)
        for j, rot in zip(joints, rots):
            for ax, r in zip(('x', 'y', 'z'), rot):
                if cmds.getAttr('%s.r%s' % (j, ax), se=True):
                    cmds.setAttr('%s.r%s' % (j, ax), r)

        align_utils.alignSimple(joints[2], control)
        if key:
            cmds.setKeyframe(joints)
            cmds.setKeyframe('%s.%s' % (control, self.IK_BLEND_ATTRNAME))

        # modify the selection - make sure there are no ik controls selected and add the
        # end fk control to the selection
        cmds.select(self.getIkControls(), d=True)
        cmds.select(joints[-1], add=True)

    def switchToIk(self, key=False, _isBatchMode=False):
        control, poleControl, handle = self.getIkControls()
        joints = self.getFkControls()

        if handle is None or not cmds.objExists(handle):
            logger.error('No ikHandle specified')
            return

        align_utils.alignSimple(control, joints[2])
        if poleControl:
            if cmds.objExists(poleControl):
                pos = rig_utils.findPolePosition(joints[2], joints[1], joints[0])
                cmds.move(pos[0], pos[1], pos[2], poleControl, a=True, ws=True, rpr=True)
                if key:
                    cmds.setKeyframe(poleControl, at=('t',))

        cmds.setAttr('%s.%s' % (control, self.IK_BLEND_ATTRNAME), self.IK_ON_VALUE)
        if key:
            cmds.setKeyframe(control, at=('t', 'r'))
            if not _isBatchMode:
                cmds.setKeyframe(control, at=self.IK_BLEND_ATTRNAME)

        # modify the selection - make sure there are no fk controls selected and add the
        # end ik control to the selection
        cmds.select(self.getFkControls(), d=True)
        cmds.select(control, add=True)

    def isIk(self):
        """
        Returns whether the part is in ik mode currently or not
        """
        control, poleControl, handle = self.getIkControls()

        return cmds.getAttr('%s.%s' % (control, self.IK_BLEND_ATTRNAME)) == self.IK_ON_VALUE

    def placePole(self, key=False):
        fkControls = list(self.getFkControls())
        fkControls.reverse()

        pos = rig_utils.findPolePosition(*fkControls)

        poleControl = self.getIkControls()[1]
        cmds.move(pos[0], pos[1], pos[2], poleControl, rpr=True)
        if key:
            cmds.setKeyframe(poleControl)

    @maya_decorators.d_undoBlock
    @maya_decorators.d_maintainSceneSelection
    def fixMidFk(self):
        self.switchToIk(False)
        self.switchToFk(False)

class MidBuildContainer(object):
    pass

def buildIkFkBase(part, nameScheme=ARM_NAMING_SCHEME, alignEnd=True):
    assert isinstance(part, RigPart)
    data = MidBuildContainer()

    data.nameScheme = nameScheme
    data.alignEnd = alignEnd

    data.bicep, data.elbow, data.wrist = bicep, elbow, wrist = part.getSkeletonPart().getIkFkItems()
    colour = part.getParityColour()

    suffix = part.getSuffix()
    ikBlendAttrName = part.IK_BLEND_ATTRNAME

    # get the world part/control
    worldPart = part.getWorldPart()
    worldControl = worldPart.getControl('control')
    partsNode = worldPart.getNamedNode('parts')

    # build the fk controls
    data.fkSpace = control.buildAlignedNull(bicep, "fk_%sSpace%s" % (nameScheme[0], suffix))
    data.driverUpper = control.buildControl("fk_%sControl%s" % (nameScheme[1], suffix), bicep,
                                            control.PivotModeDesc.MID, shapeDesc=control.ShapeDesc('sphere'),
                                            colour=colour, asJoint=True, oriented=False, scale=part.scale,
                                            parent=data.fkSpace)

    data.driverMid = control.buildControl("fk_%sControl%s" % (nameScheme[2], suffix), elbow,
                                          control.PivotModeDesc.MID, shapeDesc=control.ShapeDesc('sphere'),
                                          colour=colour, asJoint=True, oriented=False, scale=part.scale,
                                          parent=data.driverUpper)

    data.driverLower = control.buildControl("fk_%sControl%s" % (nameScheme[3], suffix),
                                            control.PlaceDesc(wrist, wrist if alignEnd else None),
                                            shapeDesc=control.ShapeDesc('sphere'), colour=colour, asJoint=True,
                                            oriented=False, constrain=False, scale=part.scale,
                                            parent=data.driverMid)

    data.fkControls = data.driverUpper, data.driverMid, data.driverLower
    control.attrState(data.fkControls, ('t', 'radi'), *control.LOCK_HIDE)

    # build the ik controls
    data.ikSpace = control.buildAlignedNull(data.wrist, "ik_%sSpace%s" % (data.nameScheme[0], suffix),
                                            parent=worldControl)
    data.ikHandle = apiExtensions.asMObject(
        cmds.ikHandle(fs=1, sj=data.driverUpper, ee=data.driverLower, solver='ikRPsolver')[0])
    data.control = limbControl = control.buildControl(
        '%sControl%s' % (data.nameScheme[0], suffix),
        control.PlaceDesc(data.wrist, data.wrist if data.alignEnd else None),
        shapeDesc=control.ShapeDesc('cube'), colour=colour,
        scale=part.scale, constrain=False, parent=data.ikSpace)

    cmds.rename(data.ikHandle, '%sIkHandle%s' % (data.nameScheme[0], suffix))
    cmds.xform(data.control, p=True, rotateOrder='yzx')
    cmds.setAttr('%s.snapEnable' % data.ikHandle, False)
    cmds.setAttr('%s.v' % data.ikHandle, False)

    cmds.addAttr(data.control, ln=ikBlendAttrName, shortName='ikb', dv=1, min=0, max=1, at='double')
    cmds.addAttr(data.control, ln='fkVis', at='bool')
    cmds.setAttr('%s.%s' % (data.control, ikBlendAttrName), keyable=True)
    cmds.connectAttr('%s.%s' % (data.control, ikBlendAttrName), '%s.ikBlend' % data.ikHandle)

    control.attrState(data.ikHandle, 'v', *control.LOCK_HIDE)
    cmds.parent(data.ikHandle, data.control)

    # build the pole control
    polePos = rig_utils.findPolePosition(data.driverLower, data.driverMid, data.driverUpper, 5)
    data.poleControl = control.buildControl(
        "%s_poleControl%s" % (data.nameScheme[0], suffix),
        control.PlaceDesc(data.elbow, control.PlaceDesc.WORLD),
        shapeDesc=control.ShapeDesc('sphere'), colour=colour, constrain=False,
        parent=worldControl, scale=part.scale * 0.5)

    data.poleControlSpace = poleControlSpace = baseSkeletonPart.getNodeParent(data.poleControl)
    control.attrState(data.poleControlSpace, 'v', lock=False, show=True)

    cmds.move(polePos[0], polePos[1], polePos[2], data.poleControlSpace, a=True, ws=True, rpr=True)
    cmds.move(polePos[0], polePos[1], polePos[2], data.poleControl, a=True, ws=True, rpr=True)
    cmds.makeIdentity(data.poleControlSpace, a=True, t=True)
    cmds.setAttr('%s.v' % data.poleControl, True)

    cmds.poleVectorConstraint(data.poleControl, data.ikHandle)

    # build the pole selection trigger
    data.lineNode = control.buildControl(
        "%s_poleSelectionTrigger%s" % (data.nameScheme[0], suffix),
        shapeDesc=control.ShapeDesc('sphere'),
        colour=control.ColourDesc('darkblue'),
        scale=part.scale, constrain=False,
        oriented=False, parent=data.ikSpace)

    data.lineStart, data.lineEnd, data.lineShape = rig_utils.buildAnnotation(data.lineNode)

    cmds.parent(data.lineStart, data.poleControl)
    cmds.delete(cmds.pointConstraint(data.poleControl, data.lineStart))
    cmds.pointConstraint(data.elbow, data.lineNode)
    control.attrState(data.lineNode, ('t', 'r'), *control.LOCK_HIDE)

    # Make the actual line unselectable
    cmds.setAttr('%s.template' % data.lineStart, 1)

    # Setup constraints to the wrist - it is handled differently because it needs to blend
    # between the ik and fk chains (the other controls are handled by maya)
    data.endOrient = control.buildAlignedNull(
        data.wrist, "%s_follow%s_space" % (data.nameScheme[3], suffix), parent=data.driverMid, freeze=False)

    control.setItemRigControl(wrist, data.endOrient)
    control.setNiceName(data.endOrient, 'Fk %s' % data.nameScheme[3])

    # Constrain the wrist to the end orient
    wristConstraint = cmds.parentConstraint(data.endOrient, wrist)[0]
    cmds.setAttr('%s.interpType' % wristConstraint, 2)  # 2 is shortest

    # Constrain the end orient between the fk wrist control and the ik arm control
    # but delete the weight attrs afterward... We'll use target[n].targetWeight
    endOrientConstraint = data.endOrientConstraint = cmds.orientConstraint(
        data.control, data.driverLower, data.endOrient, mo=True)[0]

    # Build expressions for fk blending and control visibility
    cmds.expression(
        s='%(endOrientConstraint)s.w0 = %(limbControl)s.%(ikBlendAttrName)s;\n'
          '%(endOrientConstraint)s.w1 = 1 - %(limbControl)s.%(ikBlendAttrName)s;\n'
          'if (%(limbControl)s.%(ikBlendAttrName)s == 0) {%(limbControl)s.v = 0; %(limbControl)s.fkVis = 1;}\n'
          'else if (%(limbControl)s.%(ikBlendAttrName)s == 1) {%(limbControl)s.v = 1; %(limbControl)s.fkVis = 0;}\n'
          'else {%(limbControl)s.v = 1; %(limbControl)s.fkVis = 1;};' % locals(),
        n='constraintAndVisSwitch')

    # Connect other controls to the vis attributes
    cmds.connectAttr('%s.v' % data.control, '%s.v' % data.poleControlSpace, f=True)
    cmds.connectAttr('%s.v' % data.control, '%s.v' % data.lineNode, f=True)
    for driver in (data.driverUpper, data.driverMid, data.driverLower):
        for shape in cmds.listRelatives(driver, s=True, pa=True):
            cmds.connectAttr('%s.fkVis' % data.control, '%s.v' % shape, f=True)

    # Add set pole to fk pos command to pole control
    poleTrigger = triggered.Trigger.Create(data.poleControl, data.fkControls)
    poleTrigger.createMenu('Place pole sensibly', RigMenuCommand).setCmdStr('thisRig.placePole()')
    poleTrigger.createMenu('Place pole sensibly for all keys', RigMenuCommand).setCmdStr(
        'from zoo.zmaya.animation import switching; switching.placePoleForAnimatedPart(thisRig)')

    limbTrigger = triggered.Trigger.Create(data.control)
    limbTrigger.createMenu('Switch to FK', RigMenuCommand).setCmdStr('thisRig.switchToFk()')
    limbTrigger.createMenu('Switch to FK for all keys', RigMenuCommand).setCmdStr(
        'from zoo.zmaya.animation import switching; switching.switchToFkForAnimatedPart(thisRig)')
    limbTrigger.createMenu('Switch to IK', RigMenuCommand).setCmdStr('thisRig.switchToIk()')
    limbTrigger.createMenu('Switch to IK for all keys', RigMenuCommand).setCmdStr(
        'from zoo.zmaya.animation import switching; switching.switchToIkForAnimatedPart(thisRig)')

    limbTrigger.createMenu('Place pole sensibly', RigMenuCommand).setCmdStr('thisRig.placePole()')
    limbTrigger.createMenu('Place pole sensibly for all keys', RigMenuCommand).setCmdStr(
        'from animation import switching; switching.placePoleForAnimatedPart(thisRig)')

    # add all zooObjMenu commands to the fk controls
    for fk in data.fkControls:
        fkTrigger = triggered.Trigger.Create(fk)
        fkTrigger.createMenu('Switch to IK', RigMenuCommand).setCmdStr('thisRig.switchToIk()')
        fkTrigger.createMenu('Switch to IK for all keys', RigMenuCommand).setCmdStr(
            'from zoo.zmaya.animation import switching; switching.switchToIkForAnimatedPart(thisRig)')
        fkTrigger.createMenu('Fix ' + nameScheme[1], RigMenuCommand).setCmdStr('thisRig.fixMidFk()')
        fkTrigger.createMenu('Select FK controls', RigMenuCommand).setCmdStr('cmds.select(thisRig.getFkControls())')

    # add trigger commands
    trigger = triggered.Trigger.Create(
        data.lineNode, connects=[data.poleControl], cmdCls=triggered.SelectConnectsCommand)
    cmds.setAttr('%s.displayHandle' % data.lineNode, True)

    # turn unwanted transforms off, so that they are locked, and no longer keyable
    control.attrState(data.poleControl, 'r', *control.LOCK_HIDE)

    return data

#end
