#                only for maya 2011/2012/2013
#
#
#             curveRecreator.py 
#             version 2.0, last modified 31/07/2014
#             Copyright (C) 2014 Perry Leijten
#             Email: perryleijten@gmail.com
#             Website: www.perryleijten.com
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# See http://www.gnu.org/licenses/gpl.html for a copy of the GNU General 
# Public License.
#--------------------------------------------------------------------------------#
#                    I N S T A L L A T I O N:
#
# Copy the "curveRecreator.py" together with "ControlCurveCreater.ui", Icon folder and curves folder to your Maya scriptsdirectory:
#     MyDocuments\Maya\scripts\
#         use this text as a python script within Maya:
'''
import curveRecreator
curveRecreator.StartUI()
'''
# this text can be entered from the script editor and can be made into a button
#
# note: PyQt and sip or pyside  libraries are necessary to run this file
import curveRecreator, os, sys, re, stat, functools,shutil
from maya import mel, cmds, OpenMayaUI

default = "none"
try:
    from PyQt4                 import *
    from PyQt4                 import QtCore
    from PyQt4                 import uic
    import sip
    default = "pyqt4"
except:
    print "pyqt4 not found"
try:
    import xml.etree.ElementTree     as xml
    from cStringIO                     import StringIO
    from PySide                     import QtGui, QtCore
    import pysideuic, shiboken
    default = "pyside"
except:
    print "pyside not found"

if default == "none":
    cmds.error("no Library found, please install PyQt4 or PySide!")

def loadUiType(uiFile):
    if default ==  "pyqt4":
        form_class, base_class =  uic.loadUiType( uiFile )
    else:
        parsed = xml.parse(uiFile)
        widget_class = parsed.find('widget').get('class')
        form_class = parsed.find('class').text

        with open(uiFile, 'r') as f:
            o = StringIO()
            frame = {}

            pysideuic.compileUi(f, o, indent=0)
            pyc = compile(o.getvalue(), '<string>', 'exec')
            exec pyc in frame

            form_class = frame['Ui_%s'%form_class]
            base_class = eval('QtGui.%s'%widget_class)
    return form_class, base_class


FilePath = curveRecreator.__file__.replace('\\','/').rsplit('/',1)[0] + '/'
qDir     = QtCore.QDir()
uiFile   = FilePath + 'ControlCurveCreator.ui'
sub      = FilePath + 'controlImageInterface.ui'
ui_path  = os.path.dirname(uiFile)
qDir.setCurrent(ui_path)
Control_CreatorUI_form, Control_CreatorUI_base         = loadUiType(uiFile)
Control_CreatorUI_form_sub, Control_CreatorUI_base_sub = loadUiType(sub)


def wrapinstance(ptr, base=None):
    if ptr is None:
        return None
    ptr = long(ptr) #Ensure type
    if globals().has_key('shiboken'):
        if base is None:
            qObj = shiboken.wrapInstance(long(ptr), QtCore.QObject)
            metaObj = qObj.metaObject()
            cls = metaObj.className()
            superCls = metaObj.superClass().className()
            if hasattr(QtGui, cls):
                base = getattr(QtGui, cls)
            elif hasattr(QtGui, superCls):
                base = getattr(QtGui, superCls)
            else:
                base = QtGui.QWidget
        return shiboken.wrapInstance(long(ptr), base)
    elif globals().has_key('sip'):
        base = QtCore.QObject
        return sip.wrapinstance(long(ptr), base)
    else:
        return None


