
from maya import cmds
from maya.cmds import *

from .. import vectors

from .baseMelUI import *
from .maya_decorators import d_showWaitCursor
from . import baseMelUI

from . import skinWeightsUI
from . import mesh_utils
from . import mel_utils

from .skeletonBuilder import baseSkeletonPart
from .skeletonBuilder import baseRigPart
from .skeletonBuilder import rig_utils
from .skeletonBuilder import control
from .skeletonBuilder import volumes

logger = logging.getLogger(__name__)

Axis = vectors.Axis

# stores UI build methods keyed by arg name
UI_FOR_NAMED_RIG_ARGS = {}

ShapeDesc = control.ShapeDesc

def reloadSkeletonBuilder():
    import sys
    import inspect

    skeletonPartIter = baseSkeletonPart.SkeletonPart.IterSubclasses
    rigPartIter = baseRigPart.RigPart.IterSubclasses

    zooPackageDirpath = path.Path(inspect.getfile(path)).up()

    # First, get all skeleton and rig part modules not under the zoo tools
    partModules = set()
    for partIter in (skeletonPartIter, rigPartIter):
        for part in partIter():
            partFilepath = path.Path(inspect.getfile(part)).abs()
            if partFilepath.isUnder(zooPackageDirpath):
                continue

            partModules.add(inspect.getmodule(part))
            logger.debug('Found SkeletonBuilder module outside of zoo: %s at %s' % (part, partFilepath))

    # Now remove the modules from sys.modules
    for module in partModules:
        for k, v in sys.modules.items():
            if v is module:
                sys.modules.pop(k)
                logger.debug('Popped module %s from sys.modules' % k)

    from .. import flush

    flush.flushZoo()

    # NOTE: this needs to be wrapped in eval deferred as this module has just been flushed!
    cmds.evalDeferred('from zoo.zmaya import skeletonBuilderUI; skeletonBuilderUI.SkeletonBuilderUI()')

class ListEditor(BaseMelWindow):
    WINDOW_NAME = 'parentsEditor'
    WINDOW_TITLE = 'Edit Custom Parents'

    DEFAULT_SIZE = 275, 300
    DEFAULT_MENU = None

    FORCE_DEFAULT_SIZE = True

    def __new__(self, theList, changeCB):
        return BaseMelWindow.__new__(self)

    def __init__(self, theList, storage):
        BaseMelWindow.__init__(self)

        f = MelFormLayout(self)
        self.add = MelButton(f, l='add selected item', c=self.on_add)
        self.rem = MelButton(f, l='remove highlighted items', c=self.on_rem)

        self.scroll = MelTextScrollList(f)
        self.scroll.setItems(theList)
        self.storage = storage

        f(e=True,
          af=((self.add, 'top', 0),
              (self.add, 'left', 0),
              (self.rem, 'top', 0),
              (self.rem, 'right', 0),
              (self.scroll, 'left', 0),
              (self.scroll, 'right', 0),
              (self.scroll, 'bottom', 0)),
          ap=((self.add, 'right', 0, 45),
              (self.rem, 'left', 0, 45)),
          ac=((self.scroll, 'top', 0, self.add)))

    # ## EVENT HANDLERS ###
    def on_add(self, *a):
        sel = cmds.ls(sl=True)
        if sel:
            self.scroll.appendItems(sel)

        self.storage.setValue(self.scroll.getItems())
        self.storage.cb()

    def on_rem(self, *a):
        self.scroll.removeSelectedItems()

        self.storage.setValue(self.scroll.getItems())
        self.storage.cb()

class MelListEditorButton(MelButton):
    def __init__(self, parent, *a, **kw):
        MelButton.__init__(self, parent, *a, **kw)
        self.setChangeCB(self.openEditor)
        self.setLabel('define parents')

    def setValue(self, value, executeChangeCB=False):
        self.value = value

    def getValue(self):
        return self.value

    def setChangeCB(self, cb):
        self.cb = cb

    def openEditor(self, *a):
        win = ListEditor(self.value, self)
        win.show()

# hook up list/tuple types to a button - we don't want a text
# scroll list showing up in the part UI, but a button to bring
# up said editor is fine
UI_FOR_PY_TYPES[list] = MelListEditorButton
UI_FOR_PY_TYPES[tuple] = MelListEditorButton

