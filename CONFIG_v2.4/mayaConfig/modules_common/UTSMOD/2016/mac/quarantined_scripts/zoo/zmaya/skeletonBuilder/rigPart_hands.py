
from maya import cmds

from baseRigPart import *
from . import constants

HandSkeletonCls = baseSkeletonPart.SkeletonPart.GetNamedSubclass('Hand')
FINGER_IDX_NAMES = HandSkeletonCls.FINGER_IDX_NAMES or ()

class Hand(PrimaryRigPart):
    __version__ = 0
    SKELETON_PRIM_ASSOC = (HandSkeletonCls,)
    CONTROL_NAMES = 'control', 'poses'
    NAMED_NODE_NAMES = ('qss',)

    ADD_CONTROLS_TO_QSS = False

    def _build(self, skeletonPart, taper=0.8, **kw):
        return self.doBuild(skeletonPart.bases, taper=taper, **kw)

    def doBuild(self, bases, wrist=None, num=0, names=FINGER_IDX_NAMES, taper=0.8, **kw):
        if wrist is None:
            wrist = baseSkeletonPart.getNodeParent(bases[0])

        scale = kw['scale']

        idx = kw['idx']
        parity = str_utils.Parity(idx)
        colour = control.ColourDesc('orange')

        suffix = parity.asName()

        # no parity flip on controls
        parityMult = 1.0

        partParent, rootControl = getParentAndRootControl(bases[0])

        minSlider = -90
        maxSlider = 90

        # rotation at minimum slider value
        minFingerRot = -45

        # rotation at maxiumum slider value
        maxFingerRot = 90

        #get the bounds of the geo skinned to the hand and use it to determine default placement of the slider control
        bounds = rig_utils.getJointBounds([wrist] + bases)
        backwardAxis = rig_utils.getObjectAxisInDirection(wrist, -rig_utils.MAYA_FWD)
        dist = bounds[not backwardAxis.isNegative()][backwardAxis % 3]

        #build the main hand group, and the slider control for the fingers
        handSliders = control.buildControl(
            "hand_sliders" + suffix, wrist,
            shapeDesc=control.ShapeDesc('pointer', backwardAxis),
            constrain=False, colour=colour, offset=(0, 0, dist * 1.25), scale=scale * 1.25)

        poseCurve = control.buildControl(
            "hand_poses" + suffix, handSliders,
            shapeDesc=control.ShapeDesc('starCircle', control.AX_Y),
            oriented=False, constrain=False, colour=colour, parent=handSliders, scale=scale)

        handQss = cmds.sets(empty=True, text="gCharacterSet", n="hand_ctrls" + suffix)
        cmds.sets(handQss, add=self.getQssSet())
        handGrp = baseSkeletonPart.getNodeParent(handSliders)

        poseCurveTrigger = triggered.Trigger(poseCurve)
        cmds.setAttr('%s.v' % poseCurve, False)

        #constrain the group to the wrist
        cmds.parentConstraint(wrist, handGrp)
        cmds.parent(handGrp, partParent)

        control.attrState((handSliders, poseCurve), ('t', 'r'), *control.LOCK_HIDE)

        # build the attribute so posesToSliders knows where to write the pose sliders to when poses are rebuilt
        cmds.addAttr(poseCurve, ln='controlObject', at='message')
        cmds.connectAttr('%s.message' % handSliders, '%s.controlObject' % poseCurve)

        #now start building the controls
        allCtrls = [handSliders, poseCurve]
        slider_curl = []
        slider_bend = []

        for n, base in enumerate(bases):
            #discover the list of joints under the current base
            name = names[n]

            if not num:
                num = 100

            joints = [base]
            for i in range(num):
                children = cmds.listRelatives(joints[-1], type='joint')
                if not children:
                    break

                joints.append(children[0])

            num = len(joints)

            #build the controls
            ctrls = []
            for i, j in enumerate(joints):
                ctrlScale = (scale / 3.5) * (taper ** i)

                c = control.buildControl(
                    "%sControl_%d%s" % (name, i, suffix), j,
                    shapeDesc=control.ShapeDesc('ring', constants.BONE_AIM_AXIS),
                    parent=handGrp, scale=ctrlScale, qss=handQss)

                cParent = baseSkeletonPart.getNodeParent(c)
                if i:
                    cmds.parent(cParent, ctrls[-1])

                ctrls.append(c)
                poseCurveTrigger.connect(baseSkeletonPart.getNodeParent(c))

            allCtrls += ctrls

            ###------
            ###CURL SLIDERS
            ###------
            driverAttr = name + "Curl"

            cmds.addAttr(handSliders, ln=driverAttr, k=True, at='double', min=minSlider, max=maxSlider, dv=0)
            driverAttr = '%s.%s' % (handSliders, driverAttr)
            cmds.setAttr(driverAttr, keyable=True)
            spaces = [baseSkeletonPart.getNodeParent(c) for c in ctrls]
            for s in spaces:
                setDrivenKeyframe('%s.r' % s, cd=driverAttr)

            cmds.setAttr(driverAttr, maxSlider)
            for s in spaces:
                cmds.rotate(0, maxFingerRot * parityMult, 0, s, r=True, os=True)
                setDrivenKeyframe('%s.r' % s, cd=driverAttr)

            cmds.setAttr(driverAttr, minSlider)
            for s in spaces:
                cmds.rotate(0, minFingerRot * parityMult, 0, s, r=True, os=True)
                setDrivenKeyframe('%s.r' % s, cd=driverAttr)

            cmds.setAttr(driverAttr, 0)
            slider_curl.append(driverAttr)

            ###------
            ###BEND SLIDERS
            ###------
            driverAttr = name + "Bend"

            cmds.addAttr(handSliders, ln=driverAttr, k=True, at='double', min=minSlider, max=maxSlider, dv=0)
            driverAttr = '%s.%s' % (handSliders, driverAttr)
            cmds.setAttr(driverAttr, keyable=True)

            baseCtrlSpace = spaces[0]
            setDrivenKeyframe('%s.r' % baseCtrlSpace, cd=driverAttr)

            cmds.setAttr(driverAttr, maxSlider)
            cmds.rotate(0, maxFingerRot * parityMult, 0, baseCtrlSpace, r=True, os=True)
            setDrivenKeyframe('%s.r' % baseCtrlSpace, cd=driverAttr)

            cmds.setAttr(driverAttr, minSlider)
            cmds.rotate(0, minFingerRot * parityMult, 0, baseCtrlSpace, r=True, os=True)
            setDrivenKeyframe('%s.r' % baseCtrlSpace, cd=driverAttr)

            cmds.setAttr(driverAttr, 0)
            slider_bend.append(driverAttr)

        #add toggle finger control vis
        handSlidersTrigger = triggered.Trigger(handSliders)
        tglCmd = handSlidersTrigger.createMenu('Toggle finger controls', RigMenuCommand)
        tglCmd.setCmdStr('thisRig.toggleControlVisibility()')

        return allCtrls, [handQss]

    def setupMirroring(self):
        for c in self:
            oppositeControl = self.getOppositeControl(c)
            pair = poseSym.ControlPair.Create(c, oppositeControl)

            # never mirror translation for fingers
            cmds.setAttr('%s.neverDoT' % pair.node, True)

    def toggleControlVisibility(self):
        fingerControls = list(self)[2:]
        shapes = cmds.listRelatives(fingerControls[0], s=True, pa=True)
        vis = not cmds.getAttr('%s.v' % shapes[0])

        for c in fingerControls:
            for shape in cmds.listRelatives(c, s=True, pa=True) or []:
                cmds.setAttr('%s.v' % shape, vis)

    def getControlToJointMapping(self):
        mapping = str_utils.Mapping()

        for c, joint in zip(list(self)[2:], list(self._skeletonPart)):
            mapping.append(c, joint)

        return mapping

#end
