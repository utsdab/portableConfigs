
from PySide.QtCore import Qt, Signal
from PySide.QtGui import *

from maya import cmds

from ... import objListWidget
from ... import ui_utils
from ... import list_widget
from .. import base_ui
from .. import apiExtensions
from .. import maya_decorators

import spaceSwitching

WORLD_NAME = 'spaceSwitchingWorld'

class NodeChooserWidget(base_ui.MayaQWidget):
    nodeLoaded = Signal(object)

    def __init__(self):
        super(NodeChooserWidget, self).__init__()

        self.setMinimumWidth(300)

        self._node = None

        self._buttonLoadNode = QPushButton('Set Selected->')
        self._lineEditNode = list_widget.ButtonLineEdit('remove.png')

        self._lineEditNode.setPlaceholderText('press button to set node...')

        self._buttonLoadNode.clicked.connect(self._loadSelected)
        self._lineEditNode.clicked.connect(self._clear)
        self._lineEditNode.editingFinished.connect(self._renameNode)

        self.setRenameCB(self._updateText)
        self.setSelectionChangeCB(self._updateState)
        self.setNodeDeleteCB(self._nodeDeleted)

        # update UI state
        self._updateState()

        hlayout = ui_utils.makeHLayout(0)
        hlayout.addWidget(self._buttonLoadNode)
        hlayout.addSpacing(5)
        hlayout.addWidget(self._lineEditNode, 1)

        self.setLayout(hlayout)

    def _updateState(self):
        enabled = bool(cmds.ls(sl=True))
        self._buttonLoadNode.setEnabled(enabled)

        if self._node is None:
            self._lineEditNode.setEnabled(False)
            self._lineEditNode.setText("")
        else:
            self._lineEditNode.setEnabled(True)
            self._lineEditNode.setText(str(self._node))

            nodeReadonly = bool(cmds.ls(self._node, readOnly=True))
            self._lineEditNode.setReadOnly(nodeReadonly)

    def _nodeDeleted(self, node, clientData):
        if self._node is None:
            return

        # if the node that was deleted was this node, set the node to None
        if apiExtensions.cmpNodes(node, self._node):
            self.setNode(None)

    def _updateText(self):
        if self._node is None:
            return

        # make sure the node still exists - it may have been deleted...
        if cmds.objExists(self._node):
            self._lineEditNode.setText(str(self._node))

    def _clear(self):
        self.setNode(None)

    def _loadSelected(self):
        sel = cmds.ls(sl=True) or []
        if sel:
            self.setNode(sel[0])

    def _renameNode(self):
        if self._node is None:
            return

        # check to see if the node exists before renaming
        if cmds.objExists(self._node):
            if not cmds.ls(self._node, readOnly=True):
                cmds.rename(self._node, self._lineEditNode.text())

    def getNode(self):
        return self._node

    def setNode(self, node):
        if node is not None:

            # store as an MObject - this way we don't lose the ref when a
            # rename is undone...
            node = apiExtensions.asMObject(node)

        self._node = node

        # update the UI state
        self._updateState()

        # emit the signal
        self.nodeLoaded.emit(node)

    def setButtonText(self, text):
        self._buttonLoadNode.setText(text)

    def setButtonWidth(self, width):
        self._buttonLoadNode.setMinimumWidth(width)

