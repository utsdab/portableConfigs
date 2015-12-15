
from maya import cmds

from ... import str_utils
from ... import vectors

from .. import triggered
from .. import poseSym

from . import control
from . import constants
from . import baseRigPart
from . import baseSkeletonPart
from . import rig_utils

class Root(baseRigPart.PrimaryRigPart):
    __version__ = 1

    SKELETON_PRIM_ASSOC = (baseSkeletonPart.Root,)
    CONTROL_NAMES = 'control', 'gimbal', 'hips'

    def _build(self, skeletonPart, **kw):
        scale = kw['scale']
        root = skeletonPart.root

        # deal with colours
        colour = control.ColourDesc('blue')
        darkColour = colour.darken(0.5)
        lightColour = colour.lighten(0.5)

        # hook up the scale from the main control
        cmds.connectAttr('%s.scale' % self.getWorldControl(), '%s.scale' % root)
        partParent, altRootControl = baseRigPart.getParentAndRootControl(root)

        # try to determine a sensible size for the root control - basically grab
        # the autosize of the root joint, and take the x-z plane values
        size = vectors.Vector((scale, scale, scale))

        # create the controls, and parent them
        rootControl = control.buildControl(
            'rootControl',
            root,
            shapeDesc=control.ShapeDesc('stump', axis=constants.BONE_AIM_AXIS),
            colour=colour, constrain=False, scale=scale * 2, parent=partParent)
        rootGimbal = control.buildControl(
            'gimbalControl',
            root,
            shapeDesc=control.ShapeDesc('hex', axis=control.AX_Y),
            colour=darkColour, oriented=False,
            scale=scale * 1.7, parent=rootControl, niceName='Upper Body Control')
        hipsControl = control.buildControl(
            'hipsControl',
            skeletonPart.hips,
            shapeDesc=control.ShapeDesc('hex', axis=control.AX_Y),
            colour=lightColour, constrain=False, oriented=False,
            scale=scale * 1.5, parent=rootGimbal)

        # delete the connections to rotation so we can put an orient
        # constraint on the root joint to the hips control
        for ax in rig_utils.AXES:
            cmds.delete('%s.r%s' % (root, ax), icn=True)

        cmds.orientConstraint(hipsControl, root, mo=True)

        control.attrState(hipsControl, 't', *control.LOCK_HIDE)

        # turn unwanted transforms off, so that they are locked, and
        # no longer keyable
        control.attrState((rootGimbal, hipsControl), 't', *control.LOCK_HIDE)

        for s in cmds.listRelatives(rootGimbal, s=True, pa=True):
            cmds.setAttr('%s.visibility' % s, False)

        cmds.xform(rootControl, p=1, roo='xzy')
        cmds.xform(rootGimbal, p=1, roo='zxy')

        # add right click menu to turn on the gimbal control
        triggered.Trigger(rootControl).createMenu(
            'toggle gimbal control', baseRigPart.RigMenuCommand).setCmdStr('thisRig.toggleGimbalVisibility()')
        triggered.Trigger(rootGimbal).createMenu(
            'toggle gimbal control', baseRigPart.RigMenuCommand).setCmdStr('thisRig.toggleGimbalVisibility()')

        controls = rootControl, rootGimbal, hipsControl

        return controls, ()

    def setupMirroring(self):
        for c in self.getControls():
            pair = poseSym.ControlPair.Create(c)
            pair.setFlips(0)

    def toggleGimbalVisibility(self):
        gimbal = self.getControl('gimbal')
        gimbalShapes = cmds.listRelatives(gimbal, pa=True, s=True)
        if gimbalShapes:
            vis = not cmds.getAttr('%s.v' % gimbalShapes[0])
            for s in gimbalShapes:
                cmds.setAttr('%s.v' % s, vis)

            if vis:
                cmds.select(gimbal)

    def getControlToJointMapping(self):
        mapping = str_utils.Mapping()

        mapping.append(self.getControl('control'), self._skeletonPart.hips)

        return mapping

#end
