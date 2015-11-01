
from maya import cmds

from ... import vectors
from ... import str_utils

from . import baseSkeletonPart
from . import baseRigPart
from . import control
from . import constants
from . import rigPart_ikFkBase
from . import spaceSwitching
from . import rig_utils
from . import twistJoints
from . import stretchJoints

def snapTo(obj, target):
    pos = cmds.xform(target, q=True, ws=True, rp=True)
    cmds.move(pos[0], pos[1], pos[2], obj, a=True, ws=True, rpr=True)

class XformRestoreContext(object):
    def __init__(self, nodes):
        self._nodes = nodes

    def __enter__(self):
        self._preXforms = [
            (cmds.getAttr('%s.t' % n)[0],
             cmds.getAttr('%s.r' % n)[0]) for n in self._nodes]

    def __exit__(self, *_):
        for n, (t, r) in zip(self._nodes, self._preXforms):
            cmds.setAttr('%s.t' % n, *t)
            cmds.setAttr('%s.r' % n, *r)

class IkFkArm(rigPart_ikFkBase.IkFkBase):
    __version__ = 3 + rigPart_ikFkBase.IkFkBase.__version__  # factor in the version of the ikfk sub rig part
    SKELETON_PRIM_ASSOC = (baseSkeletonPart.SkeletonPart.GetNamedSubclass('Arm'),)
    CONTROL_NAMES = 'control', 'fkBicep', 'fkElbow', 'fkWrist', 'poleControl', 'clavicle', 'allPurpose'

    def getFkControls(self):
        return self.getControl('fkBicep'), self.getControl('fkElbow'), self.getControl('fkWrist')

    def getIkHandle(self):
        ikCons = cmds.listConnections('%s.message' % self.getControl('fkBicep'), s=False, type='ikHandle')
        if ikCons:
            return ikCons[0]

    @staticmethod
    def rigSkeletonPartTwists(skeletonPart):
        with XformRestoreContext([skeletonPart.bicep]):
            cmds.rotate(90 * skeletonPart.getParityMultiplier(), 0, 0, skeletonPart.bicep, ws=True)
            if skeletonPart.bicepTwists:
                twistJoints.rigTwistJoints(
                    skeletonPart.elbow, skeletonPart.bicep,
                    skeletonPart.bicep, skeletonPart.clavicle,
                    twists=skeletonPart.bicepTwists,
                    axis=constants.BONE_AIM_AXIS)

        if skeletonPart.wristTwists:
            twistJoints.rigTwistJoints(
                skeletonPart.elbow, skeletonPart.elbow,
                skeletonPart.wrist, skeletonPart.wrist,
                twists=list(reversed(skeletonPart.wristTwists)),
                axis=constants.BONE_AIM_AXIS)

    def _build(self, skeletonPart, translateClavicle=True, stretchy=False, **kw):
        bicep = skeletonPart.bicep
        wrist = skeletonPart.wrist
        clavicle = skeletonPart.clavicle

        rig_utils.getWristToWorldRotation(wrist, True)

        colour = self.getParityColour()
        parentControl, rootControl = baseRigPart.getParentAndRootControl(clavicle or bicep)

        # Build twist rigs first
        skeletonPart = self.getSkeletonPart()
        self.rigSkeletonPartTwists(skeletonPart)

        # build the base controls
        data = rigPart_ikFkBase.buildIkFkBase(self, rigPart_ikFkBase.ARM_NAMING_SCHEME, alignEnd=True)

        #create variables for each control used
        ikArmSpace, fkArmSpace = data.ikSpace, data.fkSpace
        driverBicep, driverElbow, driverWrist = data.driverUpper, data.driverMid, data.driverLower
        elbowControl = data.poleControl

        # Build the clavicle
        if clavicle:
            clavControl = control.buildControl(
                'clavicleControl%s' % self.getParity().asName(),
                control.PlaceDesc(bicep, clavicle, clavicle),
                shapeDesc=control.ShapeDesc('sphere'), scale=self.scale * 1.25,
                colour=colour)
            clavControlOrient = baseSkeletonPart.getNodeParent(clavControl)

            cmds.parent(clavControlOrient, parentControl)
            cmds.parent(fkArmSpace, clavControl)
            if not translateClavicle:
                control.attrState(clavControl, 't', *control.LOCK_HIDE)
        else:
            clavControl = None
            cmds.parent(fkArmSpace, parentControl)

        # Build space switching
        allPurposeObj = self.buildAllPurposeLocator('arm')
        baseRigPart.buildDefaultSpaceSwitching(bicep, elbowControl, **spaceSwitching.NO_ROTATION)
        baseRigPart.buildDefaultSpaceSwitching(bicep, data.control, [allPurposeObj], ['All Purpose'], True)
        baseRigPart.buildDefaultSpaceSwitching(bicep, driverBicep, **spaceSwitching.NO_TRANSLATION)

        # Do we need to build the stretch rig?
        if stretchy:
            if skeletonPart.bicepTwists:
                stretchJoints.rigTwistStretch(
                    driverBicep, driverElbow, skeletonPart.bicepTwists)

            if skeletonPart.wristTwists:
                stretchJoints.rigTwistStretch(
                    driverElbow, driverWrist, skeletonPart.wristTwists)

            stretchJoints.rigLimbStretch(
                data.control, (driverBicep, driverElbow, driverWrist), self.getParity())

        controls = data.control, driverBicep, driverElbow, driverWrist, elbowControl, clavControl, allPurposeObj
        namedNodes = data.ikSpace, data.fkSpace, data.ikHandle, data.endOrient, data.lineNode

        return controls, namedNodes

    def getControlToJointMapping(self):
        mapping = str_utils.Mapping()
        mapping.append(self.getControl('clavicle'), self._skeletonPart.clavicle)
        mapping.append(self.getControl('control'), self._skeletonPart.wrist)
        mapping.append(self.getControl('poleControl'), self._skeletonPart.elbow)

        return mapping

