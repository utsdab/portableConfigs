# importing libraries:
import maya.cmds as cmds
import dpControls as ctrls
import dpUtils as utils
import dpBaseClass as Base
import dpLayoutClass as Layout

# global variables to this module:    
CLASS_NAME = "Finger"
TITLE = "m007_finger"
DESCRIPTION = "m008_fingerDesc"
ICON = "/Icons/dp_finger.png"


class Finger(Base.StartClass, Layout.LayoutClass):
    def __init__(self, dpUIinst, langDic, langName, userGuideName):
        Base.StartClass.__init__(self, dpUIinst, langDic, langName, userGuideName, CLASS_NAME, TITLE, DESCRIPTION, ICON)
        pass
    
    
    def createModuleLayout(self, *args):
        Base.StartClass.createModuleLayout(self)
        Layout.LayoutClass.basicModuleLayout(self)
    
    
    def createGuide(self, *args):
        Base.StartClass.createGuide(self)
        # Custom GUIDE:
        cmds.addAttr(self.moduleGrp, longName="nJoints", attributeType='long')
        cmds.setAttr(self.moduleGrp+".nJoints", 1)
        
        cmds.setAttr(self.moduleGrp+".moduleNamespace", self.moduleGrp[:self.moduleGrp.rfind(":")], type='string')
        
        self.cvJointLoc = ctrls.cvJointLoc(ctrlName=self.guideName+"_JointLoc1", r=0.3)
        self.jGuide1 = cmds.joint(name=self.guideName+"_JGuide1", radius=0.001)
        cmds.setAttr(self.jGuide1+".template", 1)
        cmds.parent(self.jGuide1, self.moduleGrp, relative=True)
        
        self.cvEndJoint = ctrls.cvLocator(ctrlName=self.guideName+"_JointEnd", r=0.2)
        cmds.parent(self.cvEndJoint, self.cvJointLoc)
        cmds.setAttr(self.cvEndJoint+".tz", 1.3)
        self.jGuideEnd = cmds.joint(name=self.guideName+"_JGuideEnd", radius=0.001)
        cmds.setAttr(self.jGuideEnd+".template", 1)
        cmds.transformLimits(self.cvEndJoint, tz=(0.01, 1), etz=(True, False))
        ctrls.setLockHide([self.cvEndJoint], ['rx', 'ry', 'rz', 'sx', 'sy', 'sz'])
        
        cmds.parent(self.cvJointLoc, self.moduleGrp)
        cmds.parent(self.jGuideEnd, self.jGuide1)
        ctrls.directConnect(self.cvJointLoc, self.jGuide1, ['tx', 'ty', 'tz', 'rx', 'ry', 'rz'])
        ctrls.directConnect(self.cvEndJoint, self.jGuideEnd, ['tx', 'ty', 'tz', 'rx', 'ry', 'rz'])
        
        # change the number of falanges to 3:
        self.changeJointNumber(3)
        
        # create a base cvLoc to start the finger joints:
        self.cvBaseJoint = ctrls.cvLocator(ctrlName=self.guideName+"_JointLoc0", r=0.2)
        cmds.setAttr(self.cvBaseJoint+".translateZ", -1)
        cmds.parent(self.cvBaseJoint, self.moduleGrp)
        
        # transform cvLocs in order to put as a good finger guide:
        cmds.setAttr(self.moduleGrp+".rotateX", 90)
        cmds.setAttr(self.moduleGrp+".rotateZ", 90)
    
    
    def changeJointNumber(self, enteredNJoints, *args):
        """ Edit the number of joints in the guide.
        """
        utils.useDefaultRenderLayer()
        # get the number of joints entered by user:
        if enteredNJoints == 0:
            try:
                self.enteredNJoints = cmds.intField(self.nJointsIF, query=True, value=True)
            except:
                return
        else:
            self.enteredNJoints = enteredNJoints
        # get the number of joints existing:
        self.currentNJoints = cmds.getAttr(self.moduleGrp+".nJoints")
        # start analisys the difference between values:
        if self.enteredNJoints != self.currentNJoints:
            # unparent temporarely the Ends:
            self.cvEndJoint = self.guideName+"_JointEnd"
            cmds.parent(self.cvEndJoint, world=True)
            self.jGuideEnd = (self.guideName+"_JGuideEnd")
            cmds.parent(self.jGuideEnd, world=True)
            # verify if the nJoints is greather or less than the current
            if self.enteredNJoints > self.currentNJoints:
                for n in range(self.currentNJoints+1, self.enteredNJoints+1):
                    # create another N cvJointLoc:
                    self.cvJointLoc = ctrls.cvJointLoc( ctrlName=self.guideName+"_JointLoc"+str(n), r=0.2 )
                    # set its nJoint value as n:
                    cmds.setAttr(self.cvJointLoc+".nJoint", n)
                    # parent it to the lastGuide:
                    cmds.parent(self.cvJointLoc, self.guideName+"_JointLoc"+str(n-1), relative=True)
                    cmds.setAttr(self.cvJointLoc+".translateZ", 1)
                    cmds.setAttr(self.cvJointLoc+".rotateY", -1)
                    # create a joint to use like an arrowLine:
                    self.jGuide = cmds.joint(name=self.guideName+"_JGuide"+str(n), radius=0.001)
                    cmds.setAttr(self.jGuide+".template", 1)
                    cmds.parent(self.jGuide, self.guideName+"_JGuide"+str(n-1))
                    ctrls.directConnect(self.cvJointLoc, self.jGuide, ['tx', 'ty', 'tz', 'rx', 'ry', 'rz'])
            elif self.enteredNJoints < self.currentNJoints:
                # re-define cvEndJoint:
                self.cvJointLoc = self.guideName+"_JointLoc"+str(self.enteredNJoints)
                self.cvEndJoint = self.guideName+"_JointEnd"
                self.jGuide = self.guideName+"_JGuide"+str(self.enteredNJoints)
                # re-parent the children guides:
                childrenGuideBellowList = utils.getGuideChildrenList(self.cvJointLoc)
                if childrenGuideBellowList:
                    for childGuide in childrenGuideBellowList:
                        cmds.parent(childGuide, self.cvJointLoc)
                # delete difference of nJoints:
                cmds.delete(self.guideName+"_JointLoc"+str(self.enteredNJoints+1))
                cmds.delete(self.guideName+"_JGuide"+str(self.enteredNJoints+1))
            # re-parent cvEndJoint:
            cmds.parent(self.cvEndJoint, self.cvJointLoc)
            cmds.setAttr(self.cvEndJoint+".tz", 1.3)
            cmds.parent(self.jGuideEnd, self.jGuide)
            # actualise the nJoints in the moduleGrp:
            cmds.setAttr(self.moduleGrp+".nJoints", self.enteredNJoints)
            self.currentNJoints = self.enteredNJoints
            # re-build the preview mirror:
            Layout.LayoutClass.createPreviewMirror(self)
        cmds.select(self.moduleGrp)
    
    
    def rigModule(self, *args):
        Base.StartClass.rigModule(self)
        # verify if the guide exists:
        if cmds.objExists(self.moduleGrp):
            try:
                hideJoints = cmds.checkBox('hideJointsCB', query=True, value=True)
            except:
                hideJoints = 1
            # declaring lists to send information for integration:
            self.scalableGrpList, self.ikCtrlZeroList = [], []
            # start as no having mirror:
            sideList = [""]
            # analisys the mirror module:
            self.mirrorAxis = cmds.getAttr(self.moduleGrp+".mirrorAxis")
            if self.mirrorAxis != 'off':
                # get rigs names:
                self.mirrorNames = cmds.getAttr(self.moduleGrp+".mirrorName")
                # get first and last letters to use as side initials (prefix):
                sideList = [ self.mirrorNames[0]+'_', self.mirrorNames[len(self.mirrorNames)-1]+'_' ]
                for s, side in enumerate(sideList):
                    duplicated = cmds.duplicate(self.moduleGrp, name=side+self.userGuideName+'_Guide_Base')[0]
                    allGuideList = cmds.listRelatives(duplicated, allDescendents=True)
                    for item in allGuideList:
                        cmds.rename(item, side+self.userGuideName+"_"+item)
                    self.mirrorGrp = cmds.group(name="Guide_Base_Grp", empty=True)
                    cmds.parent(side+self.userGuideName+'_Guide_Base', self.mirrorGrp, absolute=True)
                    # re-rename grp:
                    cmds.rename(self.mirrorGrp, side+self.userGuideName+'_'+self.mirrorGrp)
                    # do a group mirror with negative scaling:
                    if s == 1:
                        for axis in self.mirrorAxis:
                            cmds.setAttr(side+self.userGuideName+'_'+self.mirrorGrp+'.scale'+axis, -1)
            else: # if not mirror:
                duplicated = cmds.duplicate(self.moduleGrp, name=self.userGuideName+'_Guide_Base')[0]
                allGuideList = cmds.listRelatives(duplicated, allDescendents=True)
                for item in allGuideList:
                    cmds.rename(item, self.userGuideName+"_"+item)
                self.mirrorGrp = cmds.group(self.userGuideName+'_Guide_Base', name="Guide_Base_Grp", relative=True)
                # re-rename grp:
                cmds.rename(self.mirrorGrp, self.userGuideName+'_'+self.mirrorGrp)
            # store the number of this guide by module type
            dpAR_count = utils.findModuleLastNumber(CLASS_NAME, "dpAR_type") + 1
            # run for all sides
            for s, side in enumerate(sideList):
                self.base = side+self.userGuideName+'_Guide_Base'
                # get the number of joints to be created:
                self.nJoints = cmds.getAttr(self.base+".nJoints")
                for n in range(0, self.nJoints+1):
                    cmds.select(clear=True)
                    # declare guide:
                    self.guide = side+self.userGuideName+"_Guide_JointLoc"+str(n)
                    # create a joint:
                    self.jnt = cmds.joint(name=side+self.userGuideName+"_"+str(n)+"_Jnt", scaleCompensate=False)
                    cmds.addAttr(self.jnt, longName='dpAR_joint', attributeType='float', keyable=False)
                    # create a control:
                    if n == 1:
                        self.ctrl = ctrls.cvFinger(ctrlName=side+self.userGuideName+"_"+str(n)+"_Ctrl", r=self.ctrlRadius)
                        utils.originedFrom(objName=self.ctrl, attrString=self.base+";"+self.guide)
                        # edit the mirror shape to a good direction of controls:
                        if s == 1:
                            if self.mirrorAxis == 'X':
                                cmds.setAttr(self.ctrl+'.rotateZ', 180)
                            elif self.mirrorAxis == 'Y':
                                cmds.setAttr(self.ctrl+'.rotateY', 180)
                            elif self.mirrorAxis == 'Z':
                                cmds.setAttr(self.ctrl+'.rotateZ', 180)
                            elif self.mirrorAxis == 'XY':
                                cmds.setAttr(self.ctrl+'.rotateX', 180)
                            elif self.mirrorAxis == 'XYZ':
                                cmds.setAttr(self.ctrl+'.rotateZ', 180)
                            cmds.makeIdentity(self.ctrl, apply=True, translate=False, rotate=True, scale=False)
                    else:
                        self.ctrl = cmds.circle(name=side+self.userGuideName+"_"+str(n)+"_Ctrl", degree=1, normal=(0, 0, 1), r=self.ctrlRadius, s=6, ch=False)[0]
                        utils.originedFrom(objName=self.ctrl, attrString=self.guide)
                    # hide visibility attribute:
                    cmds.setAttr(self.ctrl+'.visibility', keyable=False)
                    # put another group over the control in order to use this to connect values from mainFingerCtrl:
                    self.sdkGrp = cmds.group(self.ctrl, name=side+self.userGuideName+"_"+str(n)+"_SDKGrp")
                    if n == 1:
                        # change pivot of this group to control pivot:
                        pivotPos = cmds.xform(self.ctrl, query=True, worldSpace=True, rotatePivot=True)
                        cmds.setAttr(self.sdkGrp+'.rotatePivotX', pivotPos[0])
                        cmds.setAttr(self.sdkGrp+'.rotatePivotY', pivotPos[1])
                        cmds.setAttr(self.sdkGrp+'.rotatePivotZ', pivotPos[2])
                    # position and orientation of joint and control:
                    tempDel = cmds.parentConstraint(self.guide, self.jnt, maintainOffset=False)
                    cmds.delete(tempDel)
                    tempDel = cmds.parentConstraint(self.guide, self.sdkGrp, maintainOffset=False)
                    cmds.delete(tempDel)
                    # zeroOut controls:
                    utils.zeroOut([self.sdkGrp])
                # create end joint:
                self.cvEndJoint = side+self.userGuideName+"_Guide_JointEnd"
                self.endJoint = cmds.joint(name=side+self.userGuideName+"_JEnd", scaleCompensate=False)
                tempDel = cmds.parentConstraint(self.cvEndJoint, self.endJoint, maintainOffset=False)
                cmds.delete(tempDel)
                cmds.parent(self.endJoint, side+self.userGuideName+"_"+str(self.nJoints)+"_Jnt", absolute=True)
                # grouping:
                for n in range(0, self.nJoints+1):
                    self.jnt      = side+self.userGuideName+"_"+str(n)+"_Jnt"
                    self.ctrl     = side+self.userGuideName+"_"+str(n)+"_Ctrl"
                    self.zeroCtrl = side+self.userGuideName+"_"+str(n)+"_SDKGrp_Zero"
                    if n > 0:
                        if n == 1:
                            if not cmds.objExists(self.ctrl+'.ikFkBlend'):
                                cmds.addAttr(self.ctrl, longName="ikFkBlend", attributeType='float', keyable=True, minValue=0.0, maxValue=1.0, defaultValue=1.0)
                                self.ikFkRevNode = cmds.createNode("reverse", name=side+self.userGuideName+"_ikFk_Rev")
                                cmds.connectAttr(self.ctrl+".ikFkBlend", self.ikFkRevNode+".inputX", force=True)
                            if not cmds.objExists(self.ctrl+'.'+self.langDic[self.langName]['c_showControls']):
                                cmds.addAttr(self.ctrl, longName=self.langDic[self.langName]['c_showControls'], attributeType='float', keyable=True, minValue=0.0, maxValue=1.0, defaultValue=0.0)
                                self.ctrlShape0 = cmds.listRelatives(side+self.userGuideName+"_0_Ctrl", children=True, type='nurbsCurve')[0]
                                cmds.connectAttr(self.ctrl+"."+self.langDic[self.langName]['c_showControls'], self.ctrlShape0+".visibility", force=True)
                                cmds.setAttr(self.ctrl+'.'+self.langDic[self.langName]['c_showControls'], keyable=False, channelBox=True)
                            for j in range(1, self.nJoints+1):
                                cmds.addAttr(self.ctrl, longName=self.langDic[self.langName]['c_falange']+str(j), attributeType='float', keyable=True)
                        # parent joints as a simple chain (line)
                        self.fatherJnt = side+self.userGuideName+"_"+str(n-1)+"_Jnt"
                        cmds.parent(self.jnt, self.fatherJnt, absolute=True)
                        # parent zeroCtrl Group to the before ctrl:
                        self.fatherCtrl = side+self.userGuideName+"_"+str(n-1)+"_Ctrl"
                        cmds.parent(self.zeroCtrl, self.fatherCtrl, absolute=True)
                    # freeze joints rotation
                    cmds.makeIdentity(self.jnt, apply=True)
                    # create parent and scale constraints from ctrl to jnt:
                    cmds.parentConstraint(self.ctrl, self.jnt, maintainOffset=False, name=self.jnt+"_ParentConstraint")
                    cmds.scaleConstraint(self.ctrl, self.jnt, maintainOffset=False, name=self.jnt+"_ScaleConstraint")
                # make first falange be leads from base finger control:
                cmds.parentConstraint(side+self.userGuideName+"_0_Ctrl", side+self.userGuideName+"_1_SDKGrp_Zero", maintainOffset=True, name=side+self.userGuideName+"_1_SDKGrp_Zero"+"_ParentConstraint")
                cmds.scaleConstraint(side+self.userGuideName+"_0_Ctrl", side+self.userGuideName+"_1_SDKGrp_Zero", maintainOffset=True, name=side+self.userGuideName+"_1_SDKGrp_Zero"+"_ScaleConstraint")
                # connecting the attributes from control 1 to falanges rotate:
                for n in range(1, self.nJoints+1):
                    self.ctrl   = side+self.userGuideName+"_1_Ctrl"
                    self.sdkGrp = side+self.userGuideName+"_"+str(n)+"_SDKGrp"
                    cmds.connectAttr(self.ctrl+"."+self.langDic[self.langName]['c_falange']+str(n), self.sdkGrp+".rotateY", force=True)
                    if n > 1:
                        self.ctrlShape = cmds.listRelatives(side+self.userGuideName+"_"+str(n)+"_Ctrl", children=True, type='nurbsCurve')[0]
                        cmds.connectAttr(self.ctrl+"."+self.langDic[self.langName]['c_showControls'], self.ctrlShape+".visibility", force=True)
                # ik setup
                if self.nJoints == 2:
                    dup = cmds.duplicate(side+self.userGuideName+"_0_Jnt")[0]
                else:
                    dup = cmds.duplicate(side+self.userGuideName+"_1_Jnt")[0]
                childrenList = cmds.listRelatives(dup, children=True, allDescendents=True, fullPath=True)
                if childrenList:
                    for child in childrenList:
                        if not cmds.objectType(child) == "joint":
                            cmds.delete(child)
                jointList = cmds.listRelatives(dup, children=True, allDescendents=True, fullPath=True)
                for jointNode in jointList:
                    if "_Jnt" in jointNode[jointNode.rfind("|"):]:
                        cmds.rename(jointNode, jointNode[jointNode.rfind("|")+1:].replace("_Jnt", "_Ik_Jxt"))
                    elif "_JEnd" in jointNode[jointNode.rfind("|"):]:
                        cmds.rename(jointNode, jointNode[jointNode.rfind("|")+1:].replace("_JEnd", "_Ik_JEnd"))
                ikBaseJoint = cmds.rename(dup, dup.replace("_Jnt1", "_Ik_Jxt"))
                ikJointList = cmds.listRelatives(ikBaseJoint, children=True, allDescendents=True)
                ikJointList.append(ikBaseJoint)
                for ikJoint in ikJointList:
                    if not "_JEnd" in ikJoint:
                        if cmds.objExists(ikJoint+".dpAR_joint"):
                            cmds.deleteAttr(ikJoint+".dpAR_joint")
                        skinnedJoint = ikJoint.replace("_Ik_Jxt", "_Jnt")
                        thisCtrl = ikJoint.replace("_Ik_Jxt", "_Ctrl")
                        self.ctrl = side+self.userGuideName+"_1_Ctrl"
                        ikFkParent = cmds.parentConstraint(ikJoint, skinnedJoint, maintainOffset=True)[0]
                        cmds.connectAttr(self.ctrl+".ikFkBlend", ikFkParent+"."+thisCtrl+"W0", force=True)
                        cmds.connectAttr(self.ikFkRevNode+".outputX", ikFkParent+"."+ikJoint+"W1", force=True)
                if self.nJoints == 2:
                    ikHandleList = cmds.ikHandle(startJoint=side+self.userGuideName+"_0_Ik_Jxt", endEffector=side+self.userGuideName+"_"+str(self.nJoints)+"_Ik_Jxt", solver="ikRPsolver", name=side+self.userGuideName+"_IkHandle")
                else:
                    ikHandleList = cmds.ikHandle(startJoint=side+self.userGuideName+"_1_Ik_Jxt", endEffector=side+self.userGuideName+"_"+str(self.nJoints)+"_Ik_Jxt", solver="ikRPsolver", name=side+self.userGuideName+"_IkHandle")
                cmds.rename(ikHandleList[1], side+self.userGuideName+"_Effector")
                endIkHandleList = cmds.ikHandle(startJoint=side+self.userGuideName+"_"+str(self.nJoints)+"_Ik_Jxt", endEffector=side+self.userGuideName+"_Ik_JEnd", solver="ikSCsolver", name=side+self.userGuideName+"_EndIkHandle")
                cmds.rename(endIkHandleList[1], side+self.userGuideName+"_EndEffector")
                self.ikCtrl = ctrls.cvBox(ctrlName=side+self.userGuideName+"_Ik_Ctrl", r=self.ctrlRadius)
                cmds.addAttr(self.ikCtrl, longName='twist', attributeType='float', keyable=True)
                cmds.connectAttr(self.ikCtrl+".twist", ikHandleList[0]+".twist", force=True)
                cmds.delete(cmds.parentConstraint(side+self.userGuideName+"_Ik_JEnd", self.ikCtrl))
                self.ikCtrlZero = utils.zeroOut([self.ikCtrl])[0]
                self.ikCtrlZeroList.append(self.ikCtrlZero)
                cmds.connectAttr(self.ikFkRevNode+".outputX", self.ikCtrlZero+".visibility", force=True)
                for q in range(2, self.nJoints):
                    cmds.connectAttr(side+self.userGuideName+"_1_Ctrl.ikFkBlend", side+self.userGuideName+"_"+str(q)+"_Ctrl.visibility", force=True)
                cmds.parentConstraint(self.ikCtrl, ikHandleList[0], name=side+self.userGuideName+"_IkHandle_ParentConstraint", maintainOffset=True)
                cmds.parentConstraint(self.ikCtrl, endIkHandleList[0], name=side+self.userGuideName+"_EndIkHandle_ParentConstraint", maintainOffset=True)
                ikHandleGrp = cmds.group(ikHandleList[0], endIkHandleList[0], name=side+self.userGuideName+"_IkHandle_Grp")
                ctrls.setLockHide([self.ikCtrl], ['sx', 'sy', 'sz', 'v'])

                # create a masterModuleGrp to be checked if this rig exists:
                self.toCtrlHookGrp = cmds.group(self.ikCtrlZero, side+self.userGuideName+"_0_SDKGrp_Zero", side+self.userGuideName+"_1_SDKGrp_Zero", name=side+self.userGuideName+"_Control_Grp")
                if self.nJoints == 2:
                    self.toScalableHookGrp = cmds.group(side+self.userGuideName+"_0_Jnt", ikBaseJoint, ikHandleGrp, name=side+self.userGuideName+"_Joint_Grp")
                else:
                    self.toScalableHookGrp = cmds.group(side+self.userGuideName+"_0_Jnt", ikHandleGrp, name=side+self.userGuideName+"_Joint_Grp")
                self.scalableGrpList.append(self.toScalableHookGrp)
                self.toStaticHookGrp   = cmds.group(self.toCtrlHookGrp, self.toScalableHookGrp, name=side+self.userGuideName+"_Grp")
                # add hook attributes to be read when rigging integrated modules:
                utils.addHook(objName=self.toCtrlHookGrp, hookType='ctrlHook')
                utils.addHook(objName=self.toScalableHookGrp, hookType='scalableHook')
                utils.addHook(objName=self.toStaticHookGrp, hookType='staticHook')
                cmds.addAttr(self.toStaticHookGrp, longName="dpAR_name", dataType="string")
                cmds.addAttr(self.toStaticHookGrp, longName="dpAR_type", dataType="string")
                cmds.setAttr(self.toStaticHookGrp+".dpAR_name", self.userGuideName, type="string")
                cmds.setAttr(self.toStaticHookGrp+".dpAR_type", CLASS_NAME, type="string")
                # add module type counter value
                cmds.addAttr(self.toStaticHookGrp, longName='dpAR_count', attributeType='long', keyable=False)
                cmds.setAttr(self.toStaticHookGrp+'.dpAR_count', dpAR_count)
                # create a locator in order to avoid delete static group
                loc = cmds.spaceLocator(name=side+self.userGuideName+"_DO_NOT_DELETE")[0]
                cmds.parent(loc, self.toStaticHookGrp, absolute=True)
                cmds.setAttr(loc+".visibility", 0)
                ctrls.setLockHide([loc], ['tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'v'])
                if hideJoints:
                    cmds.setAttr(self.toScalableHookGrp+".visibility", 0)
                # delete duplicated group for side (mirror):
                cmds.delete(side+self.userGuideName+'_'+self.mirrorGrp)
            # finalize this rig:
            self.integratingInfo()
            cmds.select(clear=True)
        # delete UI (moduleLayout), GUIDE and moduleInstance namespace:
        self.deleteModule()
    
    
    def integratingInfo(self, *args):
        Base.StartClass.integratingInfo(self)
        """ This method will create a dictionary with informations about integrations system between modules.
        """
        self.integratedActionsDic = {
                                    "module": {
                                                "scalableGrpList" : self.scalableGrpList,
                                                "ikCtrlZeroList"  : self.ikCtrlZeroList,
                                                }
                                    }
