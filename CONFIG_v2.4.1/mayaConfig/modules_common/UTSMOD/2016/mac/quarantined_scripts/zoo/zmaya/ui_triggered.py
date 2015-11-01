
from PySide.QtGui import *

from maya import cmds

from .. import misc
from .. import objListWidget
from .. import str_utils
from . import base_ui
from . import triggered
from . import apiExtensions

class TriggeredStateWidget(QPushButton):
    def __init__(self):
        super(TriggeredStateWidget, self).__init__()

        self.clicked.connect(triggered.ToggleState)

        self._stateChanged(triggered.State())
        triggered.eventManager.addEventCallback(triggered.EVT_LOAD_STATE_CHANGE, self._stateChanged)

    def _stateChanged(self, state):
        colName = 'green' if state else 'gray'
        self.setStyleSheet('background-color:%s;' % colName)

class TriggeredLabeledStateWidget(base_ui.MayaQWidget):
    def __init__(self):
        super(TriggeredLabeledStateWidget, self).__init__()

        self._stateWidget = TriggeredStateWidget()
        self._stateLabel = QLabel()

        hlayout = QHBoxLayout()
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.addWidget(self._stateWidget)
        hlayout.addSpacing(10)
        hlayout.addWidget(self._stateLabel, 1)

        self.setLayout(hlayout)

        self._stateChanged(triggered.State())
        triggered.eventManager.addEventCallback(triggered.EVT_LOAD_STATE_CHANGE, self._stateChanged)

    def _stateChanged(self, state):
        self._stateLabel.setText('Triggered Enabled' if state else 'Triggered Disabled')

class CommandEditWidget(base_ui.MayaQWidget):
    def __init__(self, showMenuCmds=False):
        super(CommandEditWidget, self).__init__()

        self._command = None
        self._suspend = False

        self._cmdTypeWidget = QComboBox()
        self._cmdStrWidget = QPlainTextEdit()
        self._previewCmdWidget = QCheckBox('Preview Command')

        self._cmdTypeWidget.currentIndexChanged.connect(self._changeCmdType)
        self._cmdStrWidget.textChanged.connect(self._cmdEdited)
        self._previewCmdWidget.stateChanged.connect(self._preview)

        vlayout = QVBoxLayout()
        vlayout.addWidget(self._cmdTypeWidget)
        vlayout.addWidget(self._cmdStrWidget, 1)
        vlayout.addWidget(self._previewCmdWidget)

        self.setLayout(vlayout)

        if showMenuCmds:
            self._cmdClasses = [cls for cls in misc.iterClsHierarchy(triggered.Command)
                                if issubclass(cls, triggered.MenuCommand)]
        else:
            self._cmdClasses = [cls for cls in misc.iterClsHierarchy(triggered.Command)
                                if not issubclass(cls, triggered.MenuCommand)]

        # Add command types to the drop down list
        for cls in self._cmdClasses:
            self._cmdTypeWidget.addItem(str_utils.camelCaseToNice(cls.__name__))

    def clear(self):
        self._command = None
        self._cmdTypeWidget.setEnabled(False)
        self._cmdStrWidget.clear()
        self._cmdStrWidget.setEnabled(False)
        self._previewCmdWidget.setChecked(False)

    def _updateUI(self):
        self._suspend = True

        try:
            cmd = self._command
            idx = self._cmdClasses.index(type(cmd))
            self._cmdTypeWidget.setEnabled(True)
            self._cmdTypeWidget.setCurrentIndex(idx)
            self._cmdStrWidget.setPlainText(cmd.cmdStr())

            isEditable = cmd.isEditable()
            isPreview  = self._previewCmdWidget.isChecked()
            isEnabled = isEditable and not isPreview

            self._previewCmdWidget.setEnabled(isEditable)
            self._cmdStrWidget.setEnabled(isEnabled)
        finally:
            self._suspend = False

    @property
    def command(self):
        return self._command

    @command.setter
    def command(self, cmd):
        self._command = cmd
        if cmd is None:
            self.clear()
        else:
            self._updateUI()

    def _changeCmdType(self, idx):
        if self._command is None or self._suspend:
            return

        cls = self._cmdClasses[idx]
        self._command.setTypeCls(cls)
        self._updateUI()

    def _cmdEdited(self):
        if self._command is None or self._suspend:
            return

        if self._cmdStrWidget.isReadOnly():
            return

        cmdStr = self._cmdStrWidget.toPlainText()
        cmd = self._command
        cmd.setCmdStr(cmdStr)

    def _preview(self, state):
        self._cmdStrWidget.setReadOnly(state)

        cmd = self._command
        self._suspend = True

        try:
            self._cmdStrWidget.setPlainText(cmd.cmdStr(state))
        finally:
            self._suspend = False

