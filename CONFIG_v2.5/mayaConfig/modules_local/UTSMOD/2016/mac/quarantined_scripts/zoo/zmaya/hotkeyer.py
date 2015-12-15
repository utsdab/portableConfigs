
import logging

from PySide.QtGui import *

from maya import cmds

import base_ui

logger = logging.getLogger(__name__)

MODS = NONE, DISABLED, ALT, CTRL = tuple(2**n for n in xrange(4))

def _dictToStr(d):
    return ', '.join('%s=%r' % i for i in d.iteritems())

def create(keyStr, nameStr, pressCmdStr, releaseCmdStr='',
           annotation='', mods=0, isPython=True, isRuntimeCommandName=False):
    if not keyStr:
        raise Exception("No hotkey was specified - please choose a key")

    # Define the language command string
    lang = 'python' if isPython else 'mel'

    # If isRuntimeCommandName is True, then the command strings are runtime command
    # names, so we don't need to create new runtime commands
    if isRuntimeCommandName:
        rtName = pressCmdStr
        rtRelName = releaseCmdStr

    # Otherwise, we need to create new runtime commands
    else:
        rtName = '%s_hotkeyPrs' % nameStr
        if cmds.runTimeCommand(rtName, q=True, ex=True):
            cmds.runTimeCommand(rtName, e=True, delete=True)

        rtRelName = '%s_hotkeyRel' % nameStr
        if cmds.runTimeCommand(rtRelName, q=True, ex=True):
            cmds.runTimeCommand(rtRelName, e=True, delete=True)

        cmds.runTimeCommand(rtName, ann=annotation, cat='User', command=pressCmdStr, commandLanguage=lang)
        if releaseCmdStr:
            cmds.runTimeCommand(rtRelName, ann='release cmd for %s' % nameStr, cat='User', command=releaseCmdStr, commandLanguage=lang)

    # Create the nameCommands
    ncName = '%sNameCmd' % rtName
    ncRelName = '%sNameCmd' % rtRelName
    cmds.nameCommand(ncName, ann=annotation or nameStr, command=rtName, sourceType=lang)
    if releaseCmdStr:
        cmds.nameCommand(ncRelName, ann='release cmd for %s' % nameStr, command=rtRelName, sourceType=lang)

    # Bind the name commands to a hotkey
    hotkeyKwargs = {'keyShortcut': keyStr,
                    'name': ncName,
                    'ctl': bool(mods & CTRL),
                    'alt': bool(mods & ALT),
                    }

    if releaseCmdStr:
        hotkeyKwargs['releaseName'] = ncRelName

    cmds.hotkey(**hotkeyKwargs)

class HotkeyerDefinitionWidget(base_ui.MayaQWidget):
    def __init__(self, name, default, pressCmd, releaseCmd='', mods=DISABLED, locked=False, annotation='',
                 isPython=False, isRuntimeCommandName=False):
        base_ui.MayaQWidget.__init__(self)

        self._name = name

        self._pressCmd = pressCmd
        self._releaseCmd = releaseCmd

        self._annotation = annotation or name or pressCmd
        self._isPython = isPython
        self._isRuntimeCommandName = isRuntimeCommandName

        label = QLabel(annotation)
        label.setWordWrap(True)
        if not annotation:
            label.setVisible(False)

        self.key = QLineEdit()
        self.key.setText(default)

        self.ctrl = QCheckBox('ctrl')
        self.ctrl.setChecked(mods & CTRL)

        self.alt = QCheckBox('alt')
        self.alt.setChecked(mods & ALT)

        if locked:
            self.key.setEnabled(False)
            self.ctrl.setEnabled(False)
            self.alt.setEnabled(False)

        if mods & DISABLED:
            self.ctrl.setEnabled(False)
            self.alt.setEnabled(False)

        layout = QHBoxLayout()
        layout.addWidget(self.key, 1)
        layout.addWidget(self.ctrl, 1)
        layout.addWidget(self.alt, 1)

        vLayout = self.makeVLayout()
        vLayout.addWidget(label)
        vLayout.addLayout(layout)

        self.setLayout(vLayout)

    def create(self):
        mods = 0
        if self.ctrl.isChecked():
            mods |= CTRL

        if self.alt.isChecked():
            mods |= ALT

        try:
            create(
                self.key.text(),
                self._name, self._pressCmd, self._releaseCmd,
                self._annotation, mods,
                self._isPython, self._isRuntimeCommandName)
        except Exception, x:
            logger.error(str(x), exc_info=x)

class SingleHotkeyWidget(base_ui.MayaQWidget):
    def __init__(self, name, default, pressCmd, releaseCmd='', mods=DISABLED, locked=False, annotation='',
                 isPython=True, isRuntimeCommandName=False, skipByDefault=False):
        base_ui.MayaQWidget.__init__(self)

        self._definitionWidget = HotkeyerDefinitionWidget(
            name, default, pressCmd, releaseCmd, mods, locked, annotation, isPython, isRuntimeCommandName)

        self._setupButton = QPushButton('Setup This Hotkey')
        self._setupButton.clicked.connect(self.create)

        self._skipCheckWidget = QCheckBox('Skip This Hotkey')
        self._skipCheckWidget.stateChanged.connect(self.on_skipped)

        if skipByDefault:
            self._skipCheckWidget.setChecked(True)

        hlayout = self.makeHLayout()
        hlayout.addWidget(self._skipCheckWidget)
        hlayout.addWidget(self._setupButton, 1)

        layout = self.makeVLayout()
        layout.addWidget(self._definitionWidget)
        layout.addLayout(hlayout)
        self.setLayout(layout)

    @property
    def skip(self):
        return self._skipCheckWidget.isChecked()

    def create(self):
        self._definitionWidget.create()

    def on_skipped(self, state):
        self._setupButton.setEnabled(not state)
        self._definitionWidget.setEnabled(not state)

Hotkeyer = SingleHotkeyWidget.Show

#end