class MelFileBrowser(MelHLayout):
    def __init__(self, parent, *a, **kw):
        self.UI_filepath = MelTextField(self)
        self.UI_browse = MelButton(self, l='browse', c=self.on_browse, w=50)

        self.setWeight(self.UI_browse, 0)
        self.layout()

    def enable(self, state):
        self.UI_filepath.enable(state)
        self.UI_browse.enable(state)

    def setValue(self, value, executeChangeCB=False):
        '''
        the value we recieve should be a fullpath - but we want to store is as a scene relative path
        '''
        value = path.Path(value)

        #make sure it is actually an absolute path...
        if value.isAbs():
            curSceneDir = path.Path(cmds.file(q=True, sn=True)).up()
            value = value - curSceneDir

        self.UI_filepath.setValue(value, executeChangeCB)

    def getValue(self):
        '''
        return as an absolute path
        '''
        return path.Path(cmds.file(q=True, sn=True)).up() / self.UI_filepath.getValue()

    def setChangeCB(self, cb):
        self.UI_filepath.setChangeCB(cb)

    ### EVENT HANDLERS ###
    def on_browse(self, *a):
        curValue = self.getValue()
        ext = curValue.getExtension() or 'txt'

        if curValue.isFile():
            curValue = curValue.up()
        elif not curValue.isDir():
            curValue = path.Path(cmds.file(q=True, sn=True)).up(2)

        if not curValue.exists():
            curValue = path.Path('')

        filepath = cmds.fileDialog(directoryMask=curValue / ("/*.%s" % ext))
        if filepath:
            self.setValue(filepath, True)

baseMelUI.UI_FOR_PY_TYPES[path.Path] = MelFileBrowser

class MelOptionMenu_SkeletonPart(MelOptionMenu):
    PART_CLASS = baseSkeletonPart.SkeletonPart

    def __new__(cls, parent, *a, **kw):
        self = MelOptionMenu.__new__(cls, parent, *a, **kw)
        self.populate()

        return self

    def populate(self):
        self.clear()
        for part in self.PART_CLASS.Iter():
            self.append(part.end)

    def setValue(self, value, executeChangeCB=True):
        if type(value) is type:
            return

        return MelOptionMenu.setValue(self, value, executeChangeCB)

    def getValue(self):
        value = MelOptionMenu.getValue(self)
        return self.PART_CLASS.InitFromItem(value)

class MelOptionMenu_Arm(MelOptionMenu_SkeletonPart):
    PART_CLASS = baseSkeletonPart.SkeletonPart.GetNamedSubclass('Arm')

class MelOptionMenu_Shape(MelOptionMenu):
    def __new__(cls, parent, *a, **kw):
        self = MelOptionMenu.__new__(cls, parent, *a, **kw)
        self.populate()

        return self

    def populate(self):
        self.clear()
        for shapeName in sorted(control.CONTROL_SHAPE_DICT.keys()):
            self.append(shapeName)

    def setValue(self, value, executeChangeCB=True):
        if type(value) is type:
            return

        if isinstance(value, ShapeDesc):
            value = value.curveType

        return MelOptionMenu.setValue(self, value, executeChangeCB)

    def getValue(self):
        value = MelOptionMenu.getValue(self)

        return ShapeDesc(value)

class MelOptionMenu_Axis(MelOptionMenu):
    def __new__(cls, parent, *a, **kw):
        self = MelOptionMenu.__new__(cls, parent, *a, **kw)
        self.populate()

        return self

    def populate(self):
        self.clear()
        for shapeName in sorted(Axis.AXES):
            self.append(shapeName)

    def setValue(self, value, executeChangeCB=True):
        if type(value) is type:
            return

        if isinstance(value, Axis):
            value = value.asName()

        return MelOptionMenu.setValue(self, value, executeChangeCB)

#define some UI mappings based on arg types/names...
baseMelUI.UI_FOR_PY_TYPES[baseSkeletonPart.SkeletonPart] = MelOptionMenu_SkeletonPart
baseMelUI.UI_FOR_PY_TYPES[MelOptionMenu_Arm.PART_CLASS] = MelOptionMenu_Arm
baseMelUI.UI_FOR_PY_TYPES[ShapeDesc] = MelOptionMenu_Shape
UI_FOR_NAMED_RIG_ARGS['axis'] = MelOptionMenu_Axis
UI_FOR_NAMED_RIG_ARGS['direction'] = MelOptionMenu_Axis

setParent = cmds.setParent

class SeparatorLabelLayout(MelFormLayout):
    def __init__(self, parent, label):
        MelFormLayout.__init__(self, parent)
        self.UI_label = MelLabel(self, label=label, align='left')
        setParent(self)
        self.UI_separator = cmds.separator(horizontal=True)

        self(e=True,
             af=((self.UI_label, 'left', 0),
                 (self.UI_separator, 'top', 6),
                 (self.UI_separator, 'right', 0)),
             ac=((self.UI_separator, 'left', 5, self.UI_label)))

class SkeletonPartOptionMenu(MelOptionMenu):
    DYNAMIC = False
    STATIC_CHOICES = [partCls.__name__ for partCls in baseSkeletonPart.SkeletonPart.GetSubclasses() if
                      partCls.AVAILABLE_IN_UI]