# subwindow for creation of images
class SubWindow(Control_CreatorUI_form_sub, Control_CreatorUI_base_sub):
    def __init__(self, parent = None, filePath = None, inputPreset = None , name = 'test', ischecked = True):
        super(SubWindow , self).__init__(parent)  
        self.setupUi(self)

        self.isChecked     = ischecked
        self.__itemCreated = False
        self.inputPresets  = inputPreset
        self.name          = name
        self.filePath      = filePath

        self.setObjectName("subwindow")
        self.setWindowTitle("controller Image")
        self.viewportLayout.setObjectName("mainLayout")

        polyDetails    = cmds.optionVar(q='polyCountVisibility')
        self.polyCount = False
        if polyDetails == 1 : 
            cmds.TogglePolyCount()
            self.polyCount = True

        self.__addViewport()
        self.SaveAndCloseButton.clicked.connect(self.__saveAndClose)

    def __addViewport(self, *args):
        if default == "pyqt4":
            layout = OpenMayaUI.MQtUtil.fullName(long(sip.unwrapinstance(self.viewportLayout)))
        else:
            layout = OpenMayaUI.MQtUtil.fullName(long(shiboken.getCppPointer(self.viewportLayout)[0]))
        cmds.setParent(layout)
 
        paneLayoutName = cmds.paneLayout("test")
        ptr = OpenMayaUI.MQtUtil.findControl(paneLayoutName)
        
        self.paneLayout = wrapinstance(long(ptr))
        self.cameraName = cmds.camera()[0]
        cmds.hide(self.cameraName)
        self.modelPanelName = cmds.modelPanel(label="ModelPanel Test", cam=self.cameraName, mbv=False)
        
        mel.eval('modelPanelBarDecorationsCallback("GridBtn","'+self.modelPanelName+'", "'+self.modelPanelName+'|modelEditorIconBar");')
        ptr = OpenMayaUI.MQtUtil.findControl(self.modelPanelName)
        self.modelPanel = wrapinstance(long(ptr))

        self.viewportLayout.addWidget(self.paneLayout)

        cmds.modelEditor( self.modelPanelName, edit = True, displayAppearance='smoothShaded', lw=2)
        cmds.viewFit( self.cameraName, all=True )
        barLayout = cmds.modelPanel(self.modelPanelName, q=True, bl=True)
        ptr = OpenMayaUI.MQtUtil.findControl(barLayout)
        self.barLayout = wrapinstance(long(ptr))
        children =  self.barLayout.children()
        
        if default == "pyqt4":
            sip.delete(children[0])

    def createSnapshot(self, width=200, height=200):
        cmds.setFocus(self.modelPanelName)
            
        filename=self.filePath+ 'Curves/' + self.name   
        try:
            f = cmds.playblast(wh=(width,height), 
                               fp=0, 
                               frame=cmds.currentTime(q=True), 
                               format='image', 
                               compression='png', 
                               forceOverwrite=True, 
                               viewer=False)
        except Exception as e:
            cmds.warning(e.message)
        cmds.modelEditor( self.modelPanelName, edit = True,lw =1)
        f = os.path.abspath(f.replace('####', '0'))
        shutil.move(f, filename+'.png')

        return os.path.abspath(filename)

    def __saveAndClose(self, *args):
        self.createSnapshot()
        self.GetControler(self.inputPresets)
        self.__itemCreated = True
        self.close()
    
    def returnCreatedItem(self):
        return self.__itemCreated

    def closeEvent(self, event):
        cmds.delete(self.cameraName)
        if self.polyCount:
            cmds.TogglePolyCount() 

    def __fileWriteOrAdd(self, inFileName, inText, inWriteOption):                                                                                                                     
        if os.path.exists(inFileName):
            read_only_or_write_able = os.stat(inFileName)[0]
            if read_only_or_write_able != stat.S_IWRITE:
                os.chmod(inFileName, stat.S_IWRITE)

        file = open(inFileName, inWriteOption)
        file.write(inText)
        file.close()

    def GetControler(self, Selected, *args):
        cmds.delete(Selected, ch=True)

        curveDirectory = (self.filePath+ 'Curves/' + self.name+ '.py')

        directory = os.path.dirname(str(curveDirectory))
        if not os.path.exists(directory):
            os.makedirs(directory)

        baseText = 'import maya.cmds as cmds\n'
        self.__fileWriteOrAdd((curveDirectory), baseText, 'w')
        multipleShapes = False
        
        def completeList(input):
            childrenBase = cmds.listRelatives(input, ad=True, type="transform")
            childrenBase.append(input)
            childrenBase.reverse()
            return childrenBase

        childrenBase = cmds.listRelatives( Selected, ad=True, type="transform")
        if childrenBase:
            selection = completeList(Selected)
        else:
            selection = [Selected] 

        for Selected in selection:
            shapeNode = cmds.listRelatives(Selected, s=True, f=True)
            listdef = '%s = []\n'%Selected
            self.__fileWriteOrAdd((curveDirectory), listdef, 'a')


            for shapes in shapeNode:
                controlVerts      = cmds.getAttr(shapes+'.cv[*]')
                curveDegree       = cmds.getAttr(shapes+'.degree')
                period            = cmds.getAttr(shapes+'.f')
                localPosition     = cmds.getAttr(Selected+'.translate')
                worldPosition     = cmds.xform(Selected, q=True, piv=True, ws=True)
                
                print controlVerts
                infoNode = cmds.createNode('curveInfo')
                cmds.connectAttr((shapes + '.worldSpace'), (infoNode+'.inputCurve'))
                
                if len(shapeNode) > 1:
                    multipleShapes = True
                
                list1 = []
                list2 = []
                list3 = []
                
                knots = cmds.getAttr(infoNode+'.knots')
                for i in knots[0]:
                    list3.append(int(i))
                
                if self.isChecked:
                    for i in xrange(len(controlVerts)):    
                        for j in xrange(3):
                            originCalculation     =  (float(controlVerts[i][j])-float(worldPosition[j]))
                            localSpaceAddition    =  originCalculation + float(localPosition[0][j])
                            list1.append(localSpaceAddition)
                        list2.append(list1)
                        list1=[]
                else:
                    list2 = controlVerts
                
                if period == 0 :
                    periodNode = ',per = False'
                else:
                    periodNode = ',per = True'
                    for i in range(curveDegree):
                        list2.append(list2[i])
                    
                CurveCreation = ('cmds.curve( p =' + str(list2).replace('[','(').replace(']',')').replace('((','[(').replace('))',')]') + periodNode+ ', d=' + str(curveDegree) + ', k=' + str(list3)  + ')')
                CurveCreation = ('%s.append('%Selected+CurveCreation+')')
                self.__fileWriteOrAdd((curveDirectory), str(CurveCreation+'\n'), 'a')
                
                cmds.delete(infoNode)
                
            if multipleShapes == True:
                End = 'for x in range(len(%s)-1):\n\tcmds.makeIdentity(%s[x+1], apply=True, t=1, r=1, s=1, n=0)\n\tshapeNode = cmds.listRelatives(%s[x+1], shapes=True)\n\tcmds.parent(shapeNode, %s[0], add=True, s=True)\n\tcmds.delete(%s[x+1])\n'%(Selected,Selected,Selected,Selected,Selected)
                self.__fileWriteOrAdd((curveDirectory), End, 'a')
            
            parentObject = cmds.listRelatives(Selected, parent=True)
            if parentObject:
                listdef = 'cmds.parent(%s[0], %s[0])\n'%(Selected, parentObject[0])
                self.__fileWriteOrAdd((curveDirectory), listdef, 'a')
        
        close = 'fp = cmds.listRelatives(%s[0], f=True)[0]\npath = fp.split("|")[1]\ncmds.select(path)'%Selected
        self.__fileWriteOrAdd((curveDirectory), close, 'a')

