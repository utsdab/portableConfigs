
from rigPart_curves import *
from spaceSwitching import build, NO_TRANSLATION, NO_ROTATION

class FkSpine(PrimaryRigPart):
    __version__ = 0
    SKELETON_PRIM_ASSOC = (baseSkeletonPart.SkeletonPart.GetNamedSubclass('Spine'),)

    def _build(self, skeletonPart, translateControls=True, **kw):
        partParent, root = getParentAndRootControl(skeletonPart.base)

        # create the controls, and parent them
        controllers = []
        startColour = control.ColourDesc((1, 0.3, 0, 0.65))
        endColour = control.ColourDesc((0.8, 1, 0, 0.65))
        spineColour = startColour
        colourInc = (endColour - startColour) / float(len(skeletonPart))

        jParent = partParent
        for n, j in enumerate(skeletonPart):
            ax = rig_utils.getObjectAxisInDirection(j, -rig_utils.MAYA_FWD)
            c = control.buildControl("spine_%d_fkControl" % n, j, control.PivotModeDesc.BASE,
                                     control.ShapeDesc('pin', axis=ax), colour=spineColour,
                                     scale=self.scale, niceName='Spine %d Control' % n, parent=jParent)

            controllers.append(c)

            # Set parent to this new control
            jParent = c

            # Accumulate colour
            spineColour += colourInc

        control.setNiceName(controllers[0], 'Spine Base')
        control.setNiceName(controllers[-1], 'Spine End')

        def buildSS(c, parents, names):
            return spaceSwitching.build(c, parents, names, **spaceSwitching.NO_TRANSLATION)

        # create the space switching
        world = self.getWorldControl()
        buildSS(controllers[0], [root, world], ['Root', 'World'])
        buildSS(controllers[1], [controllers[0], root, world], ['Spine Base', 'Root', 'World'])
        prevControl = controllers[1]
        for c in controllers[2:]:
            buildSS(c, [prevControl, controllers[0], root, world], ['Spine Parent', 'Spine Base', 'Root', 'World'])
            prevControl = c

        # create line of action commands
        createLineOfActionMenu(skeletonPart.getItems(), controllers)

        # turn unwanted transforms off, so that they are locked, and no longer keyable
        if not translateControls:
            control.attrState(controllers, 't', *control.LOCK_HIDE)

        return controllers, ()

    def getControlToJointMapping(self):
        mapping = str_utils.Mapping()

        for control, joint in zip(list(self), list(self._skeletonPart)):
            mapping.append(control, joint)

        return mapping

class IKFKSpine(PrimaryRigPart):
    __version__ = 0
    PRIORITY = 10  # make this a lower priority than the simple FK spine rig
    SKELETON_PRIM_ASSOC = (baseSkeletonPart.SkeletonPart.GetNamedSubclass('Spine'),)

    @classmethod
    def CanRigThisPart(cls, skeletonPart):
        return len(skeletonPart) >= 3

    def _build(self, skeletonPart, **kw):
        objs = skeletonPart.items

        parentControl, rootControl = getParentAndRootControl(objs[0])

        fittedCurve, linearCurve, proxies, fixedLengthProxies, controls, splineIkHandle, halfIdx = buildControls(objs, parentControl, name='spineControl', **kw)
        buildDefaultSpaceSwitching(objs[0], controls[-1])

        worldPart = self.getWorldPart()
        partsNode = worldPart.getNamedNode('parts')

        parent(proxies, partsNode)
        parent(fittedCurve, linearCurve, partsNode)
        if splineIkHandle:
            parent(splineIkHandle, partsNode)

        if fixedLengthProxies:
            parent(fixedLengthProxies[0], partsNode)

        return controls, ()

# end