class IkFkLeg(rigPart_ikFkBase.IkFkBase):
    __version__ = 2 + rigPart_ikFkBase.IkFkBase.__version__  # factor in the version of the ikfk sub rig part
    SKELETON_PRIM_ASSOC = (baseSkeletonPart.SkeletonPart.GetNamedSubclass('Leg'),)
    CONTROL_NAMES = 'control', 'fkThigh', 'fkKnee', 'fkAnkle', 'poleControl', 'allPurpose'

    def getFkControls(self):
        return self.getControl('fkThigh'), self.getControl('fkKnee'), self.getControl('fkAnkle')

    def getIkHandle(self):
        ikCons = cmds.listConnections('%s.message' % self.getControl('fkThigh'), s=False, type='ikHandle')
        if ikCons:
            return ikCons[0]

    @staticmethod
    def rigSkeletonPartTwists(skeletonPart):
        if skeletonPart.thighTwists:
            thighParent = cmds.listRelatives(skeletonPart.thigh, p=True, pa=True)
            if thighParent:
                thighParent = thighParent[0]
                twistJoints.rigTwistJoints(
                    skeletonPart.knee, skeletonPart.thigh,
                    skeletonPart.thigh, thighParent,
                    twists=skeletonPart.thighTwists,
                    axis=constants.BONE_AIM_AXIS)

        if skeletonPart.ankleTwists:
            twistJoints.rigTwistJoints(
                skeletonPart.knee, skeletonPart.knee,
                skeletonPart.ankle, skeletonPart.ankle,
                twists=list(reversed(skeletonPart.ankleTwists)),
                axis=constants.BONE_AIM_AXIS)

    def _build(self, skeletonPart, stretchy=False, **kw):
        thigh = skeletonPart.thigh
        ankle = skeletonPart.ankle
        partParent, rootControl = baseRigPart.getParentAndRootControl(thigh)

        # first rotate the foot so its aligned to a world axis
        footCtrlRot = vectors.Vector(rig_utils.getAnkleToWorldRotation(str(ankle), 'z', True))
        footCtrlRot = (0, -footCtrlRot.y, 0)

        # build the base controls
        data = rigPart_ikFkBase.buildIkFkBase(self, rigPart_ikFkBase.LEG_NAMING_SCHEME, alignEnd=False)

        # if the legs are parented to a root part - which is usually the case but not
        # always - grab the hips and parent the fk control space to the hips
        hipsControl = partParent
        partParentRigPart = baseRigPart.RigPart.InitFromItem(partParent)
        if isinstance(partParentRigPart.getSkeletonPart(), baseSkeletonPart.Root):
            hipsControl = partParentRigPart.getControl('hips')

        # if the part parent in a Root primitive, grab the hips control instead of the root
        # gimbal - for the leg parts this is preferable
        parentRigPart = baseRigPart.RigPart.InitFromItem(partParent)
        if isinstance(parentRigPart, baseSkeletonPart.Root):
            partParent = parentRigPart.getControl('hips')

        # create variables for each control used
        legControl = data.control
        legControlSpace = baseSkeletonPart.getNodeParent(legControl)

        ikLegSpace, fkLegSpace = data.ikSpace, data.fkSpace
        driverThigh, driverKnee, driverAnkle = data.driverUpper, data.driverMid, data.driverLower

        kneeControl = data.poleControl
        kneeControlSpace = baseSkeletonPart.getNodeParent(kneeControl)
        cmds.parent(kneeControlSpace, partParent)

        toe = skeletonPart.toe
        toeTip = self.getSkeletonPart().endPlacer
        placers = self.getSkeletonPart().getPlacers()

        # build the objects to control the foot
        suffix = self.getSuffix()
        footControlSpace = control.buildNullControl("foot_controlSpace" + suffix, ankle, parent=legControl)
        heelRoll = control.buildNullControl(
            "heel_roll_piv" + suffix, ankle, offset=(0, 0, -self.scale), parent=footControlSpace)
        snapTo(heelRoll, placers[3])

        toeRoll = control.buildNullControl("leg_toe_roll_piv" + suffix, toeTip, parent=heelRoll)
        snapTo(toeRoll, toeTip)

        # move bank pivots to a good spot on the ground
        footBankL = control.buildNullControl("bank_in_piv" + suffix, toe, parent=toeRoll)
        snapTo(footBankL, placers[1])

        footBankR = control.buildNullControl("bank_out_piv" + suffix, toe, parent=footBankL)
        snapTo(footBankR, placers[2])

        footRollControl = control.buildNullControl("roll_piv" + suffix, toe, parent=footBankR)
        snapTo(footRollControl, toe)

        #move the knee control so its inline with the leg
        cmds.rotate(
            footCtrlRot[0], footCtrlRot[1], footCtrlRot[2], kneeControlSpace,
            p=cmds.xform(thigh, q=True, ws=True, rp=True), a=True, ws=True)

        cmds.makeIdentity(kneeControl, apply=True, t=True)

        # add attributes to the leg control, to control the pivots
        cmds.addAttr(legControl, ln='rollBall', at='double', min=0, max=10, k=True)
        cmds.addAttr(legControl, ln='rollToe', at='double', min=-10, max=10, k=False)
        cmds.addAttr(legControl, ln='twistFoot', at='double', min=-10, max=10, k=False)
        cmds.addAttr(legControl, ln='bank', at='double', min=-10, max=10, k=True)

        # Parent the ik handle to the roll pivot
        cmds.parent(data.ikHandle, footRollControl)

        # replace the legControl as a target to the parent constraint on the endOrient transform
        # so the ikHandle respects the foot slider controls
        footFinalPivot = control.buildNullControl("roll_orient_piv" + suffix, ankle, parent=footRollControl)
        cmds.delete(cmds.parentConstraint(footFinalPivot, data.ikHandle, mo=True))
        cmds.aimConstraint(
            footRollControl, footFinalPivot,
            aimVector=constants.BONE_AIM_VECTOR, upVector=constants.BONE_ROTATE_VECTOR, worldUpType='objectrotation',
            worldUpVector=constants.BONE_ROTATE_VECTOR, worldUpObject=legControl)
        xxx = control.buildNullControl("xxx" + suffix, legControl, parent=footFinalPivot)
        cmds.delete(cmds.parentConstraint(legControl, xxx))
        rig_utils.replaceGivenConstraintTarget(data.endOrientConstraint, legControl, xxx)

        # build the SDK's to control the pivots
        cmds.setDrivenKeyframe('%s.rx' % footRollControl, cd='%s.rollBall' % legControl, dv=0, v=0)
        cmds.setDrivenKeyframe('%s.rx' % footRollControl, cd='%s.rollBall' % legControl, dv=10, v=90)
        cmds.setDrivenKeyframe('%s.rx' % footRollControl, cd='%s.rollBall' % legControl, dv=-10, v=-90)

        cmds.setDrivenKeyframe('%s.rx' % toeRoll, cd='%s.rollToe' % legControl, dv=0, v=0)
        cmds.setDrivenKeyframe('%s.rx' % toeRoll, cd='%s.rollToe' % legControl, dv=10, v=90)
        cmds.setDrivenKeyframe('%s.rx' % toeRoll, cd='%s.rollToe' % legControl, dv=0, v=0)
        cmds.setDrivenKeyframe('%s.rx' % toeRoll, cd='%s.rollToe' % legControl, dv=-10, v=-90)
        cmds.setDrivenKeyframe('%s.ry' % toeRoll, cd='%s.twistFoot' % legControl, dv=-10, v=-90)
        cmds.setDrivenKeyframe('%s.ry' % toeRoll, cd='%s.twistFoot' % legControl, dv=10, v=90)

        min = -90 if self.getParity() == str_utils.Parity.LEFT else 90
        max = 90 if self.getParity() == str_utils.Parity.LEFT else -90
        cmds.setDrivenKeyframe('%s.rz' % footBankL, cd='%s.bank' % legControl, dv=0, v=0)
        cmds.setDrivenKeyframe('%s.rz' % footBankL, cd='%s.bank' % legControl, dv=10, v=max)
        cmds.setDrivenKeyframe('%s.rz' % footBankR, cd='%s.bank' % legControl, dv=0, v=0)
        cmds.setDrivenKeyframe('%s.rz' % footBankR, cd='%s.bank' % legControl, dv=-10, v=min)

        # setup the toe if we have one
        if toe:
            toeSDK = control.buildControl(
                "toeSDK%s" % suffix, toe,
                shapeDesc=control.SHAPE_NULL,
                parent=footBankR,
                scale=self.scale,
                colour=self.getParityColour())

            cmds.addAttr(legControl, ln='toe', at='double', min=-10, max=10, k=True)
            cmds.setDrivenKeyframe(
                '%s.r%s' % (toeSDK, constants.BONE_ROTATE_AXIS.asCleanName()),
                cd='%s.toe' % legControl, dv=-10, v=90)
            cmds.setDrivenKeyframe(
                '%s.r%s' % (toeSDK, constants.BONE_ROTATE_AXIS.asCleanName()),
                cd='%s.toe' % legControl, dv=10, v=-90)

            toeSDKSpace = cmds.listRelatives(toeSDK, p=True, pa=True)[0]
            toeParentConstraint = cmds.parentConstraint(footBankR, toeSDKSpace, mo=True)[0]
            cmds.parentConstraint(data.endOrient, toeSDKSpace, weight=0, mo=True)
            cmds.connectAttr('%s.w0' % data.endOrientConstraint, '%s.w0' % toeParentConstraint)
            cmds.connectAttr('%s.w1' % data.endOrientConstraint, '%s.w1' % toeParentConstraint)

        # Build space switching
        cmds.parent(fkLegSpace, hipsControl)
        worldPart = self.getWorldPart()
        worldControl = worldPart.getControl('control')
        allPurposeObj = self.buildAllPurposeLocator('leg')
        spaceSwitching.build(legControl, (worldControl, hipsControl, rootControl, allPurposeObj),
                             ('World', None, 'Root', 'All Purpose'), space=legControlSpace)
        spaceSwitching.build(kneeControl, (legControl, partParent, rootControl, worldControl),
                             ("Leg", None, "Root", "World"), **spaceSwitching.NO_ROTATION)
        spaceSwitching.build(driverThigh, (hipsControl, rootControl, worldControl), (None, 'Root', 'World'),
                             **spaceSwitching.NO_TRANSLATION)
        spaceSwitching.build(kneeControl, (worldControl, hipsControl, rootControl), ('World', None, 'Root'),
                             **spaceSwitching.NO_ROTATION)

        # Create the twist rigs
        skeletonPart = self.getSkeletonPart()
        self.rigSkeletonPartTwists(skeletonPart)

        # Make the limb stretchy
        if stretchy:
            if skeletonPart.thighTwists:
                stretchJoints.rigTwistStretch(
                    driverThigh, driverKnee, skeletonPart.thighTwists)

            if skeletonPart.ankleTwists:
                stretchJoints.rigTwistStretch(
                    driverKnee, driverAnkle, skeletonPart.ankleTwists)

            stretchJoints.rigLimbStretch(
                legControl, (driverThigh, driverKnee, data.endOrient), self.getParity())

        controls = legControl, driverThigh, driverKnee, driverAnkle, kneeControl, allPurposeObj
        namedNodes = data.ikSpace, data.fkSpace, data.ikHandle, data.endOrient, data.lineNode

        return controls, namedNodes

    def getControlToJointMapping(self):
        mapping = str_utils.Mapping()
        mapping.append(self.getControl('control'), self._skeletonPart.ankle)
        mapping.append(self.getControl('poleControl'), self._skeletonPart.knee)

        return mapping

    def switchToIk(self, key=False, _isBatchMode=False):

        # Set all foot roll sliders to 0 before calling the base implementation
        control = self.getControl('control')
        cmds.setAttr('%s.rollBall' % control, 0)
        cmds.setAttr('%s.rollToe' % control, 0)
        cmds.setAttr('%s.twistFoot' % control, 0)
        cmds.setAttr('%s.bank' % control, 0)

        super(IkFkLeg, self).switchToIk(key, _isBatchMode)

#end