class ManualPartCreationLayout(MelHSingleStretchLayout):
    def __init__(self, parent, *a, **kw):
        MelHSingleStretchLayout.__init__(self, parent, *a, **kw)

        self.UI_partType = SkeletonPartOptionMenu(self)

        self.UI_convert = MelButton(self, l='Convert Selection To Skeleton Part', c=self.on_convert)
        self.setSelectionChangeCB(self.on_selectionChange)

        self.setStretchWidget(self.UI_convert)
        self.layout()

        self.on_selectionChange()

    ### EVENT HANDLERS ###
    def on_convert(self, *a):
        partTypeStr = self.UI_partType.getValue()
        partType = baseSkeletonPart.SkeletonPart.GetNamedSubclass(partTypeStr)
        sel = cmds.ls(sl=True)

        newPart = partType(baseSkeletonPart.buildSkeletonPartContainer(partType, {}, sel))
        newPart.convert({})
        self.sendEvent('manualPartCreated', newPart)

    def on_selectionChange(self, *a):
        sel = cmds.ls(sl=True)
        if not sel:
            self.UI_convert.disable()
        else:
            self.UI_convert.enable()

class CommonButtonsLayout(MelColumn):
    def __init__(self, parent):
        MelColumn.__init__(self, parent, rowSpacing=4, adj=True)

        ### SETUP PART DRIVING RELATIONSHIPS
        SeparatorLabelLayout(self, 'Part Connection Controls')
        buttonForm = MelHLayout(self)
        MelButton(buttonForm, l='Drive All Parts', c=self.on_allDrive)
        MelButton(buttonForm, l='Drive Parts With First Selected', c=self.on_drive)
        MelButton(buttonForm, l='Break Driver For Selected', c=self.on_breakDrive)
        MelButton(buttonForm, l='Break All Drivers', c=self.on_breakAllDrive)
        buttonForm.layout()

        ### SETUP VISUALIZATION CONTROLS
        SeparatorLabelLayout(self, 'Visualization')
        buttonForm = MelHLayout(self)
        MelButton(buttonForm, l='Visualization ON', c=self.on_visOn)
        MelButton(buttonForm, l='Visualization OFF', c=self.on_visOff)
        buttonForm.layout()

        ### SETUP ALIGNMENT CONTROL BUTTONS
        SeparatorLabelLayout(self, 'Part Alignment')
        buttonForm = MelHLayout(self)
        MelButton(buttonForm, l='Re-Align Selected Part', c=self.on_reAlign)
        MelButton(buttonForm, l='Re-Align ALL Parts', c=self.on_reAlignAll)
        buttonForm.layout()

        ### SETUP SKINNING CONTROL BUTTONS
        skinFrame = MelFrameLayout(self, l='Skinning Tools', cl=True, cll=True, bs='etchedOut')
        skinCol = MelColumnLayout(skinFrame)

        buttonForm = MelHLayout(skinCol)
        self.UI_skinOff = MelButton(buttonForm, l='Turn Skinning Off', c=self.on_skinOff)
        self.UI_skinOn = MelButton(buttonForm, l='Turn Skinning On', c=self.on_skinOn)
        MelButton(buttonForm, l='Reset All Skin Clusters', c=self.on_resetSkin)
        buttonForm.layout()
        self.updateSkinButtons()

        ### SETUP VOLUME BUILDER CONTROL BUTTONS
        SeparatorLabelLayout(skinCol, 'Volume Tools')
        buttonForm = MelHLayout(skinCol)
        MelButton(buttonForm, l='Create Volumes', c=self.on_buildVolumes)
        MelButton(buttonForm, l='Extract Selected To Volume', c=self.on_extractSelected)
        MelButton(buttonForm, l='Fit Selected Volumes', c=self.on_fitVolumes)
        MelButton(buttonForm, l='Remove Volumes', c=self.on_removeVolumes)
        buttonForm.layout()

        buttonForm = MelHLayout(skinCol)
        MelButton(buttonForm, l='Open Skin Weights Tool', c=lambda *a: skinWeightsUI.SkinWeightsWindow())
        MelButton(buttonForm, l='Generate Skin Weights', c=self.on_generateWeights)
        buttonForm.layout()

        self.setSceneChangeCB(self.on_sceneOpen)

    def updateSkinButtons(self):
        state = rig_utils.getSkinClusterEnableState()
        self.UI_skinOn(e=True, en=not state)
        self.UI_skinOff(e=True, en=state)

    def on_allDrive(self, e=None):
        baseSkeletonPart.setupAutoMirror()

    def on_drive(self, e=None):
        selParts = baseSkeletonPart.getPartsFromObjects(cmds.ls(sl=True))
        if len(selParts) <= 1:
            print 'WARNING :: please select two or more parts - the first part selected will drive consequent parts'
            return

        firstPart = selParts.pop(0)
        for p in selParts:
            firstPart.driveOtherPart(p)

    def on_breakDrive(self, e=None):
        for p in baseSkeletonPart.getPartsFromObjects(cmds.ls(sl=True)):
            p.breakDriver()

    def on_breakAllDrive(self, e=None):
        for p in baseSkeletonPart.SkeletonPart.Iter():
            p.breakDriver()

    def on_reAlign(self, e=None):
        baseSkeletonPart.realignSelectedParts()

    def on_reAlignAll(self, e=None):
        baseSkeletonPart.realignAllParts()

    def on_finalize(self, e=None):
        baseSkeletonPart.finalizeAllParts()

    def on_visOn(self, e=None):
        for p in baseSkeletonPart.SkeletonPart.Iter():
            p.visualize()

    def on_visOff(self, e=None):
        for p in baseSkeletonPart.SkeletonPart.Iter():
            p.unvisualize()

    def on_skinOff(self, e=None):
        rig_utils.disableSkinClusters()
        self.updateSkinButtons()

    def on_skinOn(self, e=None):
        rig_utils.enableSkinClusters()
        self.updateSkinButtons()

    @d_showWaitCursor
    def on_resetSkin(self, e=None):
        for sc in cmds.ls(typ='skinCluster'):
            rig_utils.resetSkinCluster(sc)

    def on_buildVolumes(self, e=None):
        volumes.buildAllVolumes()

    def on_fitVolumes(self, e=None):
        volumes.shrinkWrapSelection()

    def on_removeVolumes(self, e=None):
        volumes.removeAllVolumes()

    def on_extractSelected(self, e=None):
        cmds.select(mesh_utils.extractFaces(cmds.ls(sl=True, fl=True)))
        mel_utils.MEL.setSelectMode("objects", "Objects")

    def on_generateWeights(self, e=None):
        volumes.volumesToSkinning()

    def on_sceneOpen(self, *a):
        self.updateSkinButtons()

