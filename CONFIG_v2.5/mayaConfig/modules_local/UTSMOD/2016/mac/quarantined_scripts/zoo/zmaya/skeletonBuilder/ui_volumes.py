
from PySide.QtGui import *

from maya import cmds

from .. import base_ui
from . import volumes

class VolumesTool(base_ui.MayaQWidget):
    _itemDelegates = (
        volumes.cylinderCreationDelegate,
        volumes.cubeCreationDelegate,
        volumes.sphereCreationDelegate,
    )

    _itemDelegateNames = (
        'Cylinder',
        'Cube',
        'Sphere',
    )

    def __init__(self):
        super(VolumesTool, self).__init__()

        self.comboVolumeType = QComboBox()

        buttonAddFit = QPushButton("Add and fit volume to selected")
        buttonAdd = QPushButton("Add volume to selected")
        buttonFit = QPushButton("Fit volumes")
        buttonSkin = QPushButton("Create skinning from volumes")
        buttonRemove = QPushButton("Remove volume from selected")

        buttonAddFit.clicked.connect(self.createAndFitVolumes)
        buttonAdd.clicked.connect(self.createVolumes)
        buttonFit.clicked.connect(volumes.shrinkWrapSelection)
        buttonSkin.clicked.connect(volumes.volumesToSkinning)
        buttonRemove.clicked.connect(self.removeVolumes)

        for item in self._itemDelegateNames:
            self.comboVolumeType.addItem(item)

        self.comboVolumeType.setCurrentIndex(0)

        hlayout = QHBoxLayout()
        hlayout.addWidget(buttonAdd, 1)
        hlayout.addWidget(buttonFit, 1)

        mainLayout = QVBoxLayout()
        mainLayout.addWidget(QLabel("Volume creation"))
        mainLayout.addWidget(self.comboVolumeType)
        mainLayout.addWidget(buttonAddFit)
        mainLayout.addLayout(hlayout)
        mainLayout.addWidget(base_ui.createSeparator())
        mainLayout.addWidget(QLabel("Volumes to skinning"))
        mainLayout.addWidget(buttonSkin)
        mainLayout.addWidget(base_ui.createSeparator())
        mainLayout.addWidget(buttonRemove)
        mainLayout.addStretch(1)

        self.setLayout(mainLayout)

    @staticmethod
    def _getItems():
        return cmds.ls(sl=True, type='joint')

    def createAndFitVolumes(self):
        creationDelegate = self._itemDelegates[self.comboVolumeType.currentIndex()]
        volumes.buildVolumes(
            self._getItems(), creationDelegate,
            performShrinkWrap=True)

    def createVolumes(self):
        volumes.buildVolumes(
            self._getItems(),
            performShrinkWrap=False)

    def removeVolumes(self):
        volumes.removeVolumes(self._getItems())

#end
