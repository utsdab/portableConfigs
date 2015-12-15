
import maya.cmds as cmd

from baseMelUI import *
import poseSym

class PoseSymLayout(MelVSingleStretchLayout):
    _THIS_DIR = path.Path(__file__).abs().up()
    ICONS = ICON_SWAP, ICON_MIRROR, ICON_MATCH = ( _THIS_DIR / 'poseSym_swap.png',
                                                   _THIS_DIR / 'poseSym_mirror.png',
                                                   _THIS_DIR / 'poseSym_match.png' )

    def __init__(self, parent):
        self.UI_swap = swap = MelIconButton(
            self, label='swap pose', style='iconAndTextCentered',
            align='left', h=30, c=self.on_swap)
        swap.setImage(self.ICON_SWAP)

        self.UI_mirror = mirror = MelIconButton(
            self, label='mirror pose', style='iconAndTextCentered',
            align='left', h=30, c=self.on_mirror)

        mirror.setImage(self.ICON_MATCH)

        self.UI_mirror = mirror = MelIconButton(
            self, label='mirror animation',
            style='iconAndTextCentered', align='left',
            h=30, c=self.on_swapAnimation)

        mirror.setImage(self.ICON_SWAP)

        spacer = MelSpacer(self)

        hLayout = MelHLayout(self)
        MelLabel(hLayout, l='mirror: ')
        self.UI_mirror_t = MelCheckBox(hLayout, l='translate', v=1)
        self.UI_mirror_r = MelCheckBox(hLayout, l='rotate', v=1)
        self.UI_mirror_other = MelCheckBox(hLayout, l='other', v=1)
        hLayout.layout()

        self.setStretchWidget(spacer)
        self.layout()

    # ## EVENT HANDLERS ###
    def on_swap(self, *_):
        cmdStack = poseSym.CommandStack()
        for pair, obj in poseSym.iterPairAndObj(cmd.ls(sl=True) or []):
            pair.swap(t=self.UI_mirror_t.getValue(), r=self.UI_mirror_r.getValue(),
                      other=self.UI_mirror_other.getValue(), cmdStack=cmdStack)

        cmdStack.execute()

    def on_mirror(self, *_):
        for pair, obj in poseSym.iterPairAndObj(cmd.ls(sl=True) or []):
            pair.mirror(obj == pair.controlA, t=self.UI_mirror_t.getValue(), r=self.UI_mirror_r.getValue(),
                        other=self.UI_mirror_other.getValue())

    def on_match(self, *_):
        for pair, obj in poseSym.iterPairAndObj(cmd.ls(sl=True) or []):
            pair.match(obj == pair.controlA, t=self.UI_mirror_t.getValue(), r=self.UI_mirror_r.getValue(),
                       other=self.UI_mirror_other.getValue())

    def on_swapAnimation(self, *_):
        from animation import mirroring

        mirroring.swapAnimationForControls(cmd.ls(sl=True) or [])

class PoseSymWindow(BaseMelWindow):
    WINDOW_NAME = 'PoseSymTool'
    WINDOW_TITLE = 'Pose Symmetry Tool'

    DEFAULT_SIZE = 250, 150
    DEFAULT_MENU = 'Setup'

    HELP_MENU = 'zooPoseSym', None, 'http://www.macaronikazoo.com/?page_id=824'

    FORCE_DEFAULT_SIZE = True

    def __init__(self):
        self.editor = PoseSymLayout(self)
        self.setupMenu()
        self.show()

    def setupMenu(self):
        menu = self.getMenu('Setup')

        menu.clear()

        MelMenuItem(menu, l='Create Paired Relationship',
                    ann='Will put the two selected objects into a "paired" relationship - they will know how to mirror/exchange poses with one another',
                    c=self.on_setupPair)
        MelMenuItem(menu, l='Create Singular Relationship On Selected',
                    ann='Will setup each selected control with a mirror node so it knows how to mirror poses on itself',
                    c=self.on_setupSingle)
        MelMenuItemDiv(menu)
        MelMenuItem(menu, l='Auto Setup Skeleton Builder',
                    ann='Tries to determine mirroring relationships from skeleton builder', c=self.on_setupSingle)

    # ## EVENT HANDLERS ###
    def on_setupPair(self, *_):
        sel = cmd.ls(sl=True, type='transform')
        if len(sel) == 1:
            pair = poseSym.ControlPair.Create(sel[0])
            cmd.select(pair.node)
        elif len(sel) >= 2:
            pair = poseSym.ControlPair.Create(*sel[:3])
            cmd.select(pair.node)

    def on_setupSingle(self, *_):
        sel = cmd.ls(sl=True, type='transform')
        nodes = []
        for s in sel:
            pair = poseSym.ControlPair.Create(s)
            nodes.append(pair.node)

        cmd.select(nodes)

    def on_setupSkeletonBuilder(self, *_):
        from skeletonBuilder import baseRigPart

        baseRigPart.setupMirroring()

#end