class BuildPartLayout(MelFormLayout):
    '''
    ui for single skeleton part creation
    '''
    BUTTON_LBL_TEMPLATE = 'Create %s'

    def __new__(cls, parent, partClass):
        return MelFormLayout.__new__(cls, parent)

    def __init__(self, parent, partClass):
        MelFormLayout.__init__(self, parent)

        self.partClass = partClass
        self.UI_create = cmds.button(l=self.BUTTON_LBL_TEMPLATE % str_utils.camelCaseToNice(partClass.GetPartName()),
                                     c=self.on_create, w=160)

        #now populate the ui for the part's args
        self.kwarg_UIs = {}  #keyed by arg name
        kwargList = partClass.GetDefaultBuildKwargList()
        self.UI_argsLayout = MelFormLayout(self)

        #everything has a parent attribute, so build it first
        prevUI = None
        for arg, default in kwargList:
            #skip UI for parent - assume selection always
            if arg == 'parent':
                continue

            setParent(self.UI_argsLayout)
            lbl = cmds.text(l=str_utils.camelCaseToNice(arg))

            #determine the function to use for building the UI for the arg
            buildMethodFromName = UI_FOR_NAMED_RIG_ARGS.get(arg, None)
            buildMethodFromType = getBuildUIMethodForObject(default) or MelTextField

            buildMethod = buildMethodFromName or buildMethodFromType

            self.kwarg_UIs[arg] = argUI = buildMethod(self.UI_argsLayout)
            argUI.setValue(default)

            #perform layout
            if prevUI is None:
                self.UI_argsLayout(e=True, af=((lbl, 'left', 15)))
            else:
                self.UI_argsLayout(e=True, ac=((lbl, 'left', 15, prevUI)))

            if isinstance(argUI, MelCheckBox):
                self.UI_argsLayout(e=True, af=((argUI, 'top', 3)))

            self.UI_argsLayout(e=True, af=((lbl, 'top', 3)), ac=((argUI, 'left', 5, lbl)))
            prevUI = argUI

        setParent(self)

        self(e=True, af=((self.UI_create, 'left', 0),
                         (self.UI_argsLayout, 'right', 0)),
             ac=((self.UI_argsLayout, 'left', 0, self.UI_create)))

    def getKwargDict(self):
        kwargs = {}
        for arg, ui in self.kwarg_UIs.iteritems():
            kwargs[arg] = ui.getValue()

        if kwargs.has_key('parent'):
            if not kwargs['parent']:
                kwargs['parent'] = None

        kwargs['partScale'] = baseSkeletonPart.getScaleFromSkeleton()

        return kwargs

    def rePopulate(self):
        for argName, ui in self.kwarg_UIs.iteritems():
            if isinstance(ui, MelOptionMenu_SkeletonPart):
                ui.populate()

    def on_create(self, e):
        kwargs = self.getKwargDict()
        self.partClass.Create(**kwargs)
        self.sendEvent('rePopulate')

class BuildingLayout(MelScrollLayout):
    '''
    ui for skeleton part creation
    '''

    def __init__(self, parent):
        MelScrollLayout.__init__(self, parent, childResizable=True)

        self.UI_col = col = MelColumnLayout(self, rowSpacing=4, adj=True)

        MelLabel(col, l='Build Individual Parts', align='left')
        MelLabel(col, l='', height=5)

        ### BUILD THE PART CREATION BUTTONS ###
        self.UI_list = []
        parts = baseSkeletonPart.SkeletonPart.GetSubclasses()
        for part in parts:
            if part.AVAILABLE_IN_UI:
                self.UI_list.append(BuildPartLayout(col, part))

    def rePopulate(self):
        for ui in self.UI_list:
            ui.rePopulate()

