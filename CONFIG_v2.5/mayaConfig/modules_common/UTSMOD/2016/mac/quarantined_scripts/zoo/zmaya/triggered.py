
import inspect
import logging

from maya import cmds

from .. import misc
from .. import events
from . import maya_decorators
from . import serialization
from . import apiExtensions
from . import mel_utils

logger = logging.getLogger(__name__)
eventManager = events.EventManager()

#listen to these events to act on load/unload events.  A boolean argument is passed to callbacks when triggered.  True
#when triggered has been loaded, False when it has been unloaded
#example:
#def informUserIfUnloaded( state ):
#	if not state: print "TRIGGERED HAS BEEN UNLOADED!"
#eventManager.addCallback( EVT_LOAD_STATE_CHANGE, informUserIfUnloaded )
EVT_LOAD_STATE_CHANGE = eventManager.createEventId()

class Command(object):
    INVALID = '<invalid connect>'

    @staticmethod
    def GetTypeCls(typeName):
        if typeName == Command.__name__:
            return Command

        return misc.getNamedSubclass(Command, typeName)

    def __new__(cls, node, attrname, trigger):
        dataDict = serialization.TypedSerializableDict(node, attrname)
        if not dataDict:
            dataDict.setdefaults(cls.DefaultDict())

        typeName = dataDict.get('typeId', Command.__name__)
        typeCls = Command.GetTypeCls(typeName)

        # If the module that defines the menu command hasn't been imported yet,
        # this will be None, so import the module
        if typeCls is None:
            typeModuleName = dataDict.get('typeModule', None)
            if typeModuleName is None:
                raise Exception('Cannot load command of type %s' % typeName)

            # Import the module - this will make is discoverable using the
            # getNamedSubclass function
            __import__(typeModuleName)

            typeCls = Command.GetTypeCls(typeName)
            if typeCls is None:
                raise Exception('Unable to find command class %s in module %s' % (typeName, typeModuleName))

        self = object.__new__(typeCls)

        return self

    def __init__(self, node, attrname, trigger):
        """
        if an attrpath is
        """
        self._node = node
        self._attrname = attrname
        self._trigger = trigger
        self._dict = serialization.TypedSerializableDict(node, attrname)

    def __repr__(self):
        return '%s(%r, %r, %r)' % (type(self).__name__, self._node, self._attrname, self._trigger)
    __str__ = __unicode__ = __repr__

    def __eq__(self, other):
        return self._dict == other._dict

    def __ne__(self, other):
        return not self.__eq__(other)

    @classmethod
    def DefaultDict(cls):
        return dict(typeId=cls.__name__,
                    typeModule=inspect.getmodule(cls).__name__)

    @classmethod
    def FromCmd(cls, cmd):
        return cls(cmd._node, cmd._attrname, cmd._trigger)

    def isEditable(self):
        return True

    def node(self):
        return self._node

    def cmdStr(self, resolve=False, optionals=()):
        cmdStr = self._dict.get('command')
        if cmdStr and resolve:
            cmdStr = self._resolve(cmdStr)

        return cmdStr

    def setCmdStr(self, cmdStr):
        self._dict['command'] = cmdStr

    def setTypeCls(self, cmdCls):
        isCommandCls = issubclass(cmdCls, Command) or cmdCls is Command
        if not isCommandCls:
            raise ValueError('Command class must be subclass of triggered.%s' % Command.__name__)

        d = cmdCls.DefaultDict()
        with maya_decorators.UndoBlockContext():
            self._dict['typeId'] = d.pop('typeId')
            self._dict['typeModule'] = d.pop('typeModule')

        self.__class__ = cmdCls

    def typeId(self):
        return self._dict.get('typeId')

    def setTypeId(self, typeId):
        cmdCls = Command.GetTypeCls(typeId)
        if cmdCls is None:
            raise ValueError('Command class of name %s could not be found' % typeId)

        self.setTypeCls(cmdCls)

    def getCmdResolverDict(self):
        return {}

    def getCmdLocalsDict(self):
        return {
            'cmds': cmds,
            'mel': mel_utils.MEL,
        }

    def _resolve(self, cmdStr):
        connects = [connect for connect, connectIdx in self._trigger.iterConnects()]

        # NOTE: the slice on the connects arg is because when never want the trigger
        # itself when dealing with all connects, and the trigger is always connect[0]
        return cmdStr.format(*connects, self=self._trigger._node, connects=connects[1:], **self.getCmdResolverDict())

    def execute(self, *_):
        resolvedCmd = self.cmdStr(True)
        if resolvedCmd:
            logger.debug('Executing selection cmd %r: %s' % (self, resolvedCmd))
            localsDict = self.getCmdLocalsDict()
            localsDict.setdefault('cmds', cmds)
            try:
                exec resolvedCmd in localsDict
            except:
                logger.error("Failed to execute %r" % self, exc_info=1)

