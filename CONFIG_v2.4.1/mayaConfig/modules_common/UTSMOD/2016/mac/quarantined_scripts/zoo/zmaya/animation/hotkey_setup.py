
from PySide.QtGui import *
from PySide.QtCore import Qt

from .. import hotkeyer
from .. import base_ui

class CommonAnimatorHotkeys(base_ui.MayaQWidget):
    def __init__(self):
        super(CommonAnimatorHotkeys, self).__init__()
        self.setMinimumWidth(300)

        self.keyWidgets = []
        def addHotkey(*a, **kw):
            widget = hotkeyer.SingleHotkeyWidget(*a, **kw)
            self.keyWidgets.append(widget)

        addHotkey('zooResetAttrs', 's', 'from zoo.zmaya.animation import reset_attrs; reset_attrs.resetSelection()',
                  annotation='Resets all keyable attributes to their default values',
                  mods=hotkeyer.ALT,
                  isPython=True)

        addHotkey('zooSetKeyMenu', 'q',
                  'zooTangentWks', 'zooTangentWksKillUI',
                  annotation='Marking menu to make it super easy to work with key tangents',
                  isPython=False)

        addHotkey('zooSetKeyMenu', 'y',
                  'zooSetMenu', 'zooSetMenuKillUI',
                  annotation='Marking menu that makes it easy to work with selection sets',
                  isPython=False)

        """addHotkey('zooRigSelectionMM', 'y',
                  'from zoo.zmaya.skeletonBuilder import tools; tools.RigSelectionMM()',
                  'from zoo.zmaya import marking_menu; marking_menu.MarkingMenu.kill()',
                  annotation='Used to quickly select all members of the selection set in which the '
                             'currently selected object is part of. Press and hold the hotkey to '
                             'display a marking menu',
                  mods=hotkeyer.DISABLED,
                  isPython=True)"""

        addHotkey('zooSetKeyMenu', 's',
                  'zooSetkey', 'zooSetkeyKillUI',
                  annotation='Enhanced version of the default setkeyframe hotkey',
                  skipByDefault=True,
                  isPython=False)

        addHotkey('zooScrubTime', 'v',
                  'storeLastAction( "restoreLastContext " + `currentCtx` );setToolTo TimeDragger',
                  'invokeLastAction',
                  annotation='Hold down this hotkey and drag in the viewport to scrub time',
                  mods=hotkeyer.DISABLED)

        addHotkey('zooAlignSelection', 'a',
                  'from zoo.zmaya import align_utils; align_utils.alignSelection()',
                  annotation='Aligns all selected objects to the first object in the selection',
                  mods=hotkeyer.ALT,
                  isPython=True)

        addHotkey('zooSelectOppositeControl', 'd',
                  'from zoo.zmaya.skeletonBuilder import tools; tools.selectOppositeControl()',
                  annotation='Selects the selected node\'s opposite nodes using',
                  mods=hotkeyer.ALT,
                  isPython=True)

        addHotkey('zooCamMM', 'l',
                  'zooCam',
                  'zooCamKillUI',
                  annotation='Selects the selected node\'s opposite nodes using',
                  mods=hotkeyer.ALT,
                  isPython=False)

        addHotkey('zooHotkeySetsMM', 'l',
                  'from zoo.zmaya import ui_hotkey_sets; ui_hotkey_sets.HotkeyMarkingMenu()',
                  'from zoo.zmaya import marking_menu; marking_menu.MarkingMenu.kill()',
                  annotation='Displays a marking menu with available hotkey sets',
                  mods=hotkeyer.DISABLED,
                  isPython=True)

        # LAYOUT
        scrollAreaWidget = QWidget()
        scrollLayout = QVBoxLayout()
        scrollLayout.setSpacing(0)
        scrollLayout.setContentsMargins(4, 4, 4, 4)
        scrollAreaWidget.setLayout(scrollLayout)
        for widget in self.keyWidgets:
            scrollLayout.addWidget(widget)
            scrollLayout.addWidget(base_ui.createSeparator())

        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setAlignment(Qt.Vertical)
        scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scrollArea.setWidget(scrollAreaWidget)

        button = QPushButton('Setup All Hotkeys')
        button.clicked.connect(self.on_setup)

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(scrollArea, 1)
        layout.addSpacing(0)
        layout.addWidget(button)

        self.setLayout(layout)

    def on_setup(self):
        for widget in self.keyWidgets:
            if widget.skip:
                continue

            widget.create()

        self.close()

#end