class EditPartLayout(MelFormLayout):
    ARGS_TO_HIDE = ['parent', 'partScale', 'idx']

    def __new__(cls, parent, part):
        return MelFormLayout.__new__(cls, parent)

    def __init__(self, parent, part):
        MelFormLayout.__init__(self, parent)

        self.part = part
        self.argUIs = {}

        self.populate()

    def clear(self):
        MelFormLayout.clear(self)
        self.argUIs = {}

    def populate(self):
        #remove any existing children
        self.clear()
        part = self.part
        assert isinstance(part, baseSkeletonPart.SkeletonPart)

        #pimp out the UI
        lbl = MelButton(self, l=part.getPartName(), w=140, c=self.on_select)

        #grab the args the rigging method takes
        argsForm = MelFormLayout(self)
        argsUIs = []

        buildKwargs = part.getBuildKwargs()
        for arg in self.ARGS_TO_HIDE:
            buildKwargs.pop(arg, None)

        for arg, argValue in buildKwargs.iteritems():
            argLbl = MelLabel(argsForm, label=str_utils.camelCaseToNice(arg))

            #determine the function to use for building the UI for the arg
            buildMethodFromName = UI_FOR_NAMED_RIG_ARGS.get(arg, None)
            buildMethodFromType = getBuildUIMethodForObject(argValue) or MelTextField

            #prioritize the method from name over the method from type
            buildMethod = buildMethodFromName or buildMethodFromType

            argWidget = buildMethod(argsForm)
            argWidget.setValue(argValue)

            argsUIs.append(argLbl)
            argsUIs.append(argWidget)
            self.argUIs[arg] = argWidget

        try:
            inc = 1.0 / len(argsUIs)
        except ZeroDivisionError:
            inc = 1.0

        for n, ui in enumerate(argsUIs):
            p = n * inc
            if n:
                argsForm(e=True, ac=((ui, 'left', 5, argsUIs[n - 1])))
            else:
                argsForm(e=True, af=((ui, 'left', 0)))

        #build the "rebuild" button
        reButt = MelButton(self, l="rebuild", c=self.on_rebuild, w=75)

        #build the "delete" button
        deleteButt = MelButton(self, l="delete", c=self.on_delete, w=60)

        #perform layout...
        self.setWidth(50)
        argsForm.setWidth(50)

        self(
            e=True,
            af=((lbl, 'left', 0),
                (deleteButt, 'right', 0)),
            ac=((argsForm, 'left', 5, lbl),
                (reButt, 'right', 0, deleteButt),
                (argsForm, 'right', 0, reButt)))

    def getBuildKwargs(self):
        kwargs = {}
        for argName, widget in self.argUIs.iteritems():
            kwargs[argName] = widget.getValue()

        return kwargs

    def on_rebuild(self, e):
        self.part.rebuild(**self.getBuildKwargs())
        self.populate()

    def on_select(self, e=None):
        cmds.select(self.part.items)

    def on_delete(self, e=None):
        self.part.delete()
        self.delete()

class EditingLayout(MelScrollLayout):
    def __init__(self, parent):
        MelScrollLayout.__init__(self, parent, childResizable=True)

    def populate(self):
        self.clear()

        col = MelColumn(self, rowSpacing=4, adj=True)
        self.UI_partForms = []
        for part in baseSkeletonPart.SkeletonPart.IterInOrder():
            partRigForm = EditPartLayout(col, part)
            self.UI_partForms.append(partRigForm)

