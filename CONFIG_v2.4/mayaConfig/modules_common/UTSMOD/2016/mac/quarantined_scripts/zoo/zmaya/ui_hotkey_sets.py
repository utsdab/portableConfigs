
import logging

from PySide.QtGui import *

from maya import cmds

from .. import file_selection_widget
from . import base_ui
from . import hotkey_sets
from . import marking_menu

logger = logging.getLogger(__name__)

class HotkeySets(base_ui.MayaQWidget):
    NO_PRESET_STR = '<no preset set>'
    CURRENT_PRESET_TEMPLATE = 'The current hotkey set is: %s'

    def __init__(self):
        super(HotkeySets, self).__init__()

        self.currentPresetWidget = QLabel(self.NO_PRESET_STR)
        self.listWidget = QListWidget()
        self.replaceCheckWidget = QCheckBox('Replace hotkeys')
        self.loadButtonWidget = QPushButton('Load Selected Hotkey Set')
        self.saveButtonWidget = QPushButton('Save Current Hotkeys')
        self.resetButtonWidget = QPushButton('Reset Hotkeys To Default')
        self.loadFromFileLabelWidget = QLabel('Use the browser to load a file sent to you by someone else')
        self.loadFromFileBrowseWidget = file_selection_widget.FileSelectionWidget()
        self.loadFromFileButtonWidget = QPushButton('Load From File')

        self.listWidget.contextMenuEvent = self._listWidgetContextMenuEvent
        self.replaceCheckWidget.setChecked(True)

        self.listWidget.itemDoubleClicked.connect(self._loadItem)
        self.saveButtonWidget.clicked.connect(self._save)
        self.resetButtonWidget.clicked.connect(self._reset)
        self.loadButtonWidget.clicked.connect(self._load)
        self.loadFromFileButtonWidget.clicked.connect(self._loadFile)

        layout = QVBoxLayout()
        layout.addWidget(self.currentPresetWidget)
        layout.addWidget(self.listWidget, 1)
        layout.addWidget(self.replaceCheckWidget)
        layout.addWidget(self.loadButtonWidget)
        layout.addWidget(self.saveButtonWidget)
        layout.addWidget(self.resetButtonWidget)
        layout.addWidget(base_ui.createSeparator())
        layout.addWidget(self.loadFromFileLabelWidget)
        layout.addWidget(self.loadFromFileBrowseWidget)
        layout.addWidget(self.loadFromFileButtonWidget)

        self.setLayout(layout)

        self.populate()

    def updateCurrentSetName(self):

        # Set the current hotkey set name
        currentSetName = hotkey_sets.getCurrentHotkeySetName()
        if currentSetName:
            self.currentPresetWidget.setText(
                self.CURRENT_PRESET_TEMPLATE % currentSetName)

            for row in range(self.listWidget.count()):
                item = self.listWidget.item(row)
                item.setSelected(item.text() == currentSetName)
        else:
            self.currentPresetWidget.setText(self.NO_PRESET_STR)

    def populate(self):
        self.listWidget.clear()
        for preset in hotkey_sets.HotkeySet.Manager.iterPresets():
            self.listWidget.addItem(preset.name)

        if self.listWidget.count():
            self.listWidget.item(0).setSelected(True)

        self.updateCurrentSetName()

    def _listWidgetContextMenuEvent(self, event):
        menu = QMenu()
        menu.addAction('Explore to File')
        menu.addAction('Delete')
        menu.exec_(event.globalPos())

    def _reset(self):
        ret = QMessageBox.question(
            self,
            'Are You Sure?',
            'Are you sure you want to reset all hotkeys?',
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel)

        if ret == QMessageBox.Yes:
            hotkey_sets.resetToDefault()
            logger.info('Hotkeys have been reset to their defaults')

    def _save(self):
        defaultName = ''
        for item in self.listWidget.selectedItems():
            defaultName = item.text()
            break

        presetName, ret = QInputDialog.getText(
            self,
            'Enter Set Name',
            'Please enter a name for this hotkey set',
            text=defaultName)

        if ret:
            preset = hotkey_sets.HotkeySet.Manager.getPreset(presetName)
            hotkey_sets.saveToPreset(preset)
            self.populate()

    def _loadItem(self, item):
        replace = self.replaceCheckWidget.isChecked()
        presetName = item.text()
        preset = hotkey_sets.HotkeySet.Manager.getPreset(presetName)
        hotkey_sets.loadFromPreset(preset, replace)
        self.updateCurrentSetName()

        logger.info('Loaded the hotkey set %s from: %s' % (presetName, preset.path()))

    def _load(self):
        for item in self.listWidget.selectedItems():
            self._loadItem(item)
            return

    def _loadFile(self):
        filepath = self.loadFromFileBrowseWidget.path
        if filepath.exists():
            if filepath.hasExtension(hotkey_sets.HotkeySet.Manager.extension):

                # Copy the file to the presets directory
                preset = hotkey_sets.HotkeySet.Manager.getPreset(filepath.name())
                filepath.copy(preset.path())

                # Try to load the preset
                try:
                    hotkey_sets.loadFromPreset(preset)
                    self.populate()
                except:
                    preset.path().delete()

class HotkeyMarkingMenu(marking_menu.MarkingMenu):
    def show(self, menu, menuParent):
        def setHotkeySetFactory(preset):
            def _(*a):
                hotkey_sets.loadFromPreset(preset)

            return _

        currentSetName = hotkey_sets.getCurrentHotkeySetName()
        for preset in hotkey_sets.HotkeySet.Manager.iterPresets():
            cmds.menuItem(l=preset.name, c=setHotkeySetFactory(preset), cb=currentSetName == preset.name)

        cmds.menuItem(divider=True)
        cmds.menuItem(l='Open Hotkey Sets Tool', c=lambda _: HotkeySets.Show())

        cmds.menuItem(divider=True)
        cmds.menuItem(l='Reset to Default Hotkeys', c=lambda _: hotkey_sets.resetToDefault())

#end