class Control_CreatorUI(Control_CreatorUI_form, Control_CreatorUI_base):
    def __init__(self, parent=None):
        super(Control_CreatorUI, self).__init__(parent)
        self.setupUi(self)
        self.__ColorCurveCommand()
        self.__getAllFonts()
        self.__BasicTestSetting()
        self.__readOutFiles()
        self.__CheckNameGet()
        
        self.presetPath = FilePath

        self.__qt_normal_color = QtGui.QPalette(self.ControlNameLineEdit.palette()).color(QtGui.QPalette.Base)
        
        self.GetCurveButton.clicked.connect(self.__imageCreationWindow)
        self.closeButton.clicked.connect(self.__dockWindow_Delete)
        self.CreateTextButton.clicked.connect(self.__createText)
        self.CombineButton.clicked.connect(self.CombineCurveShapes)
        self.TextlineEdit.textEdited[unicode].connect(self.__ButtonEnable)
        self.ControlNameLineEdit.textEdited[unicode].connect(    self.__lineEdit_FieldEditted)
        self.NamecheckBox.toggled.connect(self.__CheckNameGet)    
        self.InfoButton.clicked.connect(self.__infoWindow)
        self.normal_state_Button.clicked.connect(self.__normalStateObject)
        self.template_state_Button.clicked.connect(self.__templateStateObject)
        self.refference_state_Button.clicked.connect(self.__refferenceStateObject)
        self.presetsTreeWidget.itemSelectionChanged.connect(self.__handleChanged)

        self.presetsTreeWidget.itemDoubleClicked.connect(self.__doubleClicked)

        self.deleteButton.clicked.connect(self._deletecontroller)

        def keyPressEventOverride(superFn, event):
            key = event.key()
            if key == QtCore.Qt.Key.Key_Control or key == QtCore.Qt.Key.Key_Shift: return
            superFn(event)

        fn = self.TextlineEdit.keyPressEvent
        superFn  = functools.partial(fn, self.TextlineEdit)
        self.TextlineEdit.keyPressEvent = functools.partial(keyPressEventOverride, fn)

        fn = self.ControlNameLineEdit.keyPressEvent
        superFn  = functools.partial(fn, self.ControlNameLineEdit)
        self.ControlNameLineEdit.keyPressEvent = functools.partial(keyPressEventOverride, fn)

    def _deletecontroller(self, *args):
        getItem = self.presetsTreeWidget.selectedItems()
        path = FilePath+ 'Curves/'
        if not getItem == []:
            inObject = getItem[0].text(0)
            try:
                os.remove(path + str(inObject) + '.png' )
            except:
                pass
            try:
                os.remove(path + str(inObject) + '.py' )
            except:
                pass
        self.__readOutFiles()

    def __imageCreationWindow(self, *args):
        selection = cmds.ls(sl=True)
        if len(selection) == 0:
            cmds.warning('warning, nothing selected to copy!')
        else:
            for Selected in selection:
                checked = self.NamecheckBox.isChecked()
                if checked:
                    curvename = Selected
                else:
                    InputText = self.ControlNameLineEdit.displayText()
                    curvename = InputText

                mel.eval("HideUnselectedObjects;")

                MayaWindowPtr = wrapinstance(long( OpenMayaUI.MQtUtil.mainWindow() ))
                ischecked = self.centeredCheck.isChecked()
                print ischecked
                subWindow = SubWindow(MayaWindowPtr ,filePath= self.presetPath, inputPreset=Selected, name =curvename, ischecked = ischecked)
                subWindow.exec_()
                if subWindow.returnCreatedItem():
                    self.__readOutFiles()
                
                mel.eval("ShowLastHidden;")
                self.__readOutFiles()

    def __normalStateObject(self, *args):
        self.DisplayType(0)
    def __templateStateObject(self, *args):
        self.DisplayType(1)
    def __refferenceStateObject(self, *args):
        self.DisplayType(2)
    
    def __infoWindow(self, *args):
        cmds.window( width=150 , title = 'info')
        cmds.columnLayout( adjustableColumn=True )
        cmds.text( label='Author  : Perry Leijten',align='left' )
        cmds.text( label='Date    : 31/07/2014 ',align='left')
        cmds.text( label='Version : 2.0 ',align='left')
        cmds.text( label='web     : www.perryleijten.com',align='left' )
        cmds.showWindow()

    def __CheckNameGet(self,*args):
        checked = self.NamecheckBox.isChecked()
        if checked == True:
            self.ControlNameLineEdit.setEnabled(False)            
        else:
            self.ControlNameLineEdit.setEnabled(True)
            self.__lineEdit_FieldEditted()
    
    def __lineEdit_FalseFolderCharacters(self, inLineEdit):                                                                    
        return re.search(r'[\\/:<>"!@#$%^&-.]', inLineEdit) or re.search(r'[*?|]', inLineEdit) or re.match(r'[0-9]', inLineEdit)
    
    def __lineEdit_Color(self, inLineEdit, inColor):                                                                        
        PalleteColor = QtGui.QPalette(inLineEdit.palette())
        PalleteColor.setColor(QtGui.QPalette.Base,QtGui.QColor(inColor))
        inLineEdit.setPalette(PalleteColor)
    
    def __lineEdit_FieldEditted(self,*args):
        Controller_name_text = self.ControlNameLineEdit.displayText()
            
            # Give object field a red color if the input contains wrong characters
        if self.__lineEdit_FalseFolderCharacters(Controller_name_text) != None:
            self.__lineEdit_Color(self.ControlNameLineEdit, 'red')
            self.GetCurveButton.setEnabled(False)
        elif Controller_name_text == "":
            self.GetCurveButton.setEnabled(False)
        else:
            self.__lineEdit_Color(self.ControlNameLineEdit, self.__qt_normal_color)
            self.GetCurveButton.setEnabled(True)

    def CombineCurveShapes(self, *args):
        selection  = cmds.ls(selection=True)
        cmds.select(clear=True)
        for x in range(len(selection)):
            if (x != 0):
                cmds.makeIdentity(selection[x], apply=True, t=1, r=1, s=1, n=0)
                shapeNode = cmds.listRelatives(selection[x], shapes=True)
                cmds.parent(shapeNode, selection[0], add=True, s=True)
                cmds.delete(selection[x])  
        cmds.select(selection[0])  
    
    def __getAllFonts(self, *args):
        fontList = []
        fonts = cmds.fontDialog(FontList=True)
        for i in fonts:    
            removed = i.split('-')
            fontList.append(removed[0])

        AllFonts = self.__RemoveDuplicates(fontList)
        for i in AllFonts:
            self.FontComboBox.addItem(i)
    
    def __RemoveDuplicates(self, seq): 
        noDuplicates = []
        [noDuplicates.append(i) for i in seq if not noDuplicates.count(i)]
        return noDuplicates
    
    def __BasicTestSetting(self):
        menu_items = self.FontComboBox.count()                                                                
        self.__read_hda = []
            
            # Set base filter as empty filter  (NoFilter)
        for i in range(menu_items):
            if self.FontComboBox.itemText(i) == "Times New Roman":
                self.FontComboBox.setCurrentIndex(i)
    
    def __ColorCurveCommand(self):
        self.colorList = [[0,[0.38, 0.38, 0.38], 'None'],    [1,[0.0, 0.0, 0.0]],        [2,[0.75, 0.75, 0.75]],
        [3,[0.5, 0.5, 0.5]],            [4,[0.8, 0.0, 0.2]],        [5,[0.0, 0.0, 0.4]],
        [6,[0.0, 0.0, 1.0]],            [7,[0.0, 0.3, 0.0]],        [8,[0.2, 0.0, 0.2]], 
        [9,[0.8, 0.0, 0.8]],            [10,[0.6, 0.3, 0.2]],        [11,[0.25, 0.13, 0.13]],
        [12,[0.7,0.2,0.0]],                [13,[1.0,0.0,0.0]],            [14,[0.0,1.0,0.0]], 
        [15,[0.0,0.3,0.6]],                [16,[1.0,1.0,1.0]],            [17,[1.0,1.0,0.0]],
        [18,[0.0,1.0,1.0]],                [19,[0.0,1.0,0.8]],            [20,[1.0,0.7,0.7]],
        [21,[0.9,0.7,0.7]],                [22,[1.0,1.0,0.4]],            [23,[0.0,0.7,0.4]],
        [24,[0.6,0.4,0.2]],                [25,[0.63,0.63,0.17]],        [26,[0.4,0.6,0.2]],
        [27,[0.2,0.63,0.35]],            [28,[0.18,0.63,0.63]],        [29,[0.18,0.4,0.63]],
        [30,[0.43,0.18,0.63]],            [31,[0.63,0.18,0.4]]]
        
        self.formColorLayout
        if default == "pyqt4":
            parentlayout = OpenMayaUI.MQtUtil.fullName( long(sip.unwrapinstance(self.formColorLayout)) )
        else:
            parentlayout = OpenMayaUI.MQtUtil.fullName( long(shiboken.getCppPointer(self.formColorLayout)[0]) )
        layout = cmds.gridLayout(numberOfColumns=8,cellWidthHeight=[45,25],parent=parentlayout)
        
        for i in self.colorList:
            if len(i) == 3:
                button = cmds.button( l='None', bgc=tuple(i[1]),parent=layout, c=('import maya.cmds as cmds\nselection = cmds.ls(sl=True)\nfor select in selection:\n\tshapes = cmds.listRelatives(select,ad=True,s=True,f=True)\n\tfor node in shapes:\n\t\tcmds.setAttr((node+".overrideEnabled"), 0)'))
            else:
                button = cmds.button( l='', bgc=tuple(i[1]),parent=layout, c=('import maya.cmds as cmds\nselection = cmds.ls(sl=True)\nfor select in selection:\n\tshapes = cmds.listRelatives(select,ad=True,s=True,f=True )\n\tfor node in shapes:\n\t\tcmds.setAttr((node+".overrideEnabled"), 1)\n\t\tcmds.setAttr((node+".overrideColor"),' + str(i[0]) + ')'))
    
    def DisplayType(self, Type, *args):
        selection         = cmds.ls(sl=True)
        if len(selection) == 0:
            cmds.warning('warning, nothing selected to copy!')
        else:
            for Selected in selection:
                cmds.delete(Selected, ch=True)
                shapeNode = cmds.listRelatives(Selected,ad=True, s=True)
                for shapes in shapeNode:
                    cmds.setAttr((shapes + ".overrideEnabled"), 1)
                    cmds.setAttr((shapes + ".overrideDisplayType"), Type)
                    if Type == 0:
                        cmds.setAttr((shapes + ".overrideEnabled"), 0)
   
    def __readOutFiles(self,*args):
        parentLayout = self.presetsTreeWidget
        parentLayout.clear()

        path = FilePath+ 'Curves/'
        listing = os.listdir(path)
        for infile in listing:
            if not '.py' in infile:
                continue
            file = infile.split('.')

            f = open((path + infile), "r")
            text = f.read()

            item    = QtGui.QTreeWidgetItem()
            item.setText(0, str(file[0]))
            try:
                icon = QtGui.QIcon(path+file[0]+".png")
                item.setIcon(0, icon)
            except:
                pass
            parentLayout.addTopLevelItem(item)  

    def __handleChanged(self):
        getItem = self.presetsTreeWidget.selectedItems()
        path = FilePath+ 'Curves/'
        if not getItem == []:
            inObject = getItem[0].text(0)
            try:
                icon = QtGui.QPixmap(path+ inObject+'.png')
                self.iconButton.setPixmap(icon)
            except:
                pass

    def __doubleClicked(self):
        getItem = self.presetsTreeWidget.selectedItems()
        path = FilePath+ 'Curves/'
        if not getItem == []:
            inObject = getItem[0].text(0)
            
            f = open((path + inObject + '.py'), "r")
            text = f.read()
            exec (text)

    def __ButtonEnable(self):
        InputText = self.TextlineEdit.text()
        
        if InputText == "":
            self.CreateTextButton.setEnabled(False)
        else:
            self.CreateTextButton.setEnabled(True)
    
    def __createText(self, *args):
        InputText = self.TextlineEdit.text()
        FontType  = self.FontComboBox.currentText()
        if str(InputText) == "":
            cmds.error('No text put in the textfield!')
        else:
            self.createTextController(str(InputText),str(FontType))
    
    def createTextController(self, inText, inFont):
        createdText = cmds.textCurves( f=inFont, t=inText )
        list = cmds.listRelatives( createdText[0], ad=True)
        list1 = []
        for i in list:
            if 'curve' in i and 'Shape' not in i:
                list1.append(i)
        for i in xrange(len(list1)):
            cmds.parent(list1[i],w=True)
            cmds.makeIdentity(list1[i], apply=True, t=1, r=1, s=1, n=0)
            if i == 0:
                parentGuide = list1[0]
            else:
                shape = cmds.listRelatives(list1[i], s=True) 
                cmds.move(0,0,0,(list1[i]+'.scalePivot'),(list1[i]+'.rotatePivot'))
                cmds.parent(shape,parentGuide,add=True,s=True)
                cmds.delete(list1[i])
        cmds.delete(createdText[0])
        cmds.xform(list1[0], cp=True)    
        worldPosition     = cmds.xform(list1[0], q=True, piv=True, ws=True)
        cmds.xform(list1[0], t=(-worldPosition[0],-worldPosition[1],-worldPosition[2]))
        cmds.makeIdentity(list1[0], apply=True, t=1, r=1, s=1, n=0)
        cmds.select(list1[0])
    
    def __dockWindow_Delete(self, *args):                                                                                    
        window_name     = 'Control_Creator'
        dock_control     = 'Control_Creator_Dock'
        
            # Remove window
        if cmds.window( window_name, exists=True ):
            cmds.deleteUI( window_name )
        
            # Remove dock
        if (cmds.dockControl(dock_control, q=True, ex=True)):
            cmds.deleteUI(dock_control)   

def StartUI():
    if default == "pyqt4":
        MayaWindowPtr = sip.wrapinstance(long( OpenMayaUI.MQtUtil.mainWindow() ), QtCore.QObject)
    else:
        MayaWindowPtr = shiboken.wrapInstance(long(OpenMayaUI.MQtUtil.mainWindow()), QtGui.QMainWindow)
    
    window_name     = 'Control_Creator'
    dock_control     = 'Control_Creator_Dock'
    
    if cmds.window( window_name, exists=True ):
        cmds.deleteUI( window_name )
    Window = Control_CreatorUI(MayaWindowPtr)
    Window.setObjectName(window_name)
    if (cmds.dockControl(dock_control, q=True, ex=True)):
        cmds.deleteUI(dock_control)
    AllowedAreas = ['right', 'left']
    cmds.dockControl(dock_control,aa=AllowedAreas, a='right', floating=False, content=window_name, label='Control Creator')
    