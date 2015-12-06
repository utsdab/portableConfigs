
from maya import cmds

def getChannelAnimCurves(attrpath):
    cons = cmds.listConnections(attrpath, d=False)
    curves = []
    for con in cons:
        if cmds.objectType(con, isAType='animCurve'):
            curves.append(con)

        # if its a blend node then the object has layered animation on it - trace it to the anim curves
        elif cmds.objectType(con, isAType='animBlendNodeBase'):
            curves += cmds.listConnections('%s.inputA' % con, d=False) or []
            curves += cmds.listConnections('%s.inputB' % con, d=False) or []

    return curves

def swapChannels(attrpath1, attrpath2):
    cons1 = cmds.listConnections(attrpath1, d=False, p=True)
    cons2 = cmds.listConnections(attrpath2, d=False, p=True)

    if cons1:
        cmds.connectAttr(cons1[0], attrpath2, f=True)

    if cons2:
        cmds.connectAttr(cons2[0], attrpath1, f=True)

#end