class ImmutableCommand(Command):

    def isEditable(self):
        return False

    def setCmdStr(self, cmdStr):
        raise TypeError("Cannot set a command string on an ImmutableCommand!")

class SelectConnectsCommand(Command):
    def execute(self, *_):

        # Get the connects
        connects = [connect for connect, connectIdx in self._trigger.iterConnects(includeSelf=False)]

        # If there are no connects, bail
        if not connects:
            return

        # De-select the trigger
        cmds.select(self._node, deselect=True)

        # Select the connects
        # NOTE: we always add to the selection here
        cmds.select(connects, add=True)

        # Call the base method
        super(SelectConnectsCommand, self).execute(*_)

class MenuCommand(Command):

    @classmethod
    def DefaultDict(cls):
        d = super(MenuCommand, cls).DefaultDict()
        d.setdefault('name', 'untitled menu')

        return d

    def getIndex(self):
        """parses the index of the menu item from the attr name"""
        idxStr = self._attrname.split('[')[1][:-1]

        return int(idxStr)

    def menuName(self):
        return self._dict['name']

    def setMenuName(self, name):
        self._dict['name'] = name

    def buildMenu(self, parent):
        cmds.menuItem(l=self.menuName(), c=self.execute, p=parent)

class ToggleConnectsShapeVisCommand(MenuCommand):
    def execute(self, *_):
        shapes = []
        for con, idx in self._trigger.connects()[1:]:
            shapes += cmds.listRelatives(con, pa=True, s=True) or []

        vis = not cmds.getAttr('%s.v' % shapes[0])
        for shape in shapes:
            cmds.setAttr('%s.v' % shape, vis)

class Trigger(object):
    VERSION = 1

    ATTR_BASE = 'zooTrigger'
    ATTR_VERSION = '_trig_version'
    ATTR_CONNECTS = '_trigger_connects'
    ATTR_SEL_TRIGGER = '_sel_trigger'
    ATTR_MENUS = '_menu_triggers'
    ATTR_KILL_STATE = '_menu_killState'
    ATTR_DATA = '_trigger_data'

    @classmethod
    def Upconvert(cls, node):

        # run any upconversion on the exportable node...
        versionAttrpath = '%s.%s' % (node, cls.ATTR_VERSION)
        version = cmds.getAttr(versionAttrpath)
        for ver in xrange(version, cls.VERSION):
            upconvertMethodName = '_Upconvert_to%s' % (ver+1)
            if hasattr(cls, upconvertMethodName):
                try:
                    getattr(cls, upconvertMethodName)(node)

                # NOTE: this needs to be explicitly caught here because this gets called from a constructor, and
                # constructor methods eat exceptions silently, returning None
                except:
                    logger.error("Error upgrading from v%d" % ver, exc_info=1)

            logger.info('Upgraded trigger from v%d' % ver)
            cmds.setAttr(versionAttrpath, ver+1)

    @classmethod
    def _Upconvert_to1(cls, node):

        # grab the attribute data and rebuild
        ver = cmds.getAttr('%s._trig_version' % node)
        connectIndices = cmds.getAttr('%s._trigger_connects' % node, multiIndices=True) or []
        trigStr = cmds.getAttr('%s._sel_trigger' % node) or ''
        menuIndices = cmds.getAttr('%s._menu_triggers' % node, multiIndices=True) or []
        ks = cmds.getAttr('%s._menu_killState' % node)

        connects = []
        for idx in connectIndices:
            attrpath = cmds.connectionInfo('%s._trigger_connects[%d]' % (node, idx), sfd=True)
            if attrpath:
                connects.append((idx, attrpath.split('.')[0]))

        menuStrs = []
        for idx in menuIndices:
            menuStrs.append(cmds.getAttr('%s._menu_triggers[%d]' % (node, idx)))

        # now delete all attributes
        cmds.deleteAttr('%s.zooTrigger' % node)

        # re-create the trigger - this will rebuild the attributes
        trig = cls(node)

        # set data
        cmds.setAttr('%s.%s' % (node, cls.ATTR_VERSION), ver)
        cmds.setAttr('%s.%s' % (node, cls.ATTR_SEL_TRIGGER), trigStr, type='string')
        cmds.setAttr('%s.%s' % (node, cls.ATTR_KILL_STATE), ks)

        for idx, connect in connects:
            cmds.connectAttr('%s.msg' % connect, '%s.%s[%d]' % (node, cls.ATTR_CONNECTS, idx), f=True)

        for idx, menuStr in enumerate(menuStrs):
            cmds.setAttr('%s.%s[%d]' % (node, cls.ATTR_MENUS, idx), menuStr, type='string')

    @classmethod
    def IsA(cls, node):
        nodeStr = str(node)
        if '.' in nodeStr or '[' in nodeStr:
            return False

        return cmds.objExists('%s.%s' % (nodeStr, cls.ATTR_BASE))

    @classmethod
    def Create(cls, node, connects=(), selectionCmd=None, cmdCls=Command):
        new = cls(node)
        for aNode in connects:
            new.connect(aNode)

        cmd = new.selectionCmd()
        cmd.setTypeCls(cmdCls)
        if selectionCmd:
            cmd.setCmdStr(selectionCmd)

        return new

    @classmethod
    def Iter(cls):
        for attrpath in cmds.ls('*.%s' % cls.ATTR_BASE, r=True) or []:
            yield cls(attrpath.split('.')[0])

    @classmethod
    def All(cls):
        triggers = []
        attrpaths = cmds.ls('*.%s' % cls.ATTR_BASE) or []
        for attrpath in attrpaths:
            triggers.append(attrpath.split('.')[0])

        return [cls(t) for t in triggers]

    def __new__(cls, node):
        if not cmds.objExists('%s.%s' % (node, cls.ATTR_BASE)):
            cmds.addAttr(node, ln=cls.ATTR_BASE, at='compound', numberOfChildren=6)
            cmds.addAttr(node, ln=cls.ATTR_VERSION, p=cls.ATTR_BASE, at='long')
            cmds.addAttr(node, ln=cls.ATTR_DATA, p=cls.ATTR_BASE, dt='string')
            cmds.addAttr(node, ln=cls.ATTR_CONNECTS, p=cls.ATTR_BASE, at='message', multi=True, indexMatters=True)
            cmds.addAttr(node, ln=cls.ATTR_SEL_TRIGGER, p=cls.ATTR_BASE, dt='string')
            cmds.addAttr(node, ln=cls.ATTR_MENUS, p=cls.ATTR_BASE, dt='string', multi=True)
            cmds.addAttr(node, ln=cls.ATTR_KILL_STATE, p=cls.ATTR_BASE, at='bool')

            # store the typeId if this isn't the base class
            if cls is not Trigger:
                serialization.TypedSerializableDict(node, cls.ATTR_DATA)['typeId'] = cls.__name__

            cmds.setAttr('%s.%s' % (node, cls.ATTR_VERSION), cls.VERSION)
            cmds.setAttr('%s.%s' % (node, cls.ATTR_KILL_STATE), True)

        cls.Upconvert(node)

        # see if the trigger has any particular type information
        if cmds.objExists('%s.%s' % (node, cls.ATTR_DATA)):
            clsStr = serialization.TypedSerializableDict(node, cls.ATTR_DATA).get('typeId')
            if clsStr:
                if clsStr in globals():
                    cls = globals()[clsStr]

        return object.__new__(cls)

    def __init__(self, node):
        if type(node) is Trigger:
            node = node._node

        self._node = apiExtensions.asMObject(node)

    def __str__(self):
        return str(self._node)

    def __unicode__(self):
        return unicode(self._node)

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self._node)

    def __eq__(self, other):
        return self._node == other._node

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._node)

    def __getitem__(self, idx):
        """
        returns the connect at index <slot>
        """
        if idx == 0:
            return self._node

        attrPath = '%s.%s[%d]' % (self._node, self.ATTR_CONNECTS, idx)
        objPath = cmds.connectionInfo(attrPath, sfd=True)
        if objPath is not None:
            return objPath.split('.')[0]

        raise IndexError('no such connect exists')

    def __len__(self):
        """
        returns the number of connects
        """
        return len(self.connects())

    @property
    def data(self):
        return serialization.TypedSerializableDict(self._node, self.ATTR_DATA)

    def iterConnects(self, includeSelf=True):
        """
        iterator that returns connectObj, connectIdx
        """
        if includeSelf:
            yield (self._node, 0)

        indices = cmds.getAttr('%s.%s' % (self._node, self.ATTR_CONNECTS), multiIndices=True) or []
        for idx in indices:
            yield (self[idx], idx)

    def connects(self):
        return list(self.iterConnects())

    def connect(self, node, idx=None):
        """
        performs the actual connection of an object to a connect idx
        """

        # if the user is trying to connect the trigger to itself, return zero which is the reserved slot for the trigger
        if apiExtensions.cmpNodes(node, self._node):
            return 0

        if idx is None:
            idx = self.connects()[-1][1] + 1

        if idx <= 0:
            return 0

        # make sure the connect isn't already connected - if it is, return the slot number
        if self.isConnected(node):
            return self.getConnectSlots(node)[0]

        attrpath = '%s.%s[%d]' % (self._node, self.ATTR_CONNECTS, idx)

        cmds.connectAttr('%s.msg' % node, attrpath, f=True)

        return idx

    def disconnect(self, nodeOrSlot):
        """
        removes either the specified object from all slots it is connected to, or deletes the given slot index
        """
        if isinstance(nodeOrSlot, basestring):
            slots = self.getConnectSlots(nodeOrSlot)
        elif type(nodeOrSlot) is int:
            slots = [nodeOrSlot]

        for slot in slots:
            cmds.removeMultiInstance('%s.%s[%d]' % (self._node, self.ATTR_CONNECTS, slot), b=True)

    def getConnectSlots(self, node):
        """
        return a list of the connect slot indicies the given obj is connected to
        """
        if apiExtensions.cmpNodes(node, self._node):
            return []

        prefixLen = len(self.ATTR_CONNECTS)

        slots = set()
        connections = cmds.listConnections('%s.msg' % node, s=False, p=True) or []
        for con in connections:
            aNode, anAttr = con.split('.')
            if not apiExtensions.cmpNodes(aNode, self._node):
                continue

            attrPrefix = anAttr[:prefixLen]
            if attrPrefix == self.ATTR_CONNECTS:
                idxStr = anAttr[prefixLen+1:-1]
                if idxStr.isdigit():
                    slots.add(int(idxStr))

        return list(sorted(slots))

    def isConnected(self, node):
        """
        returns whether a given node is connected as a connect to this trigger
        """
        for aNode, idx in self.iterConnects():
            if apiExtensions.cmpNodes(node, aNode):
                return True

        return False

    def iterMenus(self):
        """
        iterator yields tuples containing (slot, MenuCommand)
        """
        indices = cmds.getAttr('%s.%s' % (self._node, self.ATTR_MENUS), multiIndices=True) or []
        for idx in indices:
            menuCmd = MenuCommand(self._node, '%s[%d]' % (self.ATTR_MENUS, idx), self)
            yield (idx, menuCmd)

    def menus(self):
        return list(self.iterMenus())

    def selectionCmd(self):
        return Command(self._node, self.ATTR_SEL_TRIGGER, self)

    def menuCmd(self, idx):
        return MenuCommand(self._node, '%s[%d]' % (self.ATTR_MENUS, idx), self)

    def createMenu(self, name=None, cmdCls=MenuCommand):
        indices = cmds.getAttr('%s.%s' % (self._node, self.ATTR_MENUS), multiIndices=True) or []
        indices.sort()

        idx = 0
        if indices:
            idx = indices[-1] + 1

        attrname = '%s[%d]' % (self.ATTR_MENUS, idx)
        cmds.setAttr('%s.%s' % (self._node, attrname), '', type='string')

        cmd = cmdCls(self._node, attrname, self)

        if name is not None:
            cmd.setMenuName(name)

        return cmd

    def deleteMenu(self, idx):
        if isinstance(idx, MenuCommand):
            idx = idx.getIndex()

        cmds.removeMultiInstance('%s.%s[%d]' % (self._node, self.ATTR_MENUS, idx), b=True)

    def trigger(self):
        self.selectionCmd().execute()

    def killState(self):
        attrpath = '%s.%s' % (self._node, self.ATTR_KILL_STATE)

        return bool(cmds.getAttr(attrpath))

    def setKillState(self, state):
        attrpath = '%s.%s' % (self._node, self.ATTR_KILL_STATE)
        cmds.setAttr(attrpath, bool(state))

    def highlight(self):
        setHighlightValues(self._node, True)

    def unhighlight(self):
        setHighlightValues(self._node, False)

    def delete(self):
        # this is pretty trivial - all attributes are parented to the base attribute, so just
        # delete it and we're done
        cmds.deleteAttr('%s.%s' % (self._node, self.ATTR_BASE))

