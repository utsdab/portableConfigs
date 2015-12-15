
import base64
import StringIO

from maya import cmds

_encode = base64.b32encode
_decode = base64.b32decode

class DataStorage(object):
    NODE_TYPE = 'script'
    ATTR_NAME = 'zooDataStorageNode'
    _ATTRPATH_TEMPL = '%s.' + ATTR_NAME

    # Controls the amount of data written to each node in the storage chain
    CHUNK_SIZE = 1 << 20
    DATA_ATTR_NAME = 'zooData'
    _DATA_ATTRPATH_TEMPL = '%s.' + DATA_ATTR_NAME

    @classmethod
    def GetStartNode(cls, startNode):
        node = startNode
        while True:
            cons = cmds.listConnections(cls._ATTRPATH_TEMPL % node, d=False, type=cls.NODE_TYPE)
            if cons:
                node = cons[0]
            else:
                return node

    @classmethod
    def IterStorageRoots(cls):
        nodes = cmds.ls('*.' + cls.ATTR_NAME) or []
        for node in cmds.ls(type=cls.NODE_TYPE):
            if cmds.objExists(cls._ATTRPATH_TEMPL % node):
                cons = cmds.listConnections(cls._ATTRPATH_TEMPL % node, s=False)
                if not cons:
                    yield node

    @classmethod
    def Iter(cls):
        for node in cls.IterStorageRoots():
            yield cls(node)

    @classmethod
    def ConstructNode(cls, name = None):
        node = cmds.createNode(cls.NODE_TYPE)
        cmds.addAttr(node, ln=cls.ATTR_NAME, at='message')
        cmds.addAttr(node, ln=cls.DATA_ATTR_NAME, dt='string')

        # Rename the node if appropriate
        if name:
            node = cmds.rename(node, name)

        return node

    @classmethod
    def Create(cls, name = None):
        return cls(cls.ConstructNode(name))

    def __init__(self, memberNode):
        self.node = self.GetStartNode(memberNode)

    def clear(self):

        # Lock the start node so it doesn't get deleted
        cmds.lockNode(self.node, lock=True)

        # Delete all storage nodes except the first
        storageNodes = list(self.iterNodes())
        for node in storageNodes[1:]:
            cmds.lockNode(node, lock=False)
            cmds.delete(node)

        # Unlock the start node
        cmds.lockNode(self.node, lock=False)

        # Clear the data in the first node
        cmds.setAttr(self._DATA_ATTRPATH_TEMPL % self.node, '', type='string')

    def iterNodes(self):
        currentNode = self.node
        while True:
            yield currentNode
            cons = cmds.listConnections(self._ATTRPATH_TEMPL % currentNode, s=False)
            if cons:
                currentNode = cons[0]
            else: break

    def _lockNodes(self):
        for node in self.iterNodes():
            cmds.lockNode(node, lock=True)

    def _appendNode(self, previousNode):
        newNode = self.ConstructNode(self.node)
        cmds.connectAttr(self._ATTRPATH_TEMPL % previousNode, self._ATTRPATH_TEMPL % newNode)

        return newNode

    def writeFromFile(self, f):
        self.clear()

        currentNode = self.node
        while True:
            data = _encode(f.read(self.CHUNK_SIZE))
            if not data:
                break

            cmds.setAttr(self._DATA_ATTRPATH_TEMPL % currentNode, data, type='string')
            cmds.lockNode(currentNode, lock=True)
            currentNode = self._appendNode(currentNode)

        # Delete the last node - it doesn't contain any data...
        #cmds.delete(currentNode)

    def write(self, data):
        self.writeFromFile(StringIO.StringIO(data))

    def read(self):
        dataBlobs = []
        for node in self.iterNodes():
            data = cmds.getAttr(self._DATA_ATTRPATH_TEMPL % node) or ''
            dataBlobs.append(_decode(data))

        return ''.join(dataBlobs)

def findMaxStrAttrSize():

    # NOTE: this doesn't seem to work - maya crashes before reporting a value,
    # but I suspect if the file is saved and reloaded it might be a different story
    tmpFilepath = 'c:/users/macaronikazoo/Downloads/tmp.ma'
    cmds.file(new=True, f=True)
    cmds.file(rename=tmpFilepath)
    size = DataStorage.CHUNK_SIZE
    node = DataStorage.ConstructNode()

    writeStr = '0' * size
    cmds.setAttr(DataStorage._DATA_ATTRPATH_TEMPL % node, writeStr, type='string')
    cmds.file(save=True, f=True)
    cmds.file(tmpFilepath, open=True, f=True)
    readStr = cmds.getAttr(DataStorage._DATA_ATTRPATH_TEMPL % node)
    if writeStr == readStr:
        print 'CHUNK_SIZE is good'
    else:
        print 'CHUNK_SIZE is too big'

def storeFileInScene(filepath):
    storage = DataStorage.Create()
    with open(filepath) as f:
        storage.writeFromFile(f)

    return storage

def restoreFileFromScene(storage, filepath):
    with open(filepath, 'wb') as f:
        f.write(storage.read())

#end
