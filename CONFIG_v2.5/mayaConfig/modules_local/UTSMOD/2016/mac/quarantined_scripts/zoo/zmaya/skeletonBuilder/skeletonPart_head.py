from maya import cmds

from . import baseSkeletonPart
from . import constants

class Head(baseSkeletonPart.SkeletonPart):
    HAS_PARITY = False

    @property
    def head(self):
        return self[-1]

    @classmethod
    def _build(cls, parent=None, neckCount=1, **kw):
        partScale = kw.get('partScale', cls.PART_SCALE)

        parent = baseSkeletonPart.getParent(parent)

        posInc = partScale / 15.0

        head = baseSkeletonPart.createJoint('head')
        if not neckCount:
            cmds.parent(head, parent, relative=True)
            return [head]

        allJoints = []
        prevJoint = parent

        for n in range(neckCount):
            j = baseSkeletonPart.createJoint('neck%d' % (n + 1))
            cmds.parent(j, prevJoint, relative=True)
            cmds.move(0, posInc, posInc, j, r=True, ws=True)
            allJoints.append(j)
            prevJoint = j

        # move the first neck joint up a bunch
        cmds.move(0, partScale / 10.0, 0, allJoints[0], r=True, ws=True)

        # parent the head appropriately
        cmds.parent(head, allJoints[-1], relative=True)
        cmds.move(0, posInc, posInc, head, r=True, ws=True)
        allJoints.append(head)

        baseSkeletonPart.jointSize(head, 2)

        return allJoints

    def _align(self, _initialAlign=False):

        # aim all neck joints at the next neck joint
        for n, item in enumerate(self[:-1]):
            baseSkeletonPart.alignAimAtItem(item, self[n + 1])

        if _initialAlign:
            baseSkeletonPart.alignItemToAxes(self.head)
        else:
            baseSkeletonPart.alignPreserve(self.head)

    def visualize(self):
        scale = self.getBuildScale() / 10.0

        pt1 = tuple(constants.BONE_ROTATE_VECTOR * scale)
        pt2 = tuple(constants.BONE_ROTATE_VECTOR * -scale)
        pt3 = tuple(constants.BONE_AIM_VECTOR * 2 * scale)

        plane = cmds.polyCreateFacet(ch=False, tx=True, s=1, p=(pt1, pt2, pt3))
        cmds.parent(plane, self.head, relative=True)

        cmds.parent(cmds.listRelatives(plane, shapes=True, pa=True), self.head, add=True, shape=True)
        cmds.delete(plane)

#end