def setHighlightValues(node, overrideEnabled, overrideColor=17):
    attrpath = '%s.overrideEnabled' % node
    try:
        cmds.setAttr(attrpath, overrideEnabled)

    # we don't bail here because the overrides may already be turned on
    # instead of querying whether they are or not, just try to set it
    except: pass

    attrpath = '%s.overrideColor' % node
    try:
        cmds.setAttr(attrpath, overrideColor)
    except: pass

class Selecto(Trigger):
    @property
    def shader(self):
        shape = cmds.listRelatives(self._node, pa=True, s=True)[0]
        se = cmds.listConnections(shape, s=False, type='shadingEngine')[0]

        return cmds.listConnections('%s.surfaceShader' % se, d=False)[0]

    def highlight(self):

        # store the initial colour
        if 'colour' not in self.data:
            self.data['colour'] = cmds.getAttr('%s.outColor' % self.shader)[0]
            print 'storing the initial colour', self.data['colour']

        # set the highlight colour
        cmds.setAttr('%s.outColor' % self.shader, 1, 1, 1)

    def unhighlight(self):

        # grab the initial colour
        col = self.data.get('colour')
        if col:
            cmds.setAttr('%s.outColor' % self.shader, *col)
            print 'restoring original colour', col

JOB_ID = None

def Load():
    global JOB_ID

    # If there is an existing job, unload it
    if JOB_ID is not None:
        Unload()

    jobId = cmds.scriptJob(cu=True, e=('SelectionChanged', TriggerSelection))
    JOB_ID = maya_decorators.JobId(jobId)
    eventManager.trigger(EVT_LOAD_STATE_CHANGE, True)

def Unload():
    global JOB_ID
    if JOB_ID is not None:
        JOB_ID.kill()
        JOB_ID = None
        eventManager.trigger(EVT_LOAD_STATE_CHANGE, False)

def State():
    return JOB_ID is not None

def ToggleState():
    if State():
        Unload()
    else:
        Load()

@maya_decorators.d_undoBlock
def TriggerSelection():
    """
    this proc is fired off when the selection is changed - it basically just sets off the
    triggers for each object in the trigger list
    """

    # This is weird, but if this module gets "flushed" then this method becomes
    # orphaned as a script job, and no longer has access to module globals. So
    # we check here to see whether this has happened and quietly exit if it has
    if cmds is None:
        logger.debug('owning module has been flushed - unloading %s' % JOB_ID)
        Unload()
        logger.debug('unloaded job id %s' % JOB_ID)
        return

    highlight = cmds.optionVar(q='zooTrigHighlighting')

    # If highlight is on, we first have to unhighlight all existing triggers
    if highlight:
        for trigger in Trigger.Iter():
            trigger.unhighlight()

    # Trigger all triggers
    selTriggers = filter(Trigger.IsA, cmds.ls(sl=True) or [])
    for node in selTriggers:
        Trigger(node).trigger()

    # Now setup highlighting
    sel = cmds.ls(sl=True) or []
    if highlight and sel:
        possibleTriggers = cmds.listConnections('.message', s=False, p=True) or []
        for attrpath in possibleTriggers:
            toks = attrpath.split('.')
            if toks[1].startswith(Trigger.ATTR_CONNECTS):
                likelyTrigger = toks[0]
                if Trigger.IsA(likelyTrigger):
                    trigger = Trigger(likelyTrigger)
                    trigger.highlight()