class ConnectsWidget(objListWidget.ObjListWidget):
    class Connect(object):
        def __init__(self, node, idx):
            self.node = node
            self.idx = idx

        def __str__(self):
            return '%d: %s' % (self.idx, self.node)

        def __eq__(self, other):
            return self.idx == other.idx and apiExtensions.cmpNodes(self.node, other.node)

        def __hash__(self):
            if cmds.objExists(self.node):
                return hash(self.idx) | hash(apiExtensions.asMObject(self.node))

            return 0

    def __init__(self):
        super(ConnectsWidget, self).__init__()

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._trigger = None

    @property
    def trigger(self):
        return self._trigger

    @trigger.setter
    def trigger(self, node):
        self._trigger = None
        if triggered.Trigger.IsA(node):
            self._trigger = triggered.Trigger(node)

        self._populate()

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.addAction('Add Selected Nodes', self._addConnects)
        menu.addSeparator()
        menu.addAction('Highlight Selected Nodes', self._highlightSelected)
        menu.addAction('Select Highlighted Nodes', self._selectHighlighted)
        menu.addSeparator()
        menu.addAction('Remove Highlighted Nodes', self._removeHighlight)
        menu.exec_(event.globalPos())

    def _populate(self):
        self.clear()
        if self.trigger is None:
            return

        for node, idx in self.trigger.iterConnects(False):
            self.append(self.Connect(node, idx))

    def _addConnects(self):
        if self.trigger is None:
            return

        nodes = cmds.ls(sl=True)
        for node in nodes:
            idx = self.trigger.connect(node)
            c = self.Connect(node, idx)

            # Don't add the self connect to the UI
            if c.idx == 0:
                continue

            # If the connect doesn't exist in the list already, add it now
            if c not in self:
                self.append(self.Connect(node, idx))

    def _highlightSelected(self):
        nodes = cmds.ls(sl=True)
        if not nodes:
            return

        self.clearSelection()
        itemsToSelect = [item for item in self.items() if item.node in nodes]
        self.select(itemsToSelect, False)

    def _selectHighlighted(self):
        cmds.select([item.node for item in self.selectedItems()])

    def _removeHighlight(self):
        selectedItems = self.selectedItems()
        for item in selectedItems:
            self.trigger.disconnect(item.idx)

        for item in selectedItems:
            self.remove(item)

class MenuListWidget(objListWidget.ObjListWidget):
    def __init__(self):
        super(MenuListWidget, self).__init__(self._menuCmdToStr)

        self.setSelectionMode(QListWidget.ExtendedSelection)
        self._trigger = None

    @property
    def trigger(self):
        return self._trigger

    @trigger.setter
    def trigger(self, trigger):
        if isinstance(trigger, triggered.Trigger):
            self._trigger = trigger
        else:
            self._trigger = None

        self.populate()

    def _menuCmdToStr(self, menu):
        return menu.menuName()

    def populate(self):
        self.clear()
        if self._trigger is None:
            return

        for idx, menu in self._trigger.iterMenus():
            self.append(menu)

class MenuTriggerWidget(base_ui.MayaQWidget):
    def __init__(self):
        super(MenuTriggerWidget, self).__init__()

        self._lblWidget = QLabel('Triggered Menus')
        self._exclusiveWidget = QCheckBox('Only Display Triggered Menus')
        self._menusWidget = MenuListWidget()
        self._menuCommandWidget = CommandEditWidget(True)

        self._exclusiveWidget.stateChanged.connect(self._setKillMenu)
        self._menusWidget.itemSelectionChanged.connect(self._menuSelected)

        vlayout = QVBoxLayout()
        vlayout.addWidget(self._lblWidget)
        vlayout.addWidget(self._exclusiveWidget)
        vlayout.addWidget(self._menusWidget)
        vlayout.addWidget(self._menuCommandWidget, 1)

        self.setLayout(vlayout)

    @property
    def trigger(self):
        return self._menusWidget.trigger

    @trigger.setter
    def trigger(self, trigger):
        self._menusWidget.trigger = trigger

        # If we have a trigger, set the default kill state
        if trigger:
            self._exclusiveWidget.setChecked(trigger.killState())

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.addAction('Create Menu Item', self._addMenu)
        menu.addSeparator()
        menu.addAction('Rename Highlighted Menu Item', self._renameMenu)
        menu.addSeparator()
        menu.addAction('Remove Highlighted Menu Items', self._removeMenu)
        menu.exec_(event.globalPos())

    def _setKillMenu(self):
        if self.trigger:
            self.trigger.setKillState(self._exclusiveWidget.isChecked())

    def _menuSelected(self):
        sel = self._menusWidget.selectedItems()
        if sel:
            self._menuCommandWidget.command = sel[0]

    def _getMenuName(self, defaultName):
        buts = OK, CANCEL = 'Ok', 'Cancel'
        ret = cmds.promptDialog(
            t='Enter Menu Name', m='Enter a name for the menu',
            tx=defaultName, b=buts, db=OK)

        if ret == OK:
            return cmds.promptDialog(q=True, tx=True)

    def _performRename(self, menu):
        menuName = self._getMenuName(menu.menuName())
        if menuName != menu.menuName():
                menu.setMenuName(cmds.promptDialog(q=True, tx=True))
                self._menusWidget.updateItems()

    def _addMenu(self):
        menuName = self._getMenuName('<unnamed menu item>')
        if menuName:
            menu = self.trigger.createMenu(menuName)
            self._menusWidget.append(menu)
            self._menusWidget.select([menu])

    def _renameMenu(self):
        for menu in self._menusWidget.selectedItems():
            self._performRename(menu)

            # Always return here, rename only works on a single item
            return

    def _removeMenu(self):
        for menu in self._menusWidget.selectedItems():
            self.trigger.deleteMenu(menu)
            self._menusWidget.remove(menu)

