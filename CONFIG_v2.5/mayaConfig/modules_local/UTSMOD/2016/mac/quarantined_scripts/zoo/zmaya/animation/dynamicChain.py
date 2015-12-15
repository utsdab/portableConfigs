
from maya import cmds

from ...str_utils import camelCaseToNice
from ...vectors import Axis

from ..apiExtensions import getNodesCreatedBy
from ..baseMelUI import *
from ..maya_decorators import d_undoBlock, d_noAutoKey
from ..mel_utils import MEL, traceWarning, traceError
from .. import align_utils

from . import clip

class DynamicChain(object):
    """
    provides a high level interface to interact with existing dynamic chain setups in the current scene

    to create a new dynamic chain instance, use DynamicChain.Create
    to instantiate a previously created chain use DynamicChain(dynamicChainNode)

    the dynamic chain node simply describes what nodes to create the dynamic chain on, and provide a place
    to store persistent properties.  To build the dynamic chain setup you need to call dynChain.construct()
    on a DynamicChain instance.  Similarly you can turn a dynamic chain "off" by calling dynChain.mute()
    """

    # used to identify the sets used by this tool to describe the dynamic
    # chain setups
    SET_NODE_IDENTIFIER = 'zooDynamicChain'

    @classmethod
    @d_undoBlock
    def Create(cls, objs):
        """
        constructs a new DynamicChain instance

        NOTE: this only creates the description of the dynamic chain - if you want the dynamic chain to be
        "turned on", you'll need to call construct() on the instance returned
        """
        if not objs:
            raise ValueError("Must provide a list of objects to construct the DynamicChain on")

        node = cmds.sets(empty=True, text=cls.SET_NODE_IDENTIFIER)
        node = cmds.rename(node, '%s_dynChain#' % objs[0].split('|')[-1].split(':')[-1])

        cmds.addAttr(node, ln='transforms', at='message', indexMatters=True, multi=True)
        for n, obj in enumerate(objs):
            cmds.connectAttr('%s.message' % obj, '%s.transforms[%d]' % (node, n))

        # add attributes to the set node - adding them to the set means user set
        # attributes are preserved across muting and unmuting of the chain
        cmds.addAttr(node, ln='spring', at='double', min=0, max=0.5, dv=0.05, keyable=True)
        cmds.addAttr(node, ln='mass', at='double', min=1, max=50, dv=10, keyable=True)
        cmds.addAttr(node, ln='drag', at='double', min=0, max=1, dv=0.1, keyable=True)
        cmds.addAttr(node, ln='damping', at='double', min=0, max=0.3, dv=0.05, keyable=True)
        cmds.addAttr(node, ln='gravity', at='double', min=0, max=5000, dv=0, keyable=True)
        cmds.addAttr(node, ln='proxyRoot', at='message')

        self = cls(node)

        return self

    @classmethod
    def Iter(cls):
        """
        iterates over all dynamic chains in the current scene
        """
        for node in cmds.ls(type='objectSet'):
            if cmds.sets(node, q=True, text=True) == cls.SET_NODE_IDENTIFIER:
                yield cls(node)

    def __init__(self, container):
        self._node = container

    def getNode(self):
        return self._node

    def getObjs(self):
        """
        returns the objects involved in the dynamic chain
        """
        objs = []
        nControls = cmds.getAttr('%s.transforms' % self._node, size=True)
        for n in range(nControls):
            cons = cmds.listConnections('%s.transforms[%d]' % (self._node, n), d=False)
            if cons:
                objs.append(cons[0])

        return objs

    def getProxyRoot(self):
        """
        returns the
        """
        cons = cmds.listConnections('%s.proxyRoot' % self._node, d=False)
        if cons:
            return cons[0]

        return None

    @d_undoBlock
    def construct(self):
        """
        builds the actual dynamic hair network
        """
        setNode = self._node
        objs = self.getObjs()

        # before we do anything, check to see whether the selected objects have
        # any incoming connections
        warnAboutDisconnections = True
        for obj in objs:

            # check for incoming connections; if it has any, remove them
            for chan in ('t', 'r'):
                for ax in Axis.BASE_AXES:
                    cons = cmds.listConnections('%s.%s%s' % (obj, chan, ax), d=False)
                    if cons:
                        warnAboutDisconnections = True
                        if cmds.objectType(cons[0], isAType='animCurve'):
                            cmds.delete(cons[0])
                        else:
                            raise TypeError("The object %s has non anim curve incoming connections - aborting! "
                                            "Please remove connections manually before proceeding" % obj)

        if warnAboutDisconnections:
            traceWarning("Some of the objects had incoming connections (probably from "
                         "animation). These connections have been broken!  undo if you want them back")

        # wrap the creation of the nodes in a function - below this we execute
        # this function via a wrapper which returns a list of new nodes created
        # this is done so we can easily capture the nodes created and store them
        # in the set that describes this dynamic chain
        def doCreate():
            positions = []
            for obj in objs:
                positions.append(cmds.xform(obj, q=True, ws=True, rp=True))

            # the objs may not be in the same hierarchy, so create a proxy chain
            # that IS in a heirarchy
            proxyJoints = []
            for obj in objs:
                cmds.select(cl=True)
                j = cmds.createNode('joint')
                j = cmds.rename(j, '%s_dynChainProxy#' % obj.split(':')[-1].split('|')[-1])
                if proxyJoints:
                    cmds.parent(j, proxyJoints[-1])

                cmds.delete(cmds.parentConstraint(obj, j))
                proxyJoints.append(j)

                # constrain the original to the proxy
                align_utils.parentConstraint(j, obj)

            # hook up the proxy root to a special message attribute so we can
            # easily find the proxy chain again for things like baking etc...
            cmds.connectAttr('%s.message' % proxyJoints[0], '%s.proxyRoot' % setNode)

            # build a linear curve
            linearCurve = cmds.curve(d=1, p=positions)
            linearCurveShape = cmds.listRelatives(linearCurve, s=True, pa=True)[0]
            cmds.select(linearCurve)
            MEL.makeCurvesDynamicHairs(1, 0, 1)

            # find the dynamic curve shape
            cons = cmds.listConnections('%s.local' % linearCurveShape, s=False)
            if not cons:
                traceError("Cannot find follicle")
                return

            follicleShape = cons[0]
            cons = cmds.listConnections('%s.outHair' % follicleShape, s=False)
            if not cons:
                traceError("Cannot find hair system!")
                return

            hairSystemNode = cons[0]
            cmds.delete('%s.startFrame' % hairSystemNode, icn=True)
            cmds.setAttr('%s.startFrame' % hairSystemNode, cmds.playbackOptions(q=True, min=True))
            cons = cmds.listConnections('%s.outCurve' % follicleShape, s=False)
            if not cons:
                traceError("Cannot find out curve!")
                return

            # grab the dynamic curve's shape
            dynamicCurve = cons[0]
            dynamicCurveParent = cmds.listRelatives(dynamicCurve, p=True, pa=True)

            cmds.select(dynamicCurve)
            MEL.displayHairCurves("current", 1)

            # find the nucleus solver
            cons = cmds.listConnections('%s.nextState' % hairSystemNode, d=False)
            if not cons:
                traceError("Cannot find nucleus solver!")
                return

            nucleusSolver = cons[0]

            follicle = cmds.listRelatives(linearCurve, p=True, pa=True)[0]
            objParent = cmds.listRelatives(objs[0], p=True, pa=True)
            if objParent:
                objParent = objParent[0]
                cmds.parent(follicle, objParent)
                cmds.parent(proxyJoints[0], objParent)

            cmds.setAttr('%s.overrideDynamics' % follicle, 1)
            cmds.setAttr('%s.pointLock' % follicle, 1)

            # hook up all the attributes
            cmds.connectAttr('%s.spring' % setNode, '%s.startCurveAttract' % hairSystemNode)
            cmds.connectAttr('%s.mass' % setNode, '%s.mass' % hairSystemNode)
            cmds.connectAttr('%s.drag' % setNode, '%s.motionDrag' % hairSystemNode)
            cmds.connectAttr('%s.damping' % setNode, '%s.damp' % hairSystemNode)
            cmds.connectAttr('%s.gravity' % setNode, '%s.gravity' % nucleusSolver)

            cmds.ikHandle(
                sj=proxyJoints[0], ee=proxyJoints[-1],
                curve=dynamicCurve, sol='ikSplineSolver', ccv=False)

            # for some reason the dynamic curve gets re-parented by the ikHandle
            # command (weird) so set the parent back to what it was originally
            cmds.parent(dynamicCurve, dynamicCurveParent)

        newNodes, returnValue = getNodesCreatedBy(doCreate)

        # stuff the nodes created into the set that describes this dynamic chain
        # just add transform nodes...
        for aNode in newNodes:
            if cmds.objectType(aNode, isAType='transform'):
                cmds.sets(aNode, e=True, add=setNode)

    @d_undoBlock
    def mute(self):
        """
        deletes the hair nodes but retains the settings and objects involved in the hair
        """

        # we need to lock the set node before deleting its contents otherwise
        # maya will delete the set
        cmds.lockNode(self._node, lock=True)

        # now delete the set contents
        cmds.delete(cmds.sets(self._node, q=True))

        # finally unlock the node again
        cmds.lockNode(self._node, lock=False)

    def getMuted(self):
        """
        returns whether this dynamic chain is muted or not
        """
        return not bool(cmds.sets(self._node, q=True))

    def setMuted(self, state):
        if state:
            self.mute()
        else:
            self.construct()

    @d_undoBlock
    @d_noAutoKey
    def bake(self, keyEveryNthFrame=4):
        """
        if this dynamic chain isn't muted, this will bake the motion to keyframes and mute
        the dynamic hair

        keyEveryNthFrame describes how often keys are baked - set to 1 to bake every frame
        """

        start, end = cmds.playbackOptions(q=True, min=True), cmds.playbackOptions(q=True, max=True)

        # get the objects and initialize a list for translate/rotate values
        objs = self.getObjs()
        trValues = [list() for o in objs]

        # maya's bakeResults/simulation is FUCKING retarded... So bake manually
        for t in clip.iterAtTimes(range(start, end + 1)):
            for n, obj in enumerate(objs):
                tr = t, cmds.getAttr('%s.t' % obj)[0], cmds.getAttr('%s.r' % obj)[0]
                trValues[n].append(tr)

        # turn this chain off
        self.mute()

        # generate the frames to key
        timesToKey = list(range(start, end + 1, keyEveryNthFrame))
        if timesToKey[-1] != end:
            timesToKey.append(end)

        timesToKey = set(timesToKey)

        # now set key values
        for n, tr in enumerate(trValues):
            for time, t, r in tr:
                if time in timesToKey:
                    cmds.setAttr('%s.t' % objs[n], *t)
                    cmds.setAttr('%s.r' % objs[n], *r)
                    cmds.setKeyframe(objs[n], t=time, at=('t', 'r'))

    @d_undoBlock
    def delete(self):
        """
        deletes the dynamic chain
        """
        nodesInSet = cmds.sets(self._node, q=True) or []
        for node in nodesInSet:
            if cmds.objExists(node):
                cmds.delete(node)

        # the node shouldn't actually exist anymore - maya should have deleted
        # it automatically after the last object in it was deleted.  but in the
        # interests of thoroughness, lets make sure.  who knows what sort of
        # crazy corner cases exist
        if cmds.objExists(self._node):

            # check to see if the set node is referenced
            if not cmds.referenceQuery(self._node, inr=True):
                cmds.delete(self._node)

