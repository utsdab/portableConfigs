# importing libraries:
import maya.cmds as cmds
import maya.mel as mel

# global variables to this module:    
CLASS_NAME = "UpdateRigInfo"
TITLE = "m057_updateRigInfo"
DESCRIPTION = "m058_updateRigInfoDesc"
ICON = "/Icons/dp_updateRigInfo.png"


class UpdateRigInfo():
    def __init__(self, dpUIinst, langDic, langName):
        # redeclaring variables
        self.dpUIinst = dpUIinst
        self.langDic = langDic
        self.langName = langName
        # call main function
        self.dpMain(self)
    
    
    def dpMain(self, *args):
        """ Main function.
            Just call the update function.
        """
        self.updateRigInfoLists()
    
    
    def updateRigInfoLists(self, *args):
        """
        """
        ctrlList = cmds.ls("*_Ctrl")
        ctrlString = ""
        if ctrlList:
            for i, item in enumerate(ctrlList):
                ctrlString = ctrlString + str(item)
                if i < len(ctrlList):
                    ctrlString = ctrlString + ";"
            cmds.setAttr("Master_Ctrl.controlList", ctrlString, type="string")
        
        meshList = cmds.ls("*_Mesh")
        meshString = ""
        if meshList:
            for i, item in enumerate(meshList):
                meshString = meshString + str(item)
                if i < len(meshList):
                    meshString = meshString + ";"
            cmds.setAttr("Master_Ctrl.geometryList", meshString, type="string")
        print "Control List = ", ctrlString
        print "Mesh List    = ", meshString
