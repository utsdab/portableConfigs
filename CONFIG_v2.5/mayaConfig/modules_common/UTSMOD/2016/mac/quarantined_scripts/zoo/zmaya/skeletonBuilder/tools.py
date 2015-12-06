
from maya import cmds

from ... import str_utils
from .. import poseSym
from .. import marking_menu
import baseRigPart

def getAllRigControlsFromSelection():
    sel = cmds.ls(sl=True)
    if not sel:
        return ()

    for node in sel:
        try:
            part = baseRigPart.RigPart.InitFromItem(node)

        # if the node doesn't belong to a rig part, skip it
        except baseRigPart.RigPartError:
            continue

        # if it does, grab its world part and select the world part hierarchy
        else:
            worldPart = part.getWorldPart()
            return worldPart.getPartHierarchyControls()

    return ()

def getOppositeControls(controls):
    oppositeControls = []
    for node in controls:
        pairNode = poseSym.ControlPair.GetPairNode(node)
        if pairNode:
            pair = poseSym.ControlPair(pairNode)
            if pair.isSingular():
                oppositeControls.append(node)
            else:
                oppositeControls.append(pair.getOppositeControl(node))

        # if we don't have a pair node, lets try to determine the opposite using the name
        else:
            oppositeNode = str_utils.swapParity(node)
            if cmds.objExists(oppositeNode):
                oppositeControls.append(oppositeNode)

    return oppositeControls

def selectAllRigControlsFromSelection():
    nodes = getAllRigControlsFromSelection()
    if nodes:
        cmds.select(nodes)

def selectOppositeControl():
    sel = cmds.ls(sl=True) or []
    if sel:
        opposite = getOppositeControls(sel)
        if opposite:
            cmds.select(opposite)

def selectSelectedParts():
    sel = cmds.ls(sl=True)
    if sel:
        nodesToSelect = []
        for node in sel:
            try:
                part = baseRigPart.RigPart.InitFromItem(node)

            # if the node doesn't belong to a rig part, skip it
            except baseRigPart.RigPartError:
                continue

            nodesToSelect += list(part)

        if nodesToSelect:
            cmds.select(nodesToSelect, add=True)

def selectThisAndChild():
    sel = cmds.ls(sl=True)
    if sel:
        for node in sel:
            try:
                part = baseRigPart.RigPart.InitFromItem(node)

            # if the node doesn't belong to a rig part, skip it
            except baseRigPart.RigPartError:
                continue

            part.selectPartHierarchy()
            return

class RigSelectionMM(marking_menu.MarkingMenu):

    def show(self, menu, menuParent):
        cmds.menuItem(l='Select all rig controls', c=self.selectAll, rp='N')
        cmds.menuItem(l='Select this and child rig controls', c=self.selectThisAndChild, rp='S')
        cmds.menuItem(l='Select selected rig controls', c=self.selectSelectedParts, rp='E')

    def press(self):
        self.selectAll()

    def selectAll(self, _=None):
        cmds.select(getAllRigControlsFromSelection())

    def selectThisAndChild(self, _=None):
        selectThisAndChild()

    def selectSelectedParts(self, _=None):
        selectSelectedParts()

#end
