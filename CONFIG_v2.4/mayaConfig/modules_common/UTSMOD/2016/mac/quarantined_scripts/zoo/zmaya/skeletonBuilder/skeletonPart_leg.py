
from maya import cmds

from ... import str_utils
from . import baseSkeletonPart
from . import constants
from . import rig_utils
from . import twistJoints

class Leg(baseSkeletonPart.SkeletonPart):
    HAS_PARITY = True

    PLACER_NAMES = 'footTip', 'footInner', 'footOuter', 'heel'

    @property
    def thigh(self):
        return self[0]

    @property
    def knee(self):
        return self[1]

    @property
    def ankle(self):
        return self[2]

    @property
    def toe(self):
        return self[3] if len(self) > 3 else None

    @property
    def twistCount(self):
        return self.getBuildKwargs()['twistJointCount']

    @property
    def thighTwists(self):
        return self[-self.twistCount * 2:-self.twistCount]

    @property
    def ankleTwists(self):
        return self[-self.twistCount:]

    @classmethod
    def _build(cls, parent=None, buildToe=True, toeCount=0, twistJointCount=5, **kw):
        idx = str_utils.Parity(kw['idx'])
        partScale = kw['partScale']

        parent = baseSkeletonPart.getParent(parent)

        root = baseSkeletonPart.getRoot()
        height = cmds.xform(root, q=True, ws=True, rp=True)[1]

        dirMult = idx.asMultiplier()
        parityName = idx.asName()
        parityName = parityName[-1]

        sidePos = dirMult * partScale / 10.0
        upPos = partScale / 20.0
        fwdPos = -(idx / 2) * partScale / 5.0

        footHeight = height / 15.0 if buildToe else 0
        kneeFwdMove = partScale / 20.0

        thigh = baseSkeletonPart.createJoint('%s_leg01' % parityName)
        cmds.parent(thigh, parent, relative=True)
        cmds.move(sidePos, -upPos, fwdPos, thigh, r=True, ws=True)

        knee = baseSkeletonPart.createJoint('%s_leg02' % parityName)
        cmds.parent(knee, thigh, relative=True)
        cmds.move(0, -(height - footHeight) / 2.0, kneeFwdMove, knee, r=True, ws=True)

        ankle = baseSkeletonPart.createJoint('%s_leg03' % parityName)
        cmds.parent(ankle, knee, relative=True)
        cmds.move(0, -(height - footHeight) / 2.0, -kneeFwdMove, ankle, r=True, ws=True)

        baseSkeletonPart.jointSize(thigh, 2)
        baseSkeletonPart.jointSize(ankle, 2)

        allJoints = []
        if buildToe:
            toe = baseSkeletonPart.createJoint('%s_toeBase' % parityName)
            cmds.parent(toe, ankle, relative=True)
            cmds.move(0, -footHeight, footHeight * 3, toe, r=True, ws=True)
            allJoints.append(toe)

            baseSkeletonPart.jointSize(toe, 1.5)

            for n in range(toeCount):
                toeN = baseSkeletonPart.createJoint('toe_%d_%s' % (n, parityName))
                allJoints.append(toeN)
                cmds.parent(toeN, toe, relative=True)

        # Build twist joints if appropriate
        if twistJointCount > 0:
            allJoints += twistJoints.buildTwistJoints(
                thigh, knee, count=twistJointCount, prefix=thigh)
            allJoints += twistJoints.buildTwistJoints(
                knee, ankle, count=twistJointCount, prefix=knee)

        cmds.rotate(0, dirMult * 15, 0, thigh, r=True, ws=True)

        return [thigh, knee, ankle] + allJoints

    def _buildPlacers(self):
        placers = []

        scale = baseSkeletonPart.getItemScale(self.ankle)

        p = baseSkeletonPart.buildEndPlacer()
        p = cmds.parent(p, self.toe, r=True)[0]
        cmds.move(0, 0, scale / 5., p, r=True)
        cmds.move(0, 0, 0, p, moveY=True, a=True, ws=True)
        placers.append(p)

        p = baseSkeletonPart.buildEndPlacer()
        p = cmds.parent(p, self.ankle, r=True)[0]
        cmds.setAttr('%s.ty' % p, -scale / 10.)
        cmds.move(0, 0, 0, p, moveY=True, a=True, ws=True)
        placers.append(p)

        p = baseSkeletonPart.buildEndPlacer()
        p = cmds.parent(p, self.ankle, r=True)[0]
        cmds.setAttr('%s.ty' % p, scale / 15.)
        cmds.move(0, 0, 0, p, moveY=True, a=True, ws=True)
        placers.append(p)

        p = baseSkeletonPart.buildEndPlacer()
        p = cmds.parent(p, self.ankle, r=True)[0]
        cmds.move(0, 0, -scale / 5., p, r=True)
        cmds.move(0, 0, 0, p, moveY=True, a=True, ws=True)
        placers.append(p)

        return placers

    def _align(self, _initialAlign=False):
        normal = rig_utils.getPlaneNormalForObjects(self.thigh, self.knee, self.ankle)
        normal *= self.getParityMultiplier()

        parity = self.getParity()

        baseSkeletonPart.alignAimAtItem(self.thigh, self.knee, parity, worldUpVector=normal)
        baseSkeletonPart.alignAimAtItem(self.knee, self.ankle, parity, worldUpVector=normal)

        if self.toe:
            baseSkeletonPart.alignAimAtItem(self.ankle, self.toe, parity, upVector=constants.BONE_OTHER_VECTOR, upType='scene')
        else:
            baseSkeletonPart.autoAlignItem(self.ankle, parity, upVector=rig_utils.MAYA_FWD, upType='scene')

        for i in self.getOrphanJoints():
            baseSkeletonPart.alignItemToLocal(i)

        # Place the twist joints
        if self.thighTwists:
            twistJoints.placeTwistJoints(self.knee, self.thighTwists)

        if self.ankleTwists:
            twistJoints.placeTwistJoints(self.ankle, self.ankleTwists)

        # Align the twist joints
        for j in self.thighTwists + self.ankleTwists:
            baseSkeletonPart.alignItemToLocal(j)

    def visualize(self):
        scale = self.getBuildScale() / 10.0

        plane = cmds.polyCreateFacet(
            ch=False, tx=True, s=1,
            p=(
                constants.BONE_ROTATE_VECTOR * -scale,
                constants.BONE_ROTATE_VECTOR * scale,
                constants.BONE_AIM_VECTOR * self.getParityMultiplier() * 2 * scale))

        cmds.parent(plane, self.toe, relative=True)

        cmds.parent(cmds.listRelatives(plane, shapes=True, pa=True), self.toe, add=True, shape=True)
        cmds.delete(plane)

    def getIkFkItems(self):
        return self.thigh, self.knee, self.ankle

# end
