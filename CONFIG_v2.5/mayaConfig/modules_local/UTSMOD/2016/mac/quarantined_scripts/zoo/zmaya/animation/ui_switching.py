
import logging

from PySide.QtGui import *

from maya import cmds

from ... import misc
from .. import maya_decorators
from ..base_ui import MayaQWidget
from .. import constants

from ..skeletonBuilder import spaceSwitching, baseRigPart

import switching

logger = logging.getLogger(__name__)

class BaseSwitchingWidget(MayaQWidget):
    SWITCH_BUTTON_LBL = '<no label set>'
    OPTIONS_LBL = '<no label set>'

    def __init__(self):
        super(BaseSwitchingWidget, self).__init__()

        self.options = QComboBox()

        self.performSwitch = QPushButton(self.SWITCH_BUTTON_LBL)
        self.performSwitch.clicked.connect(self.switch)

        hlayout = QHBoxLayout()
        hlayout.addWidget(QLabel(self.OPTIONS_LBL))
        hlayout.addWidget(self.options, 1)

        layout = QVBoxLayout()
        layout.addLayout(hlayout)
        layout.addWidget(self.performSwitch)
        self.setLayout(layout)

        self.setSelectionChangeCB(self.updateWidgets)
        self.updateWidgets()

class SpaceSwitchingWidget(BaseSwitchingWidget):
    SWITCH_BUTTON_LBL = 'Perform Space Switch'
    OPTIONS_LBL = 'Available Parents'

    def updateWidgets(self):

        # clear any existing parents
        self.options.clear()

        enableUI = False

        # now populate the UI based on the selection
        sel = cmds.ls(sl=True)
        if sel:
            spaceNames = []

            # so we have a selection, but do we have any space switching nodes selected?
            for node in sel:
                if spaceSwitching.SpaceSwitchNode.IsA(node):

                    # extend the list of names
                    spaceNames += spaceSwitching.SpaceSwitchNode(node).names

            # remove any duplicate names
            spaceNames = misc.removeDupes(spaceNames)

            if spaceNames:
                enableUI = True

                # add the space names to the list
                for name in spaceNames:
                    self.options.addItem(name)

        self.options.setEnabled(enableUI)
        self.performSwitch.setEnabled(enableUI)

    def switch(self):
        selectedSpace = self.options.currentText()

        selectedNodes = cmds.ls(sl=True)

        # get a list of nodes we're doing the space switch on.  It may be that not all selected nodes
        # have the selected space
        parentIdxNodeMap = {}
        for node in selectedNodes:
            spaces, names = spaceSwitching.getSpaceTargetsNames(node)
            if selectedSpace in names:
                parentIdx = names.index(selectedSpace)
                parentIdxNodeMap.setdefault(parentIdx, [])
                parentIdxNodeMap[parentIdx].append(node)

        with maya_decorators.UndoBlockContext():
            for idx, nodes in parentIdxNodeMap.iteritems():
                switching.switchParentForAnimatedControls(nodes, idx)

class IkFkSwitchingWidget(BaseSwitchingWidget):
    SWITCH_BUTTON_LBL = 'Switch Now'
    OPTIONS_LBL = 'Switch to..'

    SWITCH_METHODS = (('FK', switching.switchToFkForAnimatedControl),
                      ('IK', switching.switchToIkForAnimatedControl),
                      )

    SWITCH_METHOD_DICT = dict(SWITCH_METHODS)

    def __init__(self):
        super(IkFkSwitchingWidget, self).__init__()

        for methodLabelStr, method in self.SWITCH_METHODS:
            self.options.addItem(methodLabelStr)

        self.updateWidgets()

    def updateWidgets(self):
        enableUI = False

        # have we got a selection?
        sel = cmds.ls(sl=True)
        if sel:

            # are any of these selected nodes parts?
            for node in sel:
                try:
                    part = baseRigPart.RigPart.InitFromItem(node)
                except baseRigPart.RigPartError:
                    continue

                # make sure the part supports ik fk switching (not all parts do!)
                if hasattr(part, 'switchToFk') and hasattr(part, 'switchToIk'):
                    enableUI = True

                    # we only need one...
                    break

        self.options.setEnabled(enableUI)
        self.performSwitch.setEnabled(enableUI)

    def switch(self):
        selectedLbl = self.options.currentText()
        switchMethod = self.SWITCH_METHOD_DICT.get(selectedLbl)
        if not callable(switchMethod):
            logger.error("No valid selection in the options box!")
            return

        with maya_decorators.UndoBlockContext():
            for node in cmds.ls(sl=True):
                switchMethod(node)

class RooSwitchingWidget(BaseSwitchingWidget):
    SWITCH_BUTTON_LBL = 'Switch Now'
    OPTIONS_LBL = 'Switch order to..'

    def __init__(self):
        super(RooSwitchingWidget, self).__init__()

        for rooStr in constants.MAYA_ROTATE_ORDER_STRS:
            self.options.addItem(rooStr)

        self.updateWidgets()

    def updateWidgets(self):
        nodes = switching.onlyTransforms(cmds.ls(sl=True))
        enableUI = bool(nodes)

        self.options.setEnabled(enableUI)
        self.performSwitch.setEnabled(enableUI)

        # Select a sensible default
        if nodes:
            roIdx = cmds.getAttr('%s.ro' % nodes[0])
            self.options.setCurrentIndex(roIdx)

    def switch(self):
        selectedRoo = self.options.currentText()
        switching.switchRooForAnimatedControls(cmds.ls(sl=True), selectedRoo)

class SwitchingTool(MayaQWidget):
    def __init__(self):
        super(SwitchingTool, self).__init__()

        layout = QVBoxLayout()
        layout.addWidget(SpaceSwitchingWidget())
        layout.addWidget(IkFkSwitchingWidget())
        layout.addWidget(RooSwitchingWidget())
        layout.addStretch()
        self.setLayout(layout)

#end