class RigPartLayout(MelFormLayout):
    '''
    ui for single rig primitive
    '''

    def __new__(cls, parent, part):
        return MelFormLayout.__new__(cls, parent)

    def __init__(self, parent, part):
        MelFormLayout.__init__(self, parent)

        self.part = part
        self.argUIs = {}

        lbl = MelButton(self, l=part.getPartName(), w=140, c=self.on_select)

        rigKwargs = part.getRigKwargs()

        #build the disable and optionbox for the rig method
        disableState = rigKwargs.get('disable', False)
        disable = self.UI_disable = MelCheckBox(self, l='disable')
        rigTypes = self.rigTypes = [rigType for rigType in part.RigTypes if rigType.CanRigThisPart(part)]

        if len(rigTypes) > 1:
            opts = MelOptionMenu(self, cc=self.on_rigMethodCB)
            opts.enable(not disableState)
            for method in rigTypes:
                opts.append(method.__name__)

            rigMethodName = rigKwargs.get('rigMethodName', rigTypes[0].__name__)
            if rigMethodName in opts.getItems():
                opts.selectByValue(rigMethodName, False)
        else:
            opts = MelLabel(self, l='')

        self.UI_options = opts
        argsForm = self.UI_argsForm = MelHRowLayout(self)
        self.UI_manualRig = manRig = MelButton(self)
        self.updateBuildRigButton()

        #perform layout...
        self(e=True,
             af=((lbl, 'left', 0),
                 (manRig, 'right', 0)),
             ac=((disable, 'left', 3, lbl),
                 (opts, 'left', 0, disable),
                 (argsForm, 'left', 0, opts),
                 (argsForm, 'right', 0, manRig)))

        #set initial UI state
        disable.setChangeCB(self.on_argCB)
        disable.setValue(disableState, False)

        self.populate()

    def clearArgs(self):
        self.UI_argsForm.clear()
        self.argUIs = {}

    def populate(self):
        if not bool(self.rigTypes):
            self.setVisibility(False)
            return

        #remove any existing children
        self.clearArgs()
        part = self.part

        rigKwargs = part.getRigKwargs()

        #build the disable and optionbox for the rig method
        disableState = rigKwargs.get('disable', False)

        #grab the args the rigging method takes
        argsForm = self.UI_argsForm
        argsUIs = []

        rigMethodName = rigKwargs.get('rigMethodName', self.rigTypes[0].__name__)
        rigClass = baseRigPart.RigPart.GetNamedSubclass(rigMethodName)

        if rigClass is None:
            rigClass = part.RigTypes[0]

        zeroWeightTypes = MelCheckBox, MelOptionMenu

        argNamesAndDefaults = rigClass.GetDefaultBuildKwargList()
        for arg, default in argNamesAndDefaults:
            argValue = rigKwargs.get(arg, default)
            argLbl = MelLabel(argsForm, label=str_utils.camelCaseToNice(arg))

            #determine the function to use for building the UI for the arg
            buildMethodFromName = UI_FOR_NAMED_RIG_ARGS.get(arg, None)
            buildMethodFromType = getBuildUIMethodForObject(default) or MelTextField

            buildMethod = buildMethodFromName or buildMethodFromType

            argWidget = buildMethod(argsForm)
            argWidget.setValue(argValue, False)
            argWidget.setChangeCB(self.on_argCB)

            argLbl.enable(not disableState)
            argWidget.enable(not disableState)

            argsUIs.append(argLbl)
            argsUIs.append(argWidget)
            self.argUIs[arg] = argWidget

        #if there are no args - create an empty text widget otherwise maya will crash.  yay!
        argsUIs.append(MelLabel(argsForm, label=''))

        argsForm.layout()

    def getRigKwargs(self):
        disableState = self.UI_disable.getValue()
        kwargs = {'disable': disableState, }
        if isinstance(self.UI_options, MelOptionMenu):
            rigMethod = self.UI_options.getValue()
            if rigMethod:
                kwargs['rigMethodName'] = rigMethod

        for argName, widget in self.argUIs.iteritems():
            kwargs[argName] = widget.getValue()

        self.UI_options.enable(not disableState)
        for child in self.UI_argsForm.getChildren():
            child.enable(not disableState)

        return kwargs

    def updateBuildRigButton(self):
        self.UI_manualRig.setLabel('')
        self.UI_manualRig.setVisibility(False)
        self.UI_manualRig.setEnabled(False)

        # if self.part.isRigged():
        #     self.UI_manualRig.setLabel('Delete Rig')
        #     self.UI_manualRig.setChangeCB(self.on_deleteRig)
        # else:
        #     self.UI_manualRig.setLabel('Build This Rig Only')
        #     self.UI_manualRig.setChangeCB(self.on_manualRig)

        self.UI_manualRig.setWidth(120)

        rigKwargs = self.part.getRigKwargs()
        self.UI_manualRig.setEnabled(not rigKwargs.get('disable', False))

    ### EVENT HANDLERS ###
    def on_rigMethodCB(self, e):
        #set the rig kwargs based on the current UI - it may be wrong however, because the new rig method may have different calling args
        self.part.setRigKwargs(self.getRigKwargs())

        #rebuild the UI to reflect the possibly new options for the changed rig method
        self.populate()

        #now store the rig kwargs again based on the correct UI
        self.part.setRigKwargs(self.getRigKwargs())

    def on_argCB(self, e=None):
        self.part.setRigKwargs(self.getRigKwargs())
        self.updateBuildRigButton()

    def on_select(self, e=None):
        cmds.select(self.part.items)

    def on_manualRig(self, e=None):
        self.part.finalize()
        self.part.rig()
        self.updateBuildRigButton()

    def on_deleteRig(self, e=None):
        self.part.deleteRig()
        self.updateBuildRigButton()