class SpaceSwitching(base_ui.MayaQWidget):

    # stores node/name pairs for storing in the list view
    class SpaceItem(object):
        def __init__(self, node, name):
            self.node = node
            self.name = name

        def __str__(self):
            return '%s: %s' % (self.node, self.name)

        def __eq__(self, other):
            return apiExtensions.cmpNodes(self.node, other.node)

    def __init__(self):
        super(SpaceSwitching, self).__init__()

        self._chooserControl = NodeChooserWidget()
        self._chooserSpace = NodeChooserWidget()
        self._buttonBuild = QPushButton("Re/Build Space Switch")
        self._buttonDelete = QPushButton("Delete Space Switch Data")

        # set control UI
        self._chooserControl.setButtonText("Set Control Node ->")
        self._chooserControl.setButtonWidth(120)
        self._chooserControl.setToolTip("The control on which the space switching attribute and right click menu will be added")

        # set space UI
        self._chooserSpace.setButtonText("Node to Constrain ->")
        self._chooserSpace.setButtonWidth(120)
        self._chooserSpace.setToolTip("The transform that actually gets constrained. Usually this is a group above the control, but it doesn't have to be")

        # space list UI
        self._listSpaces = objListWidget.ObjListWidget()
        self._listSpaces.mouseDoubleClickEvent = self._spaceDoubleClicked
        self._listSpaces.contextMenuEvent = self._buildListSpacesCtxMenu

        self._chooserControl.nodeLoaded.connect(self._updateControl)
        self._chooserSpace.nodeLoaded.connect(self._updateSpace)
        self._buttonBuild.clicked.connect(self._build)
        self._buttonDelete.clicked.connect(self._delete)

        vlayout = QVBoxLayout()
        vlayout.addWidget(self._chooserControl)
        vlayout.addWidget(self._chooserSpace)
        vlayout.addWidget(self._listSpaces, 1)
        vlayout.addWidget(self._buttonBuild)
        vlayout.addWidget(self._buttonDelete)

        self.setLayout(vlayout)

        self.setSceneChangeCB(self.clear)

        # if there is a selected node, load it as the control
        sel = cmds.ls(sl=True)
        if sel:
            self._chooserControl.setNode(sel[0])

    def _updateState(self):
        control = self._chooserControl.getNode()
        space = self._chooserSpace.getNode()
        enabled = control is not None and space is not None

        self._buttonBuild.setEnabled(enabled)

    def _updateControl(self, node):
        if spaceSwitching.SpaceSwitchNode.IsA(node):
            spaceSwitch = spaceSwitching.SpaceSwitchNode(node)
            self._chooserSpace.setNode(spaceSwitch.space)
            self._setSpacesFrom(spaceSwitch)
        else:
            parent = spaceSwitching.findCandidateSpace(node)
            if parent:
                self._chooserSpace.setNode(parent)

    def _updateSpace(self, node):
        self._updateState()

    def _setSpacesFrom(self, spaceSwitch):

        # clear all items
        self._listSpaces.clear()

        for node, name in zip(*spaceSwitch.getSpaceData()):
            self.addSpace(node, name)

    def _spaceDoubleClicked(self, event):
        highlighted = self._listSpaces.selectedItems()
        if highlighted:
            cmds.select(highlighted[0].node)

    def _buildListSpacesCtxMenu(self, event):
        menu = QMenu()

        sel = cmds.ls(sl=True)
        hasSel = bool(sel)

        act = menu.addAction('Add "World" parent', self.addWorld)
        act.setEnabled(not self.isWorldAdded())

        act = menu.addAction('Add selected as parent', self._addSelectedAsSpaces)
        act.setEnabled(hasSel)

        menu.addSeparator()

        highlighted = self._listSpaces.selectedItems()
        hasHighlighted = bool(highlighted)

        act = menu.addAction('Rename', self._rename)
        act.setEnabled(hasHighlighted)

        menu.addSeparator()

        act = menu.addAction('Remove highlighted parent', self._removeHighlighted)
        act.setEnabled(hasHighlighted)

        menu.exec_(event.globalPos())

    def _addSelectedAsSpaces(self):
        sel = cmds.ls(sl=True)
        if not sel:
            return

        # if there are no existing items and the world hasn't been added already, add
        # it now
        if not self._listSpaces.items():
            if not self.isWorldAdded():
                self.addWorld()

        # add all the selected nodes as spaces
        for s in sel:
            self.addSpace(s, s)

    def _rename(self):
        highlighted = self._listSpaces.selectedItems()
        if not highlighted:
            return

        item = highlighted[0]
        spaceName, ret = QInputDialog.getText(
            self,
            "Set Space Display Name",
            "Space display name",
            text=item.name)

        if ret:
            item.name = spaceName
            self._listSpaces.updateItems()

    def _removeHighlighted(self):
        highlighted = self._listSpaces.selectedItems()
        if highlighted:
            self._listSpaces.remove(highlighted[0])

    @maya_decorators.d_undoBlock
    def _build(self):

        # get the control from the UI
        control = self._chooserControl.getNode()

        # if the control is already has space switching, try to figure out what
        # has been added/removed
        if spaceSwitching.SpaceSwitchNode.IsA(control):
            spaceSwitch = spaceSwitching.SpaceSwitchNode(control)

            # has the space changed?
            space = spaceSwitch.space
            if not apiExtensions.cmpNodes(space, self._chooserSpace.getNode()):

                # this is recoverable, but for now discourage
                raise Exception("The space has changed")

            # get data from the UI and from the existing space switch
            nodesFromUI = [i.node for i in self._listSpaces.items()]
            namesFromUI = [i.name for i in self._listSpaces.items()]
            nodesFromExisting = spaceSwitch.spaces
            count = max(len(nodesFromUI), len(nodesFromExisting))
            for n in range(count):

                # in this case we have a new item from the UI
                if n >= len(nodesFromExisting):
                    print 'adding new node from UI', nodesFromUI[n]
                    spaceSwitching.add(control, nodesFromUI[n], namesFromUI[n], space)

                # in this case we have an existing item that needs to be removed
                elif n >= len(nodesFromUI):
                    print 'removing existing space', nodesFromExisting[n]
                    spaceSwitching.remove(control, str(nodesFromUI[n]))

                # in this case we need to check the equivalence of existing nodes
                else:

                    # if the nodes match, there's nothing to do...
                    if apiExtensions.cmpNodes(nodesFromExisting[n], nodesFromUI[n]):
                        print 'existing node matches node from UI', nodesFromExisting[n]
                        continue

                    # however, if the nodes are different, then we need to remove all
                    # consequent nodes and then add the remainder of the new node/name
                    # pairs from the UI
                    else:
                        raise NotImplementedError("This case isn't handled currently...")

        else:
            # otherwise rebuild the space switching based on the data in the UI
            spaceSwitching.build(
                control,

                # get the space nodes from the UI
                [space.node for space in self._listSpaces.items()],

                # get the space names from the UI
                [space.name for space in self._listSpaces.items()],

                # get the space transform from the UI
                self._chooserSpace.getNode())

    def _delete(self):
        node = self._chooserControl.getNode()
        if spaceSwitching.SpaceSwitchNode.IsA(node):
            spaceSwitching.SpaceSwitchNode(node).delete()

        self.clear()

    def clear(self):
        self._chooserControl.setNode(None)
        self._chooserSpace.setNode(None)
        self._listSpaces.clear()

    def isWorldAdded(self):
        for space in self._listSpaces.iteritems():
            if space.node == WORLD_NAME:
                return True

        return False

    def addWorld(self):
        if cmds.objExists(WORLD_NAME) is False:
            cmds.spaceLocator(n=WORLD_NAME)

        # check to see whether the world has already been added
        if self.isWorldAdded():
            return

        self.addSpace(WORLD_NAME, "The World")

        return WORLD_NAME

    def addSpace(self, node, name):
        space = self.SpaceItem(node, name)
        self._listSpaces.append(space)

#end
