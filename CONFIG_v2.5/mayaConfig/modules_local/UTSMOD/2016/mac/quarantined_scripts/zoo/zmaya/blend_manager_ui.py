
from PySide.QtGui import *

from base_ui import showWidget, MayaQWidget

from maya import cmds

class ManagerWidget(MayaQWidget):
    def __init__(self):
        QWidget.__init__(self)

        self.button = QPushButton('delete history')
        self.button.clicked.connect(self.onDeleteHistory)

        self.onSelectionChange()
        self.setSelectionChangeCB(self.onSelectionChange)
        layout = QHBoxLayout()
        layout.addWidget(self.button)
        self.setLayout(layout)

    def onSelectionChange(self):
        sel = cmds.ls(sl=True)
        self.button.setEnabled(bool(sel))

    def onDeleteHistory(self):
        sel = cmds.ls(sl=True, type='transform') or []
        for s in sel:
            node = BlendShapeNode.FromTransform(s)
            node.deleteHistory()

BlendShapeManager = ManagerWidget.Show

#end