class RiggingLayout(MelFormLayout):
    '''
    ui for rig primitive creation
    '''

    def __init__(self, parent):
        MelFormLayout.__init__(self, parent)

        scroll = MelScrollLayout(self, cr=True)
        self.UI_parts = MelColumn(scroll, rowSpacing=4, adj=True)
        self.UI_buttons = MelColumn(self, rowSpacing=4, adj=True)


        ### BUILD STATIC BUTTONS
        buttonParent = self.UI_buttons
        setParent(buttonParent)
        optsLbl = MelLabel(buttonParent, label='Rig Build Options', align='left')

        buildRigLayout = MelHLayout(buttonParent)
        self.UI_reference = MelCheckBox(buildRigLayout, label='reference model')
        self.UI_reference.setValue(False)

        buildRigLayout.layout()

        setParent(buttonParent)
        sep = cmds.separator(horizontal=True)
        but = MelButton(buttonParent, l='BUILD RIG', c=self.on_buildRig, height=35)
        deleteButton = MelButton(buttonParent, l='DELETE RIG', c=self.on_deleteRig, height=35)

        self(e=True,
             af=((scroll, 'top', 0),
                 (scroll, 'left', 0),
                 (scroll, 'right', 0),
                 (self.UI_buttons, 'left', 0),
                 (self.UI_buttons, 'right', 0),
                 (self.UI_buttons, 'bottom', 0)),
             ac=((scroll, 'bottom', 3, self.UI_buttons)))

    def populate(self):
        self.UI_parts.clear()

        col = self.UI_parts

        self.UI_partForms = []
        for part in baseSkeletonPart.SkeletonPart.IterInOrder():
            partRigForm = RigPartLayout(col, part)
            self.UI_partForms.append(partRigForm)

    def on_buildRig(self, e=None):
        curScene = path.Path(cmds.file(q=True, sn=True))

        referenceModel = self.UI_reference.getValue()
        if referenceModel:
            if not curScene:
                cmds.confirmDialog(t='Scene not saved!',
                                   m="Looks like your current scene isn't saved\n\nPlease save it first so I know where to save the rig.  thanks!",
                                   b=('OK',), db='OK')
                return

        baseRigPart.buildRigForModel(referenceModel=referenceModel, deletePlacers=False)

        #if the model is being referenced run populate to update the rig part instances - container names will have changed because they're now referenced
        if referenceModel:
            self.populate()

        #if we're not referencing the model however, its safe to just run the updateBuildRigButton method on all rig part UI instances
        else:
            for partUI in self.UI_partForms:
                partUI.updateBuildRigButton()

    def on_deleteRig(self, e=None):
        baseRigPart.deleteRigForAllParts()

class CreateEditRigTabLayout(MelTabLayout):
    def __init__(self, parent, *a, **kw):
        MelTabLayout.__init__(self, parent, *a, **kw)

        ### THE SKELETON CREATION TAB
        insetForm = self.SZ_skelForm = MelFormLayout(self)
        self.UI_builder = ed = BuildingLayout(insetForm)
        self.UI_commonButtons = bts = CommonButtonsLayout(insetForm)

        insetForm(e=True,
                  af=((ed, 'top', 7),
                      (ed, 'left', 5),
                      (ed, 'right', 5),
                      (bts, 'left', 5),
                      (bts, 'right', 5),
                      (bts, 'bottom', 5)),
                  ac=((ed, 'bottom', 5, bts)))


        ### THE RIGGING TAB
        insetForm = self.SZ_rigForm = MelFormLayout(self)
        self.UI_rigger = ed = RiggingLayout(insetForm)

        insetForm(e=True,
                  af=((ed, 'top', 7),
                      (ed, 'left', 5),
                      (ed, 'right', 5),
                      (ed, 'bottom', 5)))

        self.setLabel(0, 'create skeleton')
        self.setLabel(1, 'create rig')

        self.setSceneChangeCB(self.on_sceneOpen)
        self.setChangeCB(self.on_change)

    ### EVENT HANDLERS ###
    def on_change(self):
        if self.getSelectedTab() == self.SZ_rigForm:
            self.UI_rigger.populate()

    def on_sceneOpen(self, *a):
        self.setSelectedTabIdx(0)

