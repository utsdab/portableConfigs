
import cPickle as pickle

from maya import cmds

from .. import path
from .. import presets

from . import mel_utils

TOOL_NAME = 'zooHotkeySets'

class RuntimeCommand(object):

    @classmethod
    def FromMaya(cls, name):
        self = cls(
            name,
            cmds.runTimeCommand(name, q=True, annotation=True),
            cmds.runTimeCommand(name, q=True, commandLanguage=True),
            cmds.runTimeCommand(name, q=True, command=True))

        self.isDefault = self.name in cmds.runTimeCommand(q=True, defaultCommandArray=True)

        return self

    def __init__(self, name, annotation, lang, cmdStr):
        self.name = name
        self.annotation = annotation
        self.lang = lang
        self.cmdStr = cmdStr
        self.isDefault = False

def getNameCommandDict():
    d = {}
    for idx in range(cmds.assignCommand(q=True, num=True)):
        name = cmds.assignCommand(q=True, index=idx + 1, name=True)
        d[name] = idx

class NamedCommand(object):

    @classmethod
    def FromMaya(cls, name, nameCmdDict=None):
        if nameCmdDict is None:
            nameCmdDict = getNameCommandDict()

        idx = nameCmdDict[name]
        self = cls(
            name,
            'mel',
            cmds.assignCommand(name, q=True, index=idx, command=True),
            idx)

        return self

    def __init__(self, name, lang, cmdStr, idx=-1):
        self.name = name
        self.lang = lang
        self.cmdStr = cmdStr
        self.rtc = None
        self.idx = -1

class Hotkey(object):
    def __init__(self, key, ncName, ctrl=False, alt=False, isPress=True):
        self.key = key
        self.name = ncName
        self.ctrl = ctrl
        self.alt = alt
        self.isPress = isPress # Otherwise it is a release command
        self.namedCommand = None

    @property
    def _rtc(self):
        if self.namedCommand:
            return self.namedCommand.rtc

    @property
    def cmdStr(self):
        if self._rtc:
            return self._rtc.cmdStr
        elif self.namedCommand:
            return self.namedCommand.cmdStr

    @property
    def lang(self):
        if self._rtc:
            return self._rtc.lang

    @property
    def annotation(self):
        if self._rtc:
            return self._rtc.annotation

def resetToDefault():
    cmds.assignCommand(e=True, factorySettings=True)
    for x in range(cmds.assignCommand(q=True, num=True)) or []:
        cmds.assignCommand(e=True, delete=1)

    cmds.assignCommand(e=True, factorySettings=True)
    for rtcCmdName in cmds.runTimeCommand(q=True, userCommandArray=True) or []:
        cmds.runTimeCommand(rtcCmdName, e=True, delete=True)

    cmds.hotkey(factorySettings=True)

def getCurrentHotkeySetName():
    if cmds.optionVar(ex=TOOL_NAME):
        return cmds.optionVar(q=TOOL_NAME)

    # Return an empty string if there is no 'current' hotkey set defined
    return ''

def _iterFiles():
    prefsDir = path.Path(cmds.internalVar(userPrefDir=True))

    # Yield the runtime commands first so that when we source the scripts, the
    # runtime commands get created first, which then get referenced by the
    # named commands (why the fuck so complicated?!)
    yield prefsDir / 'userRunTimeCommands.mel'

    # Now yield named commands. The runtime commands these named commands refer
    # to should have already been sourced
    yield prefsDir / 'userNamedCommands.mel'

    # Finally yield the hotkeys which point to the named commands
    yield prefsDir / 'userHotkeys.mel'

def _deleteRuntimeCommands():
    runtimeCmds = cmds.runTimeCommand(q=True, userCommandArray=True) or []
    for runtimeCmd in runtimeCmds:
        cmds.runTimeCommand(runtimeCmd, e=True, delete=True)

def _deleteHotkeyAssignments():
    pass

def _forceReload():

    # Force the deletion of all runtime commands
    _deleteRuntimeCommands()

    # Force deletion of all hotkey assignments
    _deleteHotkeyAssignments()

    # Force a reload of the runtime commands
    mel_utils.MEL.Source(_iterFiles().next())

    # Now reload the name commands
    cmds.assignCommand(sourceUserCommands=True)

    # Now reload the hotkeys
    cmds.hotkey(sourceUserHotkeys=True)

def saveToFilepath(filepath):

    # First we want to force a save of the current hotkeys
    cmds.savePrefs(hotkeys=True)

    def read(filepath):
        with open(filepath) as f:
            return f.read()

    # Read in the files
    data = (read(f) for f in _iterFiles())

    # Now write them to the preset file
    with open(str(filepath), 'w') as fPreset:

        # Write data to the destination file
        pickle.dump(tuple(data), fPreset)

    # Store an optionvar to store this hotkey set name. It is by definition the
    # current hotkey set
    cmds.optionVar(sv=(TOOL_NAME, filepath.name()))

def loadFromFilepath(filepath, replace=True):

    # Create a backup of the current hotkeys just in case something goes
    # horribly wrong
    saveBackup()

    # Reset to default hotkeys if the replace flag is True
    if replace:
        resetToDefault()

    # Load the preset file and unpickle the contents
    with open(str(filepath)) as fPreset:
        data = pickle.load(fPreset)

    # Write the contents to the appropriate files
    for scriptFilepath, contents in zip(_iterFiles(), data):
        with open(scriptFilepath, 'w') as f:
            f.write(contents)

    # Source the scripts we just copied
    for scriptFilepath in _iterFiles():
        mel_utils.MEL.Source(scriptFilepath)

    # Source user hotkeys explicitly, I don't think this is necessary but I
    # don't think it hurts
    cmds.hotkey(sourceUserHotkeys=True)

    # Store an optionvar so we know which hotkey set is currently loaded
    cmds.optionVar(sv=(TOOL_NAME, filepath.name()))

    # Force the freshly loaded hotkeys and optionVars to save
    cmds.savePrefs(hotkeys=True, general=True)

def saveToPreset(preset):
    saveToFilepath(preset.path())

def saveToPresetName(presetName):
    saveToPreset(HotkeySet.Manager.getPreset(presetName))

def loadFromPreset(preset, replace=True):
    loadFromFilepath(preset.path(), replace)

def loadFromPresetName(presetName, replace=True):
    loadFromPreset(HotkeySet.Manager.getPreset(presetName), replace)

def getBackupPreset():
    return presets.Preset('userHotkeys', TOOL_NAME, extension='backup')

def saveBackup():
    saveToPreset(getBackupPreset())

def loadBackup():
    loadFromPreset(getBackupPreset())

class HotkeySet(object):
    Manager = presets.Manager(TOOL_NAME)

    def __init__(self, name):
        self.name = name

    def getPreset(self):
        return self.Manager.getPreset(self.name)

    def save(self):
        return saveToPreset(self.getPreset())

    def load(self):
        return loadFromPreset(self.getPreset())

def getCurrentHotkeySet():
    name = getCurrentHotkeySetName()
    if name:
        return HotkeySet(name)

    return None

#end
