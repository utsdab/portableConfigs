
from baseRigPart import *

class Head(PrimaryRigPart):
    __version__ = 0
    SKELETON_PRIM_ASSOC = (baseSkeletonPart.SkeletonPart.GetNamedSubclass('Head'),)
    CONTROL_NAMES = 'control', 'gimbal', 'neck'

    def _build(self, skeletonPart, translateControls=False, **kw):
        return self.doBuild(skeletonPart.head, translateControls=translateControls, **kw)

    def doBuild(self, head, neckCount=1, translateControls=False, **kw):
        scale = self.scale
        partParent, rootControl = getParentAndRootControl(head)

        colour = control.ColourDesc('blue')
        lightBlue = control.ColourDesc('lightblue')


        #build the head controls - we always need them
        headControl = control.buildControl('headControl', head, shapeDesc='sphere', colour=colour, scale=scale)

        headControlSpace = baseSkeletonPart.getNodeParent(headControl)
        headGimbal = control.buildControl('head_gimbalControl', head, shapeDesc='starCircle', colour=colour, oriented=False, scale=scale, parent=headControl, niceName='Head')


        #now find the neck joints
        neckJoints = []
        curParent = head
        for n in range(neckCount):
            curParent = baseSkeletonPart.getNodeParent(curParent)
            neckJoints.append(curParent)

        neckJoints.reverse()


        #build the controls for them
        neckControls = []
        theParent = partParent
        for n, j in enumerate(neckJoints):
            ax = rig_utils.getObjectAxisInDirection(j, -rig_utils.MAYA_FWD)
            c = control.buildControl('neck_%d_Control' % n, j, control.PivotModeDesc.BASE, control.ShapeDesc('pin', ax), colour=lightBlue, scale=scale*1.5, parent=theParent, niceName='Neck %d' % n)
            if not translateControls:
                control.attrState(c, 't', *control.LOCK_HIDE)

            theParent = c
            neckControls.append(c)

        if neckCount == 1:
            neckControls[ 0 ] = rename(neckControls[ 0 ], 'neckControl')
            control.setNiceName(neckControls[ 0 ], 'Neck')
        elif neckCount >= 2:
            control.setNiceName(neckControls[ 0 ], 'Neck Base')
            control.setNiceName(neckControls[ -1 ], 'Neck End')

        if neckCount:
            parent(headControlSpace, neckControls[ -1 ])
        else:
            parent(headControlSpace, partParent)

        #grab the world part/control
        worldPart = WorldPart.Create()
        worldControl = worldPart.getControl('control')

        #build space switching
        if neckControls:
            spaceSwitching.build(headControl,
                                 (neckControls[ 0 ], partParent, rootControl, worldControl),
                                 space=headControlSpace, **spaceSwitching.NO_TRANSLATION)

        for c in neckControls:
            spaceSwitching.build(c,
                                 (partParent, rootControl, worldControl),
                                 **spaceSwitching.NO_TRANSLATION)


        #add right click menu to turn on the gimbal control
        """gimbalIdx = Trigger(headControl).connect(headGimbal)
		Trigger.CreateMenu(headControl,
			                "toggle gimbal control",
			                "string $shapes[] = `listRelatives -f -s %%%d`;\nint $vis = `getAttr ($shapes[0] +\".v\")`;\nfor($s in $shapes) setAttr ($s +\".v\") (!$vis);" % gimbalIdx)"""


        #turn unwanted transforms off, so that they are locked, and no longer keyable, and set rotation orders
        gimbalShapes = listRelatives(headGimbal, s=True)
        for s in gimbalShapes:
            setAttr('%s.v' % s, 0)

        setAttr('%s.ro' % headControl, 3)
        setAttr('%s.ro' % headGimbal, 3)

        if not translateControls:
            control.attrState((headControl, headGimbal), 't', *control.LOCK_HIDE)

        controls = [ headControl, headGimbal ] + neckControls

        return controls, ()

    def getControlToJointMapping(self):
        controls = list(self)

        mapping = str_utils.Mapping()
        for control, joint in zip(list(self)[2:], list(self._skeletonPart)):
            mapping.append(control, joint)

        mapping.append(self.getControl('control'), self._skeletonPart.head)

        return mapping

#end