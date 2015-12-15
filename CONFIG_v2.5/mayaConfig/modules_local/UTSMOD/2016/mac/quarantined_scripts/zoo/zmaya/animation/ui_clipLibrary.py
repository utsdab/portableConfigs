
from PySide.QtGui import *
from PySide.QtCore import Qt, QSize, Signal

from maya import cmds

from ... import presets
from ... import anim_widget

from .. import base_ui
from .. import filterable_list
from .. import maya_decorators

from ..skeletonBuilder import tools

import clip
import clipLibrary

def getNodes(useAllRigControls):
    """
    this method is used to query the nodes that get saved

    it is also used to determine what "space" in which to search for nodes when loading
    a clip. When a clip is loaded, the tool needs to figure out how to map node names
    from the clip to the nodes in the scene
    """
    controls = ()
    if useAllRigControls:
        controls = tools.getAllRigControlsFromSelection()

    return controls or cmds.ls(sl=True) or ()

class LocaleComboBox(QComboBox):
    def __init__(self):
        super(LocaleComboBox, self).__init__()

        for locale in presets.LOCALES:
            self.addItem(locale.name)

    @property
    def locale(self):
        return presets.LOCALES[self.currentIndex()]

    def setLocale(self, locale):
        idx = presets.LOCALES.index(locale)
        self.setCurrentIndex(idx)

class ClipLibraryComboBox(QComboBox):
    librarySelected = Signal(object)

    def __init__(self):
        super(ClipLibraryComboBox, self).__init__()

        self._libraries = []
        self.currentIndexChanged.connect(self._emitLibrarySelected)

    def _emitLibrarySelected(self, idx):
        if idx >= 0:
            self.librarySelected.emit(self._libraries[idx])

    @property
    def selectedLibrary(self):
        return self._libraries[self.currentIndex()]

    def selectLibrary(self, library):
        try:
            idx = self._libraries.index(library)
        except ValueError: return

        self.setCurrentIndex(idx)
        self.librarySelected.emit(library)

    def appendLibrary(self, library, select=False):
        self._libraries.append(library)
        self.addItem(str(library))

        if select:
            self.selectLibrary(library)

    def populate(self):
        initialIdx = self.currentIndex()

        self._libraries = []
        self.clear()
        for lib in clipLibrary.Library.Iter():
            self.appendLibrary(lib, False)

        if initialIdx >= 0:
            self.selectLibrary(self._libraries[initialIdx])
        else:
            if self._libraries:
                self.setCurrentIndex(0)
                self.librarySelected.emit(self.selectedLibrary)

class ClipLibrariesWidget(QGroupBox):
    librarySelected = Signal(object)

    def __init__(self):
        super(ClipLibrariesWidget, self).__init__("Libraries")

        self._libraries = ClipLibraryComboBox()
        self._libraries.librarySelected.connect(self._librarySelected)

        self._createButton = QPushButton(" Create New... ")
        self._createButton.clicked.connect(self.on_createLibrary)

        self._deleteButton = QPushButton(" Delete ")
        self._deleteButton.clicked.connect(self.on_deleteLibrary)

        mainLayout = QHBoxLayout()
        mainLayout.addWidget(self._libraries, 1)
        mainLayout.addWidget(self._createButton)
        mainLayout.addWidget(self._deleteButton)

        self.setLayout(mainLayout)

    def populate(self):
        selLibName = cmds.optionVar(q='zooClipLibrarySelectedLibraryName')

        self._libraries.populate()

        # select the library stored in prefs
        self._libraries.selectLibrary(clipLibrary.Library(selLibName))

    def _librarySelected(self, library):
        cmds.optionVar(sv=('zooClipLibrarySelectedLibraryName', library.name))
        self.librarySelected.emit(library)

    @property
    def selectedLibrary(self):
        return self._libraries.selectedLibrary

    def on_createLibrary(self):
        libraryName, ret = QInputDialog.getText(self, "Create New Library", "Library name")
        if ret:
            newLibrary = clipLibrary.Library(libraryName)
            newLibrary.create()
            self._libraries.appendLibrary(newLibrary, True)

    def on_deleteLibrary(self):
        pass

class ClipListItem(QListWidgetItem):
    def __init__(self, item, *args):
        super(ClipListItem, self).__init__(item.displayText.split('.')[0])

        self._item = item
        self._args = args

        item.moved.append(self._clipMoved)
        item.deleted.append(self._clipDeleted)

        self.updateIcon()

    def __str__(self):
        return self._item.displayText

    def updateIcon(self, xFraction = 0):
        icon = None
        item = self._item
        if isinstance(item, clipLibrary.PoseClipPreset):
            if item.iconFilepath.exists():
                icon = QIcon(item.iconFilepath)
        elif isinstance(item, clipLibrary.AnimClipPreset):
            sequence = item.playblastImgSequence
            frame = sequence.getFrameFromPercent(xFraction)
            image = sequence.getImage(frame)
            if image is not None:
                pixmap = QPixmap()
                pixmap.convertFromImage(image)
                icon = QPixmap(pixmap)

        if icon is not None:
            self.setIcon(icon)

    def _clipMoved(self):
        self.setText(self._item.displayText)
        self.listWidget().listItemClipMoved.emit(self)

    def _clipDeleted(self):
        listWidget = self.listWidget()
        modelIdx = listWidget.indexFromItem(self)
        listWidget.takeItem(modelIdx.row())

class ClipPresetListWidget(filterable_list.FilterableListWidget):
    listItemClipMoved = Signal(object) # object is the list item who's clip was moved
    clipItemDoubleClicked = Signal(object)

    def __init__(self):
        super(ClipPresetListWidget, self).__init__(ClipListItem)

        textHeight = QFontMetrics(self.font()).height()
        iconSz = clipLibrary.ClipPreset.ICON_SIZE

        self._list.setWrapping(True)
        self._list.setUniformItemSizes(True)
        self._list.setGridSize(QSize(iconSz + 25, iconSz + textHeight + 10))
        self._list.setIconSize(QSize(iconSz, iconSz))
        self._list.setFlow(QListView.Flow.LeftToRight)
        self._list.setMovement(QListView.Movement.Static)
        self._list.setResizeMode(QListView.ResizeMode.Adjust)
        self._list.itemDoubleClicked.connect(self.clipItemDoubleClicked.emit)

        # monkey patch the viewOptions method to control icon layout
        orgFunc = self._list.viewOptions
        def viewOptions():
            options = orgFunc()

            # place the icon above the text
            options.decorationPosition = QStyleOptionViewItem.Position.Top

            # center text in the item
            options.displayAlignment = Qt.AlignHCenter

            return options

        self._list.viewOptions = viewOptions

        # this is a complete hack - we want the listItemClipMoved signal on the list
        # widget so that the ClipListItem can access it by looking at its listWidget
        self._list.listItemClipMoved = self.listItemClipMoved

        # this is a bit hacky, but overload the method on the list instance so we can
        # defined a mouse move event handler to update icons for anim clip presets
        # NOTE: patching this method stops the itemEntered signal from being emitted
        self._list.mouseMoveEvent = self._mouseMoveEvent
        self._list.setMouseTracking(True)

    def append(self, obj):
        item = super(ClipPresetListWidget, self).append(obj)
        item.setSizeHint(self._list.gridSize())

        return item

    @property
    def item(self):
        selItems = self._list.selectedItems()
        if selItems:
            return selItems[0]

    @property
    def qitem(self):
        return self._list.selectedQItems()[0]

    def contextMenuEvent(self, event):
        menu = QMenu()

        menu.addAction('Apply clip', lambda: self.clipItemDoubleClicked.emit(self.item))
        menu.addSeparator()
        menu.addAction('Re-generate Icon', self.on_regenerateIcon)
        menu.addSeparator()
        menu.addAction('Spew control names', self.on_spewControlNames)
        menu.addAction('Select all clip controls', self.on_selectClipControls)

        menu.exec_(event.globalPos())

    def on_regenerateIcon(self):
        if self.item is None:
            return

        clipPreset = self.item
        clipPreset.generateIcon()
        self.qitem.updateIcon()

    def on_spewControlNames(self):
        if self.item is None:
            return

        clipPreset = self.item
        print
        print '======== NODES IN CLIP: %s ========' % clipPreset.name
        for n in clipPreset.load().getNodes():
            print n

        print '=========================='

    def on_selectClipControls(self):
        clipPreset = self.item
        clip = clipPreset.load()
        mapping = clip.getMappingFromNodes(getNodes(True))

        cmds.select([tgt for src, tgt in mapping.iteritems()])

    def _mouseMoveEvent(self, event):
        itemUnderCursor = self._list.itemAt(event.pos())
        if itemUnderCursor is None:
            return

        # only bother doing this for anim clips...
        if isinstance(itemUnderCursor._item, clipLibrary.AnimClipPreset):
            l = self._list
            rect = l.rectForIndex(l.indexFromItem(itemUnderCursor))
            xFraction = (event.x() - rect.left()) / float(rect.height())
            itemUnderCursor.updateIcon(xFraction)

def getHighlightedCBAttrs():
    shortAttrNames = []
    flagNames = ('selectedMainAttributes', 'selectedShapeAttributes', 'selectedHistoryAttributes', 'selectedOutputAttributes')

    for flagName in flagNames:
        kwargs = {flagName:True}
        shortAttrNames += cmds.channelBox('mainChannelBox', q=True, **kwargs) or []

    # convert short attr names to long
    longAttrNames = []
    for attrName in shortAttrNames:
        longAttrNames += cmds.listAttr('.' + attrName)

    return longAttrNames

class PoseSliderWidget(QSlider):
    def __init__(self):
        super(PoseSliderWidget, self).__init__(Qt.Horizontal)

        # init to disabled - no point being enabled till a clip has been defined
        self.setEnabled(False)
        self.setRange(0, 100)

        # public attr to store which nodes to apply the clip to
        self.nodes = []

        # public attr to store whether to flip parity when doing the mapping
        self.tryFlippedParity = False

        # public attr which defines whether the clip application should be performed in
        # world space
        self.worldSpace = False

        # public attr to define whether clip should be applied additively
        self.additive = False

        # defines whether to use the highlighted channels as an attr mask
        self.useAttrMask = False

        # store the clip preset
        self._clipPreset = None

        self.sliderPressed.connect(self._sliderBegin)
        self.sliderMoved.connect(self._sliderMoved)
        self.sliderReleased.connect(self._sliderEnd)

    def setClipPreset(self, clipPreset):
        self.setEnabled(clipPreset is not None)
        self._clipPreset = clipPreset

    def _sliderBegin(self):
        self._initialClip = clip.PoseClip.Generate(self.nodes)
        self._clip = self._clipPreset.load().setMappingFromNodes(self.nodes, tryFlippedParity=self.tryFlippedParity)
        self._attrMask = clip.AttrMask(getHighlightedCBAttrs(), True) if self.useAttrMask else None

        # start an undo chunk
        cmds.undoInfo(openChunk=True)

        # turn autokey off but store the initial state
        self._entryAutoKey = cmds.autoKeyframe(q=True, state=True)
        cmds.autoKeyframe(e=True, state=False)

    def _sliderEnd(self):

        # set the value of the slider back to zero
        self.setValue(0)

        # restore the auto key state
        cmds.autoKeyframe(e=True, state=self._entryAutoKey)

        # close the undo chunk opened in the slider begin handler
        cmds.undoInfo(closeChunk=True)

        # delete un-needed temp members - these have no meaning once slider drag has
        # completed, so delete them
        del self._initialClip
        del self._clip
        del self._entryAutoKey
        del self._attrMask

    def _sliderMoved(self):

        # get the slider value
        value = self.value()
        valueRange = float(self.maximum() - self.minimum())
        percent = value / valueRange

        # if the value is max (ie the 100% dest clip value) then simply apply the dest
        # clip fully, no need to blend (computationally expensive)
        if value == self.maximum():
            clip = self._clip

        # again, if the value is min, simply slam the initial clip to the selection, no
        # need to blend
        elif value == self.minimum():
            clip = self._initialClip

        # ok so we have a non-trivial case, perform the blend
        else:
            clip = self._initialClip.blend(self._clip, percent, self.additive)

        # apply whatever clip has been defined to the selection
        clip.applyToNodes(self.nodes, worldSpace=self.worldSpace, attrMask=self._attrMask)

class ApplyClipWidget(QWidget, base_ui.CommonMixin):
    def __init__(self):
        super(ApplyClipWidget, self).__init__()

        self._clipPreset = None

        # this gets set as the layout when no clip preset has been set
        noClipLayout = QVBoxLayout(self)
        noClipLayout.addStretch(1)
        noClipLayout.addWidget(QLabel("No clip selected"))
        noClipLayout.addStretch(1)
        self._noClipWidget = QWidget()
        self._noClipWidget.setLayout(noClipLayout)

        self._icon = anim_widget.AnimWidget()
        self._stats = QLabel()
        self._applyToAllNodesInRig = QCheckBox("Apply to all nodes in clip")
        self._tryReversedParity = QCheckBox("Try reversed handed-ness")
        self._worldSpace = QCheckBox("World Space")
        self._additive = QCheckBox("Additive")
        self._attrMask = QCheckBox("Selected Attrs Only")
        self._poseApplySliderLbl = QLabel("Blend into pose")
        self._poseApplySlider = PoseSliderWidget()
        self._apply = QPushButton("Apply Clip")

        self._applyToAllNodesInRig.stateChanged.connect(lambda val: self.updateDetails())
        self._tryReversedParity.stateChanged.connect(lambda val: self.updateDetails())
        self._tryReversedParity.stateChanged.connect(lambda val: setattr(self._poseApplySlider, 'tryFlippedParity', val))
        self._worldSpace.stateChanged.connect(lambda val: setattr(self._poseApplySlider, 'worldSpace', val))
        self._additive.stateChanged.connect(lambda val: setattr(self._poseApplySlider, 'additive', val))
        self._attrMask.stateChanged.connect(lambda val: setattr(self._poseApplySlider, 'useAttrMask', val))
        self._apply.clicked.connect(self.on_apply)

        # set defaults - make sure to do this AFTER the signals have been connected
        # so that everything gets plumbed through
        self._tryReversedParity.setChecked(True)

        hlayout1 = QHBoxLayout()
        hlayout1.addWidget(self._icon)
        hlayout1.addWidget(self._stats, 1)

        hlayout2 = QHBoxLayout()
        hlayout2.addWidget(self._applyToAllNodesInRig)
        hlayout2.addWidget(self._tryReversedParity)
        hlayout2.addStretch(1)

        hlayout3 = QHBoxLayout()
        hlayout3.addWidget(self._worldSpace)
        hlayout3.addWidget(self._additive)
        hlayout3.addWidget(self._attrMask)
        hlayout3.addStretch(1)

        hlayout4 = QHBoxLayout()
        hlayout4.addWidget(self._poseApplySliderLbl)
        hlayout4.addWidget(self._poseApplySlider, 1)

        self._poseApplySliderLbl.setVisible(False)
        self._poseApplySlider.setVisible(False)

        clipLayout = QVBoxLayout(self)
        clipLayout.addLayout(hlayout1)
        clipLayout.addLayout(hlayout2)
        clipLayout.addLayout(hlayout3)
        clipLayout.addLayout(hlayout4)
        clipLayout.addWidget(self._apply)
        self._clipWidget = QWidget()
        self._clipWidget.setLayout(clipLayout)

        mainLayout = QStackedLayout()
        mainLayout.addWidget(self._noClipWidget)
        mainLayout.addWidget(self._clipWidget)
        self.setLayout(mainLayout)

        # set some tool tips
        self._applyToAllNodesInRig.setToolTip("Applies the clip to all nodes in the currently selected rig")
        self._tryReversedParity.setToolTip("Turn this on if the controls in the clip are of one handed-ness but the selected controls are of the opposite handed-ness")
        self._worldSpace.setToolTip("Applies the clip in world space. Nodes will end up in the same world position as they were in when the clip was generated")
        self._additive.setToolTip("Applies the clip additively to the nodes. Useful for adding hand/face poses on top of an existing pose")
        self._attrMask.setToolTip("Applies the clip to the attributes highlighted in the channel box")
        self._poseApplySliderLbl.setToolTip("Allows you to partially apply the pose")
        self._poseApplySlider.setToolTip(self._poseApplySliderLbl.toolTip())
        self._apply.setToolTip("Applies the clip using the settings defined above")

    def dockChanged(self):

        # update details on node selection - this is mainly so the node mapping match
        # count gets updated
        self.setSelectionChangeCB(self.updateDetails)

    def setClipPreset(self, clipPreset):
        if clipPreset is None:
            self.layout().setCurrentIndex(0)
        else:
            self.layout().setCurrentIndex(1)

            self._clipPreset = clipPreset
            if isinstance(clipPreset, clipLibrary.PoseClipPreset):
                self._icon.setIcon(clipPreset.iconFilepath)
                self._poseApplySlider.setClipPreset(clipPreset)
                self._poseApplySliderLbl.setVisible(True)
                self._poseApplySlider.setVisible(True)
            elif isinstance(clipPreset, clipLibrary.AnimClipPreset):
                self._icon.setSequence(clipPreset.playblastPrefixFilepath)
                self._poseApplySliderLbl.setVisible(False)
                self._poseApplySlider.setVisible(False)

            self.updateDetails()

    __poseClipDetailsStr = "Pose Clip: %s\nNodes in clip: %s\n" + \
                           "Selected nodes in clip: %s\n" + \
                           "Contains world space data: %s"

    __animClipDetailsStr = "Animation Clip: %s\nNodes in clip: %s\n" + \
                           "Selected nodes in clip: %s\n" + \
                           "Contains world space data: %s\n" + \
                           "Start Frame: %s  End Frame: %s  Frames: %s"

    def getNodes(self):
        return getNodes(self._applyToAllNodesInRig.isChecked())

    def _getMapping(self, clip, nodes):
        return clip.getMappingFromNodes(nodes, tryFlippedParity=self._tryReversedParity.isChecked())

    def updateDetails(self):
        if self._clipPreset is None:
            return

        nodes = self.getNodes()
        hasNodes = bool(nodes)

        self._poseApplySlider.nodes = nodes
        self._poseApplySlider.setEnabled(hasNodes)
        self._apply.setEnabled(hasNodes)

        clipPreset = self._clipPreset
        clip = clipPreset.load()
        mapping = self._getMapping(clip, nodes)
        matchCount = len(list(mapping.iteritems()))
        if isinstance(clipPreset, clipLibrary.PoseClipPreset):
            statsStr = self.__poseClipDetailsStr % (
                clipPreset.displayText,
                len(clip.getNodes()),
                matchCount,
                clip.hasWorldSpaceData,
            )
        else:
            statsStr = self.__animClipDetailsStr % (
                clipPreset.displayText,
                len(clip.getNodes()),
                matchCount,
                clip.hasWorldSpaceData,
                clip.getClipRange()[0],
                clip.getClipRange()[1],
                clip.getFrameCount(),
            )

        self._stats.setText(statsStr)

    def on_rename(self):
        if self._clipPreset is None:
            return

        newName = self._name.text()
        if self._clipPreset.name != newName:
            self._clipPreset.rename(newName)

    @maya_decorators.d_undoBlock
    def on_apply(self):

        # prepare all the args to pass to the clip apply method
        additive = self._additive.isChecked()
        worldSpace = self._worldSpace.isChecked()

        # construct the apply kwargs
        kwargs = dict(additive=additive, worldSpace=worldSpace)

        # get the target nodes
        nodes = self.getNodes()

        # load the clip
        theClip = self._clipPreset.load()

        if isinstance(clip, clip.PoseClip):
            kwargs['attrMask'] = clip.AttrMask(getHighlightedCBAttrs(), True) if self._attrMask.isChecked() else None

        # apply the clip
        mapping = self._getMapping(theClip, nodes)
        theClip.setMapping(mapping).apply(nodes, **kwargs)

