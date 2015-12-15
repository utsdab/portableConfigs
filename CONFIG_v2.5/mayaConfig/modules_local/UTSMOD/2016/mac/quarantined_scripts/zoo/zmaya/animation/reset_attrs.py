
from maya import cmds

from .. import apiExtensions

def resetNodes(nodes, skipVisibility=True):
    '''
    simply resets all keyable attributes on a given object to its default value
    great for running on a large selection such as all character controls...
    '''
    selAttrs = cmds.channelBox('mainChannelBox', q=True, sma=True) or cmds.channelBox('mainChannelBox', q=True, sha=True)
    for node in apiExtensions.castToMObjects(nodes):
        attrs = node.iterAttrs(True, True, settable=True)

        for attr in attrs:
            attrName = attr.longName()
            if skipVisibility and attrName == 'visibility':
                continue

            #if there are selected attributes AND the current attribute isn't in the list of selected attributes, skip it...
            if selAttrs is not None:
                if attr.shortName() not in selAttrs:
                    continue

            default = 0
            try:
                default = cmds.attributeQuery(attrName, n=node, listDefault=True)[0]
            except RuntimeError: pass

            attrpath = str(attr)
            if not cmds.getAttr(attrpath, settable=True):
                continue

            #need to catch because maya will let the default value lie outside an attribute's
            #valid range (ie maya will let you creat an attrib with a default of 0, min 5, max 10)
            try:
                cmds.setAttr(attrpath, default, clamp=True)
            except RuntimeError:
                pass

def resetNode(node, skipVisibility=True):
    return resetNodes([node], skipVisibility)

def resetSelection():
    resetNodes(cmds.ls(sl=True) or [])

#end
