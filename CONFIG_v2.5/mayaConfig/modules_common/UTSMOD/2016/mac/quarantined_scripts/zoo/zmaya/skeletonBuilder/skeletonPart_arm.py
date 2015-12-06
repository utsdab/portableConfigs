
from maya import cmds

from ... import str_utils
from . import baseSkeletonPart
from . import constants
from . import rig_utils
from . import twistJoints

class Arm(baseSkeletonPart.SkeletonPart):
    HAS_PARITY = True

    @classmethod
    def _build(cls, parent=None, buildClavicle=True, twistJointCount=5, **kw):
        idx = str_utils.Parity(kw['idx'])
        partScale = kw['partScale']

        parent = baseSkeletonPart.getParent(parent)

        allJoints = []
        dirMult = idx.asMultiplier()
        parityName = idx.asName()
        parityName = parityName[-1]

        if buildClavicle:
            clavicle = baseSkeletonPart.createJoint('%s_clavicle' % parityName)
            cmds.parent(clavicle, parent, relative=True)
            cmds.move(dirMult * partScale / 50.0, partScale / 10.0, partScale / 25.0, clavicle, r=True, ws=True)
            parent = clavicle
            allJoints.append(clavicle)

        bicep = baseSkeletonPart.createJoint('%s_bicep' % parityName)
        cmds.parent(bicep, parent, relative=True)
        cmds.move(dirMult * partScale / 10.0, 0, 0, bicep, r=True, ws=True)

        elbow = baseSkeletonPart.createJoint('%s_elbow' % parityName)
        cmds.parent(elbow, bicep, relative=True)
        cmds.move(dirMult * partScale / 5.0, 0, -partScale / 20.0, elbow, r=True, ws=True)

        wrist = baseSkeletonPart.createJoint('%s_wrist' % parityName)
        cmds.parent(wrist, elbow, relative=True)
        cmds.move(dirMult * partScale / 5.0, 0, partScale / 20.0, wrist, r=True, ws=True)

        cmds.rotate(0, 0, -45 * dirMult, bicep, ws=True, r=True)

        baseSkeletonPart.jointSize(bicep, 3)
        baseSkeletonPart.jointSize(wrist, 3)

        allJoints += [bicep, elbow, wrist]
        if twistJointCount > 0:
            allJoints += twistJoints.buildTwistJoints(
                bicep, elbow, count=twistJointCount, prefix=bicep)
            allJoints += twistJoints.buildTwistJoints(
                elbow, wrist, count=twistJointCount, prefix=elbow)

        return allJoints

    def _buildPlacers(self):
        return []

    def visualize(self):
        scale = self.getBuildScale() / 10.0

        plane = cmds.polyCreateFacet(
            ch=False, tx=True, s=1,
            p=(
                constants.BONE_OTHER_VECTOR * -scale,
                constants.BONE_OTHER_VECTOR * scale,
                constants.BONE_AIM_VECTOR * self.getParityMultiplier() * 2 * scale))

        cmds.parent(plane, self.wrist, relative=True)

        cmds.parent(cmds.listRelatives(plane, shapes=True, pa=True), self.wrist, add=True, shape=True)
        cmds.delete(plane)

    @property
    def hasClavicle(self):
        return self.getBuildKwargs()['buildClavicle']

    @property
    def clavicle(self):
        if self.hasClavicle:
            return self[0]

    @property
    def bicep(self):
        if self.hasClavicle:
            return self[1]
        return self[0]

    @property
    def elbow(self):
        if self.hasClavicle:
            return self[2]
        return self[1]

    @property
    def wrist(self):
        if self.hasClavicle:
            return self[3]
        return self[2]

    @property
    def twistCount(self):
        return self.getBuildKwargs()['twistJointCount']

    @property
    def bicepTwists(self):
        return self[-self.twistCount * 2:-self.twistCount] if self.twistCount > 0 else []

    @property
    def wristTwists(self):
        return self[-self.twistCount:] if self.twistCount > 0 else []

    def _align(self, _initialAlign=False):
        parity = self.getParity()

        normal = rig_utils.getPlaneNormalForObjects(self.bicep, self.elbow, self.wrist)
        normal *= parity.asMultiplier()

        if self.clavicle:
            parent = baseSkeletonPart.getNodeParent(self.clavicle)
            if parent:
                baseSkeletonPart.alignAimAtItem(
                    self.clavicle, self.bicep, parity, upType='objectrotation',
                    worldUpObject=parent, worldUpVector=rig_utils.MAYA_FWD * self.getParityMultiplier())

        baseSkeletonPart.alignAimAtItem(self.bicep, self.elbow, parity, worldUpVector=normal)
        baseSkeletonPart.alignAimAtItem(self.elbow, self.wrist, parity, worldUpVector=normal)

        if _initialAlign:
            baseSkeletonPart.autoAlignItem(self.wrist, parity, worldUpVector=normal)
        else:
            baseSkeletonPart.alignPreserve(self.wrist)

        for i in self.getOrphanJoints():
            baseSkeletonPart.alignItemToLocal(i)

        # Place the twist joints
        if self.bicepTwists:
            twistJoints.placeTwistJoints(self.elbow, self.bicepTwists)

        if self.wristTwists:
            twistJoints.placeTwistJoints(self.wrist, self.wristTwists)

        # Align the twist joints
        for j in self.bicepTwists + self.wristTwists:
            baseSkeletonPart.alignItemToLocal(j)

    def getIkFkItems(self):
        return self.bicep, self.elbow, self.wrist

# end