class CreateClipWidget(QWidget, base_ui.CommonMixin):
    _defaultLocalePrefName = 'zooClipLibraryDefaultLocale'
    clipCreated = Signal(object)

    def __init__(self):
        super(CreateClipWidget, self).__init__()

        self._library = None
        self._clipPreset = None

        self._useAllNodesInRig = QCheckBox("Store clip using all rig controls")
        self._useAllNodesInRig.setChecked(True)

        self._saveWorldSpaceData = QCheckBox("Save world space data")
        self._saveWorldSpaceData.setChecked(True)

        localeLbl = QLabel("Clip locale")
        self._localeComboBox = LocaleComboBox()

        if cmds.optionVar(ex=self._defaultLocalePrefName):
            self._localeComboBox.setCurrentIndex(cmds.optionVar(q=self._defaultLocalePrefName))

        self._createPoseButton = QPushButton("Create Pose Clip...")
        self._createAnimButton = QPushButton("Create Anim Clip...")
        self._overwriteButton = QPushButton("Overwrite Selected Clip")

        self._overwriteButton.setEnabled(False)

        # hook up signals
        self._localeComboBox.currentIndexChanged.connect(self._saveLocalePref)
        self._createPoseButton.clicked.connect(self.on_createPose)
        self._createAnimButton.clicked.connect(self.on_createAnim)
        self._overwriteButton.clicked.connect(self.on_overwrite)

        # set some tool tips
        localeLbl.setToolTip(
            "Local clips are only available to you, while global clips "
            "can be seen by all. You can easily move a clip once it has "
            "been created if you change your mind")
        self._localeComboBox.setToolTip(localeLbl.toolTip())
        self._useAllNodesInRig.setToolTip(
            "When checked, all rig controls are stored in the clip. "
            "Otherwise only animation for the selected nodes is stored.")
        self._saveWorldSpaceData.setToolTip(
            "When checked world space data is written into the clip. "
            "For anim clips with many keys (eg: mocap) this can make "
            "clip generation quite slow. For these cases it can be "
            "helpful to turn off.")
        self._createPoseButton.setToolTip("Creates a pose clip")
        self._createAnimButton.setToolTip("Creates an animation clip")

        # layout the controls
        hlayout1 = QHBoxLayout()
        hlayout1.addWidget(self._useAllNodesInRig)
        hlayout1.addWidget(self._saveWorldSpaceData)

        hlayout2 = QHBoxLayout()
        hlayout2.addWidget(localeLbl)
        hlayout2.addWidget(self._localeComboBox, 1)

        hlayout3 = QHBoxLayout()
        hlayout3.addWidget(self._createPoseButton)
        hlayout3.addWidget(self._createAnimButton)

        mainLayout = QVBoxLayout()
        mainLayout.addWidget(QLabel("Create new clips using the following settings"))
        mainLayout.addStretch(1)
        mainLayout.addLayout(hlayout1)
        mainLayout.addLayout(hlayout2)
        mainLayout.addLayout(hlayout3)
        mainLayout.addWidget(self._overwriteButton)

        self.setLayout(mainLayout)

    def dockChanged(self):
        self.setSelectionChangeCB(self._updateButtonEnabled)

    def getNodes(self):
        return getNodes(self._useAllNodesInRig.isChecked())

    def _updateButtonEnabled(self):
        enabled = (self._library is not None) and bool(self.getNodes())
        self._createPoseButton.setEnabled(enabled)
        self._createAnimButton.setEnabled(enabled)

    def _saveLocalePref(self, idx):
        cmds.optionVar(iv=(self._defaultLocalePrefName, idx))

    def setLibrary(self, library):
        self._library = library
        self._updateButtonEnabled()

    def setClipPreset(self, clipPreset):
        self._clipPreset = clipPreset
        self._overwriteButton.setEnabled(clipPreset is not None)

    def __createClipPreset(self, presetCls):
        presetName, ret = QInputDialog.getText(self, "Create New Clip", "Clip name")
        if ret:
            nodes = self.getNodes()
            locale = self._localeComboBox.locale
            worldSpace = self._saveWorldSpaceData.isChecked()
            clipPreset = self._library.createClip(presetName, presetCls, locale)
            clipPreset.save(presetCls.CLS.Generate(nodes, worldSpace=worldSpace))

            self.clipCreated.emit(clipPreset)

    def on_createPose(self):
        self.__createClipPreset(clipLibrary.PoseClipPreset)

    def on_createAnim(self):
        self.__createClipPreset(clipLibrary.AnimClipPreset)

    def on_overwrite(self):
        if self._clipPreset is None:
            return

        nodes = self.getNodes()
        self._clipPreset.save(self._clipPreset.CLS.Generate(nodes))

