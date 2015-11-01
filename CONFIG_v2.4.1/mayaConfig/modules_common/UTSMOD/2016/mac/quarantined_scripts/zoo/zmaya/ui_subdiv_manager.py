
from PySide.QtGui import *
from PySide.QtCore import Qt, QRegExp

from maya import cmds

from base_ui import showWidget, MayaQWidget

import subdiv_manager

class IntEdit(QLineEdit):
    def __init__(self, *args):
        super(IntEdit, self).__init__(*args)

        self.setValidator(QIntValidator())

    def value(self):
        return int(self.text())

    def setValue(self, value):
        self.setText(str(value))

class SubdivManager(MayaQWidget):
    def __init__(self):
        super(SubdivManager, self).__init__()

        self._subdivAmount = IntEdit()
        self._subdivAmount.textEdited.connect(self.saveAmount)

        self._subdivAmountReason = QLabel()

        flayout = QFormLayout()
        flayout.addRow('Subdiv amount:', self._subdivAmount)
        flayout.addRow('Amount source:', self._subdivAmountReason)

        button1 = QPushButton('Subdiv On')
        button1.clicked.connect(self.subdivOn)

        button2 = QPushButton('Subdiv Off')
        button2.clicked.connect(self.subdivOff)

        layout = QVBoxLayout()#self.makeVLayout(5)
        layout.addLayout(flayout)
        layout.addWidget(self._subdivAmountReason)
        layout.addWidget(button1)
        layout.addWidget(button2)
        layout.addStretch()

        self.setLayout(layout)

        self.setSelectionChangeCB(self.on_selectionChange)
        self.on_selectionChange()

    def focusOutEvent(self, event):
        self.saveAmount()

    def subdivOn(self):
        subdiv_manager.setSubdivState(True)

    def subdivOff(self):
        subdiv_manager.setSubdivState(False)

    def udpateAmount(self):
        sel = cmds.ls(sl=True)
        if sel:
            amount = subdiv_manager.getSubdivAmountForNode(sel[0])
            self._subdivAmount.setValue(amount)
            self._subdivAmountReason.setText(amount.reason)

        else:
            self._subdivAmount.clear()
            self._subdivAmountReason.clear()

    def on_selectionChange(self):
        self.udpateAmount()

    def saveAmount(self, *a):
        sel = cmds.ls(sl=True) or []
        newAmount = self._subdivAmount.value()
        for node in sel:
            subdiv_manager.setSubdivLevelForNode(node, newAmount)

        self.udpateAmount()

#end