class SkeletonBuilderWindow(BaseMelWindow):
    WINDOW_NAME = 'skeletonBuilder'
    WINDOW_TITLE = 'Skeleton Builder'

    DEFAULT_SIZE = 700, 700
    DEFAULT_MENU = 'Tools'

    FORCE_DEFAULT_SIZE = True

    def __init__(self):
        self.editor = CreateEditRigTabLayout(self)

        tMenu = self.getMenu('Tools')
        cmds.menu(tMenu, e=True, pmc=self.buildToolsMenu)

        dMenu = self.getMenu('Dev')
        cmds.menu(dMenu, e=True, pmc=self.buildDevMenu)

        #close related windows...
        UserAlignListerWindow.Close()
        PartExplorerWindow.Close()

        self.show()

    def buildToolsMenu(self, *a):
        menu = self.getMenu('Tools')
        menu.clear()

        MelMenuItem(
            menu, l='Bone Count HUD', cb=cmds.headsUpDisplay(baseSkeletonPart.HUD_NAME, ex=True),
            c=lambda _: baseSkeletonPart.setupSkeletonBuilderJointCountHUD())
        MelMenuItem(menu, l='Pose Mirroring Tool', c=self.on_loadMirrorTool)
        MelMenuItemDiv(menu)

        MelMenuItem(menu, l='Mark Selected As User Aligned', c=self.on_markUserAligned)
        MelMenuItem(menu, l='Clear User Aligned On Selected', c=self.on_clearUserAligned)
        MelMenuItem(menu, l='User Aligned Editor', c=lambda _: UserAlignListerWindow())

    def buildDevMenu(self, *a):
        menu = self.getMenu('Dev')
        menu.clear()

        MelMenuItem(menu, l='Skeleton Part Code Explorer', c=lambda *a: PartExplorerWindow())
        MelMenuItem(menu, l='Reload Tool', c=lambda *a: reloadSkeletonBuilder())

    ### EVENT HANDLERS ###
    def on_markUserAligned(self, *a):
        for j in cmds.ls(sl=True, type='joint') or []:
            baseSkeletonPart.setAlignSkipState(j, True)

    def on_clearUserAligned(self, *a):
        for j in cmds.ls(sl=True, type='joint') or []:
            baseSkeletonPart.setAlignSkipState(j, False)

    def on_loadMirrorTool(self, *a):
        import poseSymUI

        poseSymUI.PoseSymWindow()

SkeletonBuilderUI = SkeletonBuilderWindow

class PartExplorerLayout(MelTabLayout):
    def __init__(self, parent):
        MelTabLayout.__init__(self, parent)

        #do skeleton parts
        skeletonPartScroll = MelScrollLayout(self)
        theCol = MelColumnLayout(skeletonPartScroll)

        def getFile(cls):
            clsFile = path.Path(inspect.getfile(cls))
            if clsFile.setExtension('py').exists():
                return clsFile.setExtension('py')

            return clsFile

        for cls in baseSkeletonPart.SkeletonPart.IterSubclasses():
            clsFile = getFile(cls)

            col = MelColumnLayout(theCol)

            MelSeparator(col, h=5)

            hLayout = MelHSingleStretchLayout(col)
            MelLabel(hLayout, l=cls.GetPartName(), align='left').bold(True)
            MelSpacer(hLayout, w=10)
            lbl = MelLabel(hLayout, l=clsFile, align='left')
            hLayout.setStretchWidget(lbl)
            hLayout.layout()

        #do rig parts
        rigPartScroll = MelScrollLayout(self)
        theCol = MelColumnLayout(rigPartScroll)

        for cls in baseRigPart.RigPart.IterSubclasses():
            clsFile = getFile(cls)

            col = MelColumnLayout(theCol)

            MelSeparator(col, h=5)

            hLayout = MelHSingleStretchLayout(col)
            MelLabel(hLayout, l=cls.GetPartName(), align='left').bold(True)
            MelSpacer(hLayout, w=10)
            lbl = MelLabel(hLayout, l=clsFile, align='left')
            hLayout.setStretchWidget(lbl)
            hLayout.layout()

        #setup labels
        self.setLabel(0, 'Skeleton Parts')
        self.setLabel(1, 'Rig Parts')

    def on_change(self):
        self.sendEvent('layout')

class PartExplorerWindow(BaseMelWindow):
    WINDOW_NAME = 'skeletonBuilderPartExplorer'
    WINDOW_TITLE = '%s: Part Code Explorer' % SkeletonBuilderWindow.WINDOW_TITLE

    DEFAULT_MENU = None

    DEFAULT_SIZE = 450, 250
    FORCE_DEFAULT_SIZE = True

    def __init__(self):
        PartExplorerLayout(self)
        self.show()
        self.layout()

class UserAlignListerLayout(MelVSingleStretchLayout):
    def __init__(self, parent):
        def itemAsStr(item):
            if baseSkeletonPart.getAlignSkipState(item):
                return '* %s' % item

            return '  %s' % item

        UI_itemList = MelObjectScrollList(self)
        UI_itemList.itemAsStr = itemAsStr

        for part in baseSkeletonPart.SkeletonPart.IterInOrder():
            for item in part:
                UI_itemList.append(item)

        hLayout = MelHLayout(self)
        MelButton(hLayout, l='Mark As User Aligned')
        MelButton(hLayout, l='Clear User Aligned')
        hLayout.layout()

        self.setStretchWidget(UI_itemList)
        self.layout()

class UserAlignListerWindow(BaseMelWindow):
    WINDOW_NAME = 'skeletonBuilderUserAlignedJointsWindow'
    WINDOW_TITLE = '%s: User Aligned Joints' % SkeletonBuilderWindow.WINDOW_TITLE

    DEFAULT_MENU = None

    DEFAULT_SIZE = 350, 200

    def __init__(self):
        self.setSceneChangeCB(lambda: self.close())  #close on scene load...
        UserAlignListerLayout(self)
        self.show()

#end
