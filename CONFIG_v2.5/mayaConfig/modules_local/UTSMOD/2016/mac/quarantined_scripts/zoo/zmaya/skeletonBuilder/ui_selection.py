
from PySide.QtGui import *

from .. import base_ui

import tools

class SelectionTool(base_ui.MayaQWidget):
    def __init__(self):
        super(SelectionTool, self).__init__()

        buttonSelectAll = QPushButton("Select ALL Rig Controls")
        buttonSelectSub = QPushButton("Select Rig Part Controls")
        buttonSelectSubChild = QPushButton("Select Rig and Child Rig Part Controls")
        buttonSelectOpposite = QPushButton("Mirror Selection")

        buttonSelectAll.clicked.connect(tools.selectAllRigControlsFromSelection)
        buttonSelectSub.clicked.connect(tools.selectSelectedParts)
        buttonSelectSubChild.clicked.connect(tools.selectThisAndChild)
        buttonSelectOpposite.clicked.connect(tools.selectOppositeControl)

        mainLayout = QVBoxLayout()
        mainLayout.addWidget(buttonSelectAll)
        mainLayout.addWidget(buttonSelectSub)
        mainLayout.addWidget(buttonSelectSubChild)
        mainLayout.addWidget(buttonSelectOpposite)
        mainLayout.addStretch(1)

        self.setLayout(mainLayout)

#end
