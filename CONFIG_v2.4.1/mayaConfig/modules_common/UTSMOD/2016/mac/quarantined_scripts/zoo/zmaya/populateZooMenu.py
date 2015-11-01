from maya import cmds

def populateMenu(parent):

    cmds.setParent(parent, m=True)
    cmds.menuItem(l='General', sm=True)
    cmds.menuItem(
        l='Triggered Tool',
        c='from zoo.zmaya import ui_triggered; ui_triggered.Triggered.Show()')
    cmds.menuItem(
        l='Hotkey Sets',
        c='from zoo.zmaya import ui_hotkey_sets; ui_hotkey_sets.HotkeySets.Show()')
    cmds.menuItem(
        l='Vis Set Manager',
        c='from maya import mel;mel.eval("zooVisMan")')
    cmds.menuItem(
        l='Reference Rebaser',
        c='from zoo.zmaya import ui_reference_rebaser; ui_reference_rebaser.ReferenceRebaser.Show()')

    cmds.setParent(parent, m=True)
    cmds.menuItem(l='Rigging', sm=True)
    cmds.menuItem(
        l='Skin Weights Tool',
        c='from zoo.zmaya import skinWeightsUI; skinWeightsUI.SkinWeightsWindow()')
    cmds.menuItem(
        l='Volume Skinning Tool',
        c='from zoo.zmaya.skeletonBuilder import ui_volumes; ui_volumes.VolumesTool.Show()')
    cmds.menuItem(
        l='Skeleton Builder',
        c='from zoo.zmaya import skeletonBuilderUI; skeletonBuilderUI.SkeletonBuilderWindow()')
    cmds.menuItem(
        l='Setup Space Switching',
        c='from zoo.zmaya.skeletonBuilder import ui_spaceSwitching; ui_spaceSwitching.SpaceSwitching.Show()')
    cmds.menuItem(
        l='Push Skinning To Model',
        c='from zoo.zmaya import ref_propagation; ref_propagation.propagateWeightChangesToModel_confirm()')

    cmds.setParent(parent, m=True)
    cmds.menuItem(l='Animation', sm=True)
    cmds.menuItem(
        l='Clip Library',
        c='from zoo.zmaya.animation import ui_clipLibrary; ui_clipLibrary.ClipLibrary.Show()')
    cmds.menuItem(
        l='Anim Transfer Tool',
        c='from zoo.zmaya.animation import ui_xfer; ui_xfer.XferAnimWindow()')
    cmds.menuItem(
        l='Zoo Shots v2.0',
        c='from zoo.zmaya import ui_shots; ui_shots.Shots.Show()')
    cmds.menuItem(
        l='Mirror Tool',
        c='from zoo.zmaya import poseSymUI; poseSymUI.PoseSymWindow()')
    cmds.menuItem(
        l='Switching Tool',
        c='from zoo.zmaya.animation import ui_switching; ui_switching.SwitchingTool.Show()')
    cmds.menuItem(
        l='Simplify Curves',
        c='from zoo.zmaya.animation import decimate; decimate.decimateSelection()',
        ann="Removes redundant keyframes from either the selected keys, or all curves on the selected nodes")
    cmds.menuItem(
        l='Root Motion Transfer Tool',
        c='from zoo.zmaya.animation import traversal; traversal.RootMotion.Show()')
    cmds.menuItem(
        l='Dynamic Chain Tool',
        c='from zoo.zmaya.animation import dynamicChain; dynamicChain.DynamicChainWindow()')
    cmds.menuItem(d=True)
    cmds.menuItem(
        l='Setup Animator Hotkeys',
        c='from zoo.zmaya.animation import hotkey_setup; hotkey_setup.CommonAnimatorHotkeys.Show()')

    cmds.setParent(parent, m=True)
    cmds.menuItem(l='Developer', sm=True)
    cmds.menuItem(l='Reload All Zoo Tools', c='from zoo import flush;flush.flushZoo()')

    cmds.setParent(parent, m=True)
    cmds.menuItem(p=parent, divider=True)
    cmds.menuItem(
        l='Fix Duplicate Node Names',
        c='from zoo.zmaya import apiExtensions; apiExtensions.fixNonUniqueNames()')

    cmds.menuItem(p=parent, divider=True)
    import triggered
    cmds.menuItem(p=parent, l='Triggered', cb=triggered.State(), c=lambda _: triggered.ToggleState())

    # Finally, create a menu item to display the zoo tools version
    from . import install_zoo
    cmds.menuItem(p=parent, divider=True)
    cmds.menuItem(p=parent, l='Uninstall Zoo Tools', c=install_zoo.uninstall)
    cmds.menuItem(p=parent, l='zooTools version: ' + install_zoo.getInstallVersionStr(), en=False)

#end