class DynamicChainScrollList(MelObjectScrollList):
    def itemAsStr(self, item):
        isMuted = item.getMuted()
        if isMuted:
            return '[ muted ] %s' % item.getNode()

        return item.getNode()

class DynamicChainEditor(MelColumnLayout):
    def __init__(self, parent):
        self._chain = None
        MelColumnLayout.__init__(self, parent)

    def setChain(self, dynamicChain):
        self.clear()
        self._chain = dynamicChain

        if dynamicChain is None:
            return

        dynChainNode = dynamicChain.getNode()
        MelLabel(self, l='Editing Dynamic Chain: %s' % dynChainNode)
        MelSeparator(self, h=15)

        attrs = cmds.listAttr(dynChainNode, k=True) or []
        for attr in attrs:
            attrpath = '%s.%s' % (dynChainNode, attr)

            niceAttrName = camelCaseToNice(attr)

            # query the attribute type and build UI for the types we care about
            # presenting to the user
            attrType = cmds.getAttr(attrpath, type=True)
            ui = None
            if attrType == 'bool':
                ui = MelCheckBox(self, l=niceAttrName)
            elif attrType == 'double':
                min, max = cmds.addAttr(attrpath, q=True, min=True), cmds.addAttr(attrpath, q=True, max=True)
                ui = LabelledFloatSlider(self, min, max, ll=niceAttrName, llw=65).getWidget()

            if ui is None:
                continue

            cmds.connectControl(ui, attrpath)

        MelSeparator(self, h=15)

        hLayout = MelHSingleStretchLayout(self)
        lbl = MelLabel(hLayout, l='Key Every N Frames')
        self.UI_nFrame = MelIntField(hLayout, v=3, min=1, max=15, step=1)
        self.UI_bake = MelButton(hLayout, l='Bake To Keys', c=self.on_bake)

        hLayout(e=True, af=((lbl, 'top', 0), (lbl, 'bottom', 0)))
        hLayout.padding = 10
        hLayout.setStretchWidget(self.UI_bake)
        hLayout.layout()

    ### EVENT HANDLERS ###
    def on_bake(self, _=None):
        if self._chain:
            self._chain.bake(self.UI_nFrame.getValue())

        self.sendEvent('on_chainBaked')

