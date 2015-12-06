
from maya import cmds

from ..baseMelUI import *
from .. import mappingEditor

import clip


class XferAnimMappingLayout(mappingEditor.MappingLayout):
    def build_srcMenu(self, *a):
        super(XferAnimMappingLayout, self).build_srcMenu(*a)
        cmds.menuItem(l='Auto-Generate Offsets', c=self.on_autoMap)

    def on_autoMap(self, *a):
        clip.autoGeneratePostTraceScheme(self.getMapping())

class XferAnimForm(MelVSingleStretchLayout):
    def __init__(self, parent):
        MelVSingleStretchLayout.__init__(self, parent)

        self._clip = None
        self.UI_mapping = XferAnimMappingLayout(self)

        vLayout = MelVSingleStretchLayout(self)
        hLayout = MelHLayout(vLayout)
        vLayout.setStretchWidget(hLayout)

        colLayout = MelColumnLayout(hLayout)
        self.UI_radios = MelRadioCollection()
        self.RAD_dupe = self.UI_radios.createButton(colLayout, l="duplicate nodes", align='left', sl=True, cc=self.on_update)
        self.RAD_copy = self.UI_radios.createButton(colLayout, l="copy/paste keys", align='left', cc=self.on_update)
        self.RAD_trace = self.UI_radios.createButton(colLayout, l="trace objects", align='left', cc=self.on_update)

        colLayout = MelColumnLayout(hLayout)
        self.UI_check1 = MelCheckBox(colLayout, l="instance animation")
        self.UI_check2 = MelCheckBox(colLayout, l="match rotate order", v=True)
        self.UI_check3 = MelCheckBox(colLayout, l="")
        hLayout.layout()

        self.UI_traceOptionsLayout = hLayout = MelHRowLayout(self)
        self.UI_keysOnly = MelCheckBox(hLayout, l="keys only", v=True, cc=self.on_update)
        self.UI_withinRange = MelCheckBox(hLayout, l="within range:", v=False, cc=self.on_update)
        MelLabel(hLayout, l="start ->")
        self.UI_start = MelTextField(hLayout, en=False, tx='!', w=50)
        cmds.popupMenu(p=self.UI_start, b=3, pmc=self.buildTimeMenu)

        MelLabel(hLayout, l="end ->")
        self.UI_end = MelTextField(hLayout, en=False, tx='!', w=50)
        cmds.popupMenu(p=self.UI_end, b=3, pmc=self.buildTimeMenu)
        hLayout.layout()

        vLayout.layout()

        self.UI_button = MelButton(self, l='Xfer Animation', c=self.on_xfer)

        self.setStretchWidget(self.UI_mapping)
        self.layout()

        self.on_update()  #set initial state

    def setMapping(self, mapping):
        self.UI_mapping.setMapping(mapping)

    def setClip(self, clip, mapping=None):
        self._clip = clip

        #populate the source objects from the file
        self.UI_mapping.replaceSrcItems(clip.getNodes())

        self.RAD_dupe(e=True, en=True, l="times from clip")
        self.RAD_copy(e=True, en=True, sl=True, l="load clip at current time")
        self.RAD_trace(e=True, en=False, vis=False)

        self.UI_check1(e=True, l="additive key values")
        self.UI_check2(e=True, l="import as world space", v=False)
        self.UI_check3(e=True, vis=0)
        self.UI_traceOptionsLayout.setVisibility(False)

        self.UI_button.setLabel('Load Clip')

        self.on_update()

    ### MENU BUILDERS ###
    def buildTimeMenu(self, parent, uiItem):
        cmds.menu(parent, e=True, dai=True)
        cmds.setParent(parent, m=True)

        cmds.menuItem(l="! - use current range", c=lambda a: cmds.textField(uiItem, e=True, tx='!'))
        cmds.menuItem(l=". - use current frame", c=lambda a: cmds.textField(uiItem, e=True, tx='.'))
        cmds.menuItem(l="$ - use scene range", c=lambda a: cmds.textField(uiItem, e=True, tx='$'))

    ### EVENT HANDLERS ###
    def on_update(self, *a):
        sel = cmds.ls(sl=True, dep=True)

        if not self._clip is not None:
            if self.RAD_dupe.getValue():
                self.UI_check1.setEnabled(True)
            else:
                self.UI_check1(e=True, en=False, v=False)

        if self.RAD_trace.getValue():
            self.UI_keysOnly.setEnabled(True)
            self.UI_check2.getValue()
            self.UI_check3(e=True, vis=True, v=True, l="process post-trace cmds")
        else:
            self.UI_keysOnly(e=True, en=False)
            self.UI_check3(e=True, vis=False, v=False)

        if  self.UI_keysOnly.getValue():
            self.UI_withinRange.setEnabled(True)
        else:
            self.UI_withinRange(e=True, en=False, v=False)

        enableRange = self.RAD_copy.getValue() or self.RAD_trace.getValue()
        keysOnly = self.UI_keysOnly.getValue()
        withinRange = self.UI_withinRange.getValue()
        if enableRange and not keysOnly or withinRange:
            self.UI_start.setEnabled(True)
            self.UI_end.setEnabled(True)
        else:
            self.UI_start.setEnabled(False)
            self.UI_end.setEnabled(False)

    def on_xfer(self, *a):
        mapping = self.UI_mapping.getMapping()

        startTime = self.UI_start.getValue()
        endTime = self.UI_end.getValue()
        if startTime.isdigit():
            startTime = int(startTime)
        else:
            if startTime == '!': startTime = cmds.playbackOptions(q=True, min=True)
            elif startTime == '.': startTime = cmds.currentTime(q=True)
            elif startTime == '$': startTime = cmds.playbackOptions(q=True, animationStartTime=True)

        if endTime.isdigit():
            endTime = int(endTime)
        else:
            if endTime == '!': endTime = cmds.playbackOptions(q=True, max=True)
            elif endTime == '.': endTime = cmds.currentTime(q=True)
            elif endTime == '$': endTime = cmds.playbackOptions(q=True, animationEndTime=True)

        if self._clip is not None:
            assert isinstance(self._clip, clip.BaseClip)

            mapping = self.UI_mapping.getMapping()
            self._clip.setMapping(mapping).apply(mapping.tgts, worldSpace=worldSpace, additive=additive)

        elif self.RAD_dupe.getValue():
            instance = additive = self.UI_check1.getValue()
            matchRo = worldSpace = self.UI_check2.getValue()
            clip.AnimCurveDuplicator(instance, matchRo).apply(mapping)

        elif self.RAD_copy.getValue():
            clip.AnimClip.Generate(mapping.srcs).apply(mapping, applySettings)

        elif self.RAD_trace.getValue():
            traceKeys = self.UI_keysOnly.getValue()
            processPostCmds = self.UI_check3.getValue()
            clip.Tracer(traceKeys, processPostCmds, startTime, endTime).apply(mapping, True)

class XferAnimWindow(BaseMelWindow):
    WINDOW_NAME = 'xferAnim'
    WINDOW_TITLE = 'Xfer Anim'

    DEFAULT_SIZE = 375, 450
    DEFAULT_MENU = None

    def __new__(cls, mapping=None, clip=None):
        return BaseMelWindow.__new__(cls)

    def __init__(self, mapping=None, theClip=None):
        BaseMelWindow.__init__(self)

        self.editor = XferAnimForm(self)
        if theClip is not None:
            assert isinstance(theClip, clip.BaseClip)
            self.editor.setClip(theClip)

        if mapping is not None:
            self.editor.setMapping(mapping)

        self.show()

#end