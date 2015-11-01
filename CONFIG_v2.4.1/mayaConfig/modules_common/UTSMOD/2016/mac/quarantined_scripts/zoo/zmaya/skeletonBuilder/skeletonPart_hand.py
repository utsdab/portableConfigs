from maya import cmds

from ... import str_utils

from . import baseSkeletonPart
from . import constants
from . import rig_utils

class Hand(baseSkeletonPart.SkeletonPart):
    HAS_PARITY = True

    AUTO_NAME = False  # this part will handle its own naming...

    # odd indices are left sided, even are right sided
    FINGER_IDX_NAMES = ('Thumb', 'Index', 'Mid', 'Ring', 'Pinky',
                        'Sixth' 'Seventh', 'Eighth', 'Ninth', 'Tenth')

    PLACER_NAMES = FINGER_IDX_NAMES

    def getParity(self):
        """
        the parity of a hand comes from the limb its parented to, not the idx of
        the finger part itself...
        """

        parent = self.getParent()
        try:
            # if the parent has parity use it
            parentPart = baseSkeletonPart.SkeletonPart.InitFromItem(parent)

        except baseSkeletonPart.SkeletonError:
            # otherwise use the instance's index for parity...
            return super(self, Hand).getParity()

        return str_utils.Parity(parentPart.getParity())

    def iterFingerChains(self):
        """
        iterates over each finger chain in the hand - a chain is simply a list of
        joint names ordered hierarchically
        """
        for base in self.bases:
            children = cmds.listRelatives(base, ad=True, path=True, type='joint') or []
            children = [base] + baseSkeletonPart.sortByHierarchy(children)
            yield children

    @classmethod
    def _build(cls, parent=None, fingerCount=5, fingerJointCount=3, **kw):
        idx = str_utils.Parity(kw['idx'])
        partScale = kw.get('partScale', cls.PART_SCALE)

        parent = baseSkeletonPart.getParent(parent)
        parentPart = baseSkeletonPart.SkeletonPart.InitFromItem(parent)

        # try to determine a "parity index" based on the parent part.  Ideally we want to
        # inherit the parity of the parent part instead of from this part's index
        limbIdx = parentPart.getParity() if parentPart.hasParity() else idx

        # for the first two hands this is an empty string - but for each additional hand
        # pair, this is incremented.  ie the second two hands are called Hand1, the next
        # two hands are called Hand2 etc...
        typePairCountStr = str(idx / 2) if idx > 1 else ''

        minPos, maxPos = partScale / 25.0, -partScale / 25.0
        posRange = float(maxPos - minPos)
        allJoints = []

        length = partScale / 3.0 / fingerJointCount
        lengthInc = cls.ParityMultiplier(limbIdx) * (length / fingerJointCount)
        fwdVec = constants.BONE_AIM_VECTOR * lengthInc

        limbName = str_utils.Parity.NAMES[limbIdx]
        for nameIdx in range(fingerCount):
            fingerName = cls.FINGER_IDX_NAMES[nameIdx]
            prevParent = parent
            for n in range(fingerJointCount):
                j = baseSkeletonPart.createJoint('%s%s_%d%s' % (fingerName, typePairCountStr, n, limbName))
                cmds.parent(j, prevParent, r=True)
                cmds.move(fwdVec[0], fwdVec[1], fwdVec[2], j, r=True, os=True)

                if n == 0:
                    sideDist = -maxPos + (posRange * nameIdx / (fingerCount - 1))
                    sideVec = constants.BONE_OTHER_VECTOR * sideDist
                    cmds.move(sideVec[0], sideVec[1], sideVec[2], j, r=True, os=True)
                else:
                    cmds.setAttr('%s.t%s' % (j, constants.BONE_OTHER_AXIS.asName()), lock=True)

                allJoints.append(j)
                prevParent = j

        return allJoints

    def visualize(self):
        scale = self.getActualScale() / 5.0

        for base in self.bases:
            plane = cmds.polyPlane(
                w=scale, h=scale / 2, sx=1, sy=1,
                ax=constants.BONE_OTHER_AXIS.asVector(), cuv=2, ch=False)[0]

            cmds.parent(plane, base, relative=True)

            cmds.setAttr('%s.t%s' % (plane, constants.BONE_AIM_AXIS.asName()), self.getParityMultiplier() * scale / 2)
            cmds.makeIdentity(plane, a=True, t=True)

            cmds.parent(cmds.listRelatives(plane, shapes=True, pa=True), base, add=True, shape=True)
            cmds.delete(plane)

    def _align(self, _initialAlign=False):
        parity = self.getParity()

        parityMult = self.getParityMultiplier()

        for chain in self.iterFingerChains():
            upVector = rig_utils.getObjectBasisVectors(chain[0])[constants.BONE_ROTATE_AXIS]
            upVector = upVector * parityMult
            for n, item in enumerate(chain[:-1]):
                baseSkeletonPart.alignAimAtItem(item, chain[n + 1], parity, worldUpVector=upVector)

            baseSkeletonPart.autoAlignItem(chain[-1], parity, worldUpVector=upVector)

#end