class DynamicChainLayout(MelHSingleStretchLayout):
    def __init__(self, parent):
        super(DynamicChainLayout, self).__init__(parent)

        vLayout = MelVSingleStretchLayout(self)

        self.UI_dynamicChains = DynamicChainScrollList(vLayout)
        self.UI_dynamicChains.setWidth(175)
        self.UI_dynamicChains.setChangeCB(self.on_chainListSelectionChange)

        self.UI_create = MelButton(vLayout, l='Create Chain From Selection', c=self.on_create)
        self.UI_mute = MelButton(vLayout, l='Toggle Mute On Highlighted', c=self.on_mute)
        MelSeparator(vLayout, h=15)
        self.UI_delete = MelButton(vLayout, l='Delete Highlighted', c=self.on_delete)

        vLayout.padding = 0
        vLayout.setStretchWidget(self.UI_dynamicChains)
        vLayout.layout()

        self.UI_editor = DynamicChainEditor(self)

        self.padding = 10
        self.expand = True
        self.setStretchWidget(self.UI_editor)
        self.layout()

        self.populate()

        #hook up callbacks
        self.setSelectionChangeCB(self.on_sceneSelectionChange)
        self.setSceneChangeCB(self.on_sceneChange)

        #run the selection callback to update the UI
        self.on_sceneSelectionChange()

    def populate(self):
        initialSelection = self.UI_dynamicChains.getSelectedItems()

        self.UI_dynamicChains.clear()
        chains = list(DynamicChain.Iter())
        for dynamicChain in chains:
            self.UI_dynamicChains.append(dynamicChain)

        if initialSelection:
            if initialSelection[0] in self.UI_dynamicChains:
                self.UI_dynamicChains.selectByValue(initialSelection[0], False)
        elif chains:
            self.UI_dynamicChains.selectByValue(chains[0], False)

        #run the highlight callback to update the UI
        self.on_chainListSelectionChange()

    ### EVENT HANDLERS ###
    def on_sceneSelectionChange(self, _=None):
        areNodesSelected = bool(cmds.ls(sl=True, type='transform'))
        self.UI_create.setEnabled(areNodesSelected)

    def on_sceneChange(self, _=None):
        self.populate()

    def on_chainListSelectionChange(self, _=None):
        sel = self.UI_dynamicChains.getSelectedItems()
        areItemsSelected = bool(sel)

        if areItemsSelected:
            self.UI_editor.setChain(sel[0])
        else:
            self.UI_editor.setChain(None)

        # set enable state on UI that is sensitive to whether we have
        # highlighted items in the dynamic chain list
        self.UI_mute.setEnabled(areItemsSelected)
        self.UI_delete.setEnabled(areItemsSelected)

    def on_create(self, _=None):
        selection = cmds.ls(sl=True, type='transform')
        dynamicChain = DynamicChain.Create(selection)
        dynamicChain.setMuted(False)
        self.populate()

        self.UI_dynamicChains.selectByValue(dynamicChain, True)

    def on_mute(self, _=None):
        sel = self.UI_dynamicChains.getSelectedItems()
        if sel:
            muteStateToSet = not sel[0].getMuted()
            for s in sel:
                s.setMuted(muteStateToSet)

        self.populate()

    def on_delete(self, _=None):
        sel = self.UI_dynamicChains.getSelectedItems()
        if sel:
            for s in sel:
                s.delete()

        self.populate()

    def on_chainBaked(self):
        self.populate()

class DynamicChainWindow(BaseMelWindow):
    WINDOW_NAME = 'zooDynamicChainMaker'
    WINDOW_TITLE = 'Dynamic Chain Maker'

    DEFAULT_MENU = None
    DEFAULT_SIZE = 500, 325
    FORCE_DEFAULT_SIZE = True

    def __init__(self):
        super(DynamicChainWindow, self).__init__()

        DynamicChainLayout(self)
        self.show()

#end