class ManageClipWidget(QWidget):
    def __init__(self):
        super(ManageClipWidget, self).__init__()

        self._clipPreset = None

        self._nameLbl = QLabel("Clip Name")
        self._name = QLineEdit()
        self._rename = QPushButton("Rename")

        self._locationLbl = QLabel()

        self._libLbl = QLabel("Library")
        self._libraries = ClipLibraryComboBox()
        self._locales = LocaleComboBox()
        self._moveButton = QPushButton("Move Clip")
        self._deleteButton = QPushButton("Delete Clip")

        self._rename.clicked.connect(self.on_rename)
        self._moveButton.clicked.connect(self.on_move)
        self._deleteButton.clicked.connect(self.on_delete)

        hlayout1 = QHBoxLayout()
        hlayout1.addWidget(self._nameLbl)
        hlayout1.addWidget(self._name, 1)
        hlayout1.addWidget(self._rename)

        hlayout2 = QHBoxLayout()
        hlayout2.addWidget(self._libLbl)
        hlayout2.addWidget(self._libraries, 1)
        hlayout2.addWidget(self._locales)
        hlayout2.addWidget(self._moveButton)

        mainLayout = QVBoxLayout()
        mainLayout.addWidget(QLabel("Use the tools in this tab to manage your clips"))
        mainLayout.addStretch(1)
        mainLayout.addWidget(self._locationLbl)
        mainLayout.addLayout(hlayout1)
        mainLayout.addLayout(hlayout2)
        mainLayout.addWidget(self._deleteButton)
        self.setLayout(mainLayout)

    def setClipPreset(self, clipPreset):

        # remove the moved subscriber if there was a previous clip
        if self._clipPreset is not None:
            self._clipPreset.moved.remove(self._updateLocation)

        self._clipPreset = clipPreset

        if self._clipPreset is not None:
            self._clipPreset.moved.append(self._updateLocation)
            self._name.setText(clipPreset.name)
            self._updateLocation()

            # refresh the libraries
            self._libraries.populate()

            # select the appropriate combo box items
            self._libraries.selectLibrary(clipPreset.library)
            self._locales.setLocale(clipPreset.locale)

    def _updateLocation(self):
        self._locationLbl.setText(self._clipPreset._preset.path())

    def on_rename(self):
        if self._clipPreset is None:
            return

        newName = self._name.text()
        if self._clipPreset.name != newName:
            self._clipPreset.rename(newName)

    def on_move(self):
        if self._clipPreset is None:
            return

        clipPreset = self._clipPreset
        selectedLib = self._libraries.selectedLibrary
        selectedLocale = self._locales.locale

        # bail if the library/locale pair hasn't been changed
        if selectedLib == clipPreset.library and selectedLocale == clipPreset.locale:
            return

        self._clipPreset.move(clipPreset.name, selectedLib.name, selectedLocale)

    def on_delete(self):
        ret = QMessageBox.question(
            self,
            "Delete Clip?",
            "Do you really want to delete this clip?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )

        if ret == QMessageBox.Yes:
            self._clipPreset.delete()

class ClipLibrary(base_ui.MayaQWidget):
    def __init__(self):
        super(ClipLibrary, self).__init__()

        self._library = None

        self._libraries = ClipLibrariesWidget()
        self._libraries.librarySelected.connect(self.setLibrary)
        self._clipPresets = ClipPresetListWidget()
        self._applyClipWidget = ApplyClipWidget()
        self._createClipWidget = CreateClipWidget()
        self._manageClipWidget = ManageClipWidget()

        self._clipPresets._list.itemSelectionChanged.connect(self._clipSelected)
        self._clipPresets.listItemClipMoved.connect(self._listItemClipMoved)
        self._clipPresets.clipItemDoubleClicked.connect(lambda _: self._applyClipWidget.on_apply())
        self._createClipWidget.clipCreated.connect(self._clipCreated)

        tabs = QTabWidget()
        tabs.addTab(self._applyClipWidget, "Apply Clip")
        tabs.addTab(self._createClipWidget, "Create Clip")
        tabs.addTab(self._manageClipWidget, "Manage Clip")

        mainLayout = QVBoxLayout()
        mainLayout.addWidget(self._libraries)
        mainLayout.addWidget(self._clipPresets, 1)
        mainLayout.addWidget(tabs)

        self.setLayout(mainLayout)

        self._libraries.populate()

    def setLibrary(self, library):
        self._library = library
        self._createClipWidget.setLibrary(library)
        self.populate()

    def populate(self):
        self._clipPresets.clear()
        if self._library is None:
            return

        for clipPreset in self._library.iterClipPresets():
            self._clipPresets.append(clipPreset)

    def _clipSelected(self):
        clipPreset = self._clipPresets.item
        self._applyClipWidget.setClipPreset(clipPreset)
        self._createClipWidget.setClipPreset(clipPreset)
        self._manageClipWidget.setClipPreset(clipPreset)

    def _listItemClipMoved(self, listItem):
        listItem.setHidden(listItem._item.library != self._library)

    def _clipCreated(self, clipPreset):
        self._clipPresets.append(clipPreset)
        self._clipPresets.select([clipPreset])

#end