def executeMenuCmds(menuCmds):
    for menuCmd in menuCmds:
        menuCmd.execute(None)

def buildMenuItems(parent, obj):
    """
    build the menuItems in the dagProcMenu - it is possible to set a "kill menu" attribute
    on an object now that will stop the dagMenu building after the objMenu items have been
    added
    """

    if not Trigger.IsA(obj):
        return

    killState = False

    # list menus on any shape objects as well
    objs = [obj] + (cmds.listRelatives(obj, pa=True, s=True) or [])

    # have we got anything selected?
    selection = cmds.ls(sl=True) or []
    objs += selection
    objs = misc.removeDupes(objs)

    # now get a list of objs that have menus - if there are more than one, build section
    # labels, otherwise skip labels
    triggers = []
    for o in objs:
        if Trigger.IsA(o):
            triggers.append(Trigger(o))

    # if we have no triggers in the list, bail, there's nothing to do
    if not triggers:
        return

    # now gather a list of menus and remove duplicates based on the menu title
    menuNames = []  # stores order
    menuNameCmdDict = {}  # stores duplicates
    for trigger in triggers:

        # if ANY of the objs have the kill state set, turn it on
        if trigger.killState():
            killState = True

        for idx, menuCmd in trigger.iterMenus():
            name = menuCmd.menuName()
            if name in menuNameCmdDict:
                menuNameCmdDict[name].append(menuCmd)
            else:
                menuNames.append(name)
                menuNameCmdDict[name] = [menuCmd]

    # now build the actual menu widgets
    cmds.setParent(parent, m=True)
    for name in menuNames:
        menuCmds = menuNameCmdDict.pop(name)
        if len(menuCmds) == 1:
            menuCmds[0].buildMenu(parent)
        else:
            cmds.menuItem(l=name, c=misc.uiCB(executeMenuCmds, menuCmds), p=parent)

    # append dividers if we're not bailing out of the menu build
    if not killState:
        cmds.menuItem(d=True)
        cmds.menuItem(d=True)

    return killState

#end