class TriggerListWidget(objListWidget.ObjListWidget):
    def __init__(self):
        super(TriggerListWidget, self).__init__()

    def populate(self):
        if self._node is None:
            return

        for trigger in triggered.Trigger.Iter():
            self.append(trigger)

class Triggered(base_ui.MayaQWidget):
    def __init__(self):
        super(Triggered, self).__init__()

        self._stateWidget = TriggeredLabeledStateWidget()
        self._autoLoadWidget = QCheckBox('Auto Load')
        self._loadWidget = QPushButton('Load Trigger')
        self._createWidget = QPushButton('Create Trigger')

        self._triggerNameWidget = QLabel()

        self._deleteWidget = QPushButton('Remove Triggered Data')

        self._connectsWidget = ConnectsWidget()
        self._tabsWidget = QTabWidget()

        self._selCommandWidget = CommandEditWidget()
        self._menuCommandsWidget = MenuTriggerWidget()

        self._tabsWidget.addTab(self._selCommandWidget, 'Selection Command')
        self._tabsWidget.addTab(self._menuCommandsWidget, 'Menu Commands')
        self._tabsWidget.addTab(self._connectsWidget, 'Connects')

        # Hook up signals
        self._autoLoadWidget.stateChanged.connect(self._loadSelectedTrigger)
        self._loadWidget.clicked.connect(self._loadSelectedTrigger)
        self._createWidget.clicked.connect(self.createTriggerFromSelection)
        self._deleteWidget.clicked.connect(self.deleteTrigger)

        hlayout = QHBoxLayout()
        hlayout.addWidget(self._tabsWidget, 1)

        topHLayout = QHBoxLayout()
        topHLayout.addWidget(self._stateWidget)
        topHLayout.addWidget(self._autoLoadWidget)
        topHLayout.addWidget(self._loadWidget, 1)
        topHLayout.addWidget(self._createWidget, 1)

        vlayout = QVBoxLayout()
        vlayout.addLayout(topHLayout)
        vlayout.addWidget(self._triggerNameWidget)
        vlayout.addLayout(hlayout, 1)
        vlayout.addWidget(self._deleteWidget)

        self.setLayout(vlayout)

        self.setSelectionChangeCB(self._selectionChanged)

        self.trigger = None
        self._loadSelectedTrigger()

    @property
    def trigger(self):
        return self._connectsWidget.trigger

    @trigger.setter
    def trigger(self, node):
        if triggered.Trigger.IsA(node):
            trigger = triggered.Trigger(node)

            self._triggerNameWidget.setText('Editing Trigger: %s' % trigger._node)
            self._selCommandWidget.command = trigger.selectionCmd()
            self._menuCommandsWidget.trigger = trigger
            self._connectsWidget.trigger = trigger
            self._tabsWidget.setEnabled(True)
            self._deleteWidget.setEnabled(True)
        else:
            self._triggerNameWidget.setText('<no trigger loaded>')
            self._tabsWidget.setEnabled(False)
            self._deleteWidget.setEnabled(False)

    def createTriggerFromSelection(self):
        nodes = cmds.ls(sl=True)
        if nodes:
            node = nodes[0]
            if not triggered.Trigger.IsA(node):
                triggered.Trigger.Create(node)

            self.trigger = node

    def deleteTrigger(self):
        trigger = self.trigger
        if trigger:
            self.trigger = None
            trigger.delete()

    def _loadSelectedTrigger(self):
        sel = cmds.ls(sl=True)
        if sel:
            self.trigger = sel[0]

    def _selectionChanged(self):
        sel = cmds.ls(sl=True)

        # If no trigger is loaded, always auto load
        if self.trigger is None:
            self._loadSelectedTrigger()
        elif self._autoLoadWidget.isChecked():
            self._loadSelectedTrigger()

        hasSel = bool(sel)
        self._createWidget.setEnabled(hasSel)
        self._loadWidget.setEnabled(hasSel)
        self._createWidget.setEnabled(hasSel)

#end
