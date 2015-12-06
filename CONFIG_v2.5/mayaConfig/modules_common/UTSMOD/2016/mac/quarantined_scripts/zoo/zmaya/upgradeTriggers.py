
from maya import cmds

from . import triggered

OLD_CON_ATTRNAME = 'zooTrig'
OLD_CMD_ATTRNAME = 'zooTrigCmd0'
OLD_CMD_ATTRTEMPLATE = '%s.' + OLD_CMD_ATTRNAME

def upgradeNode(node):
    cmdStr = cmds.getAttr(OLD_CMD_ATTRTEMPLATE % node)
    connections = []
    for attrname in cmds.listAttr(node, ud=True):
        if attrname.startswith(OLD_CON_ATTRNAME):
            suffix = attrname[len(OLD_CON_ATTRNAME):]
            if suffix.isdigit():
                idx = int(suffix)
                cons = cmds.listConnections('%s.%s' % (node, attrname), d=False)
                if cons:
                    connections.append((idx, cons[0]))

    # Sort the connections
    connections.sort()

    # Delete the old triggered machinery
    cmds.deleteAttr(OLD_CMD_ATTRTEMPLATE % node)
    for idx, c in connections:
        cmds.deleteAttr('%s.%s%d' % (node, OLD_CON_ATTRNAME, idx))

    # So now we have the trigger cmd AND the connections, convert to a
    # new style trigger
    trigger = triggered.Trigger.Create(node, [c[1] for c in connections])

    # If the old trigger command is a select connects command, hook it up
    # to the select connects command class
    if cmdStr == 'select -d #;\nselect -add @;':
        trigger.setTypeCls(triggered.SelectConnectsCommand)

def upgrade():
    for attrpath in cmds.ls('*.zooTrigCmd0'):
        node, attrname = attrpath.split('.')
        upgradeNode(node)

#end
