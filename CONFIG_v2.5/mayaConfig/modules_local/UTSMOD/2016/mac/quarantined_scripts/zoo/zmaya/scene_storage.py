
import inspect

from maya import cmds

import apiExtensions
import serialization
import maya_decorators

# load the tb_nodes plugin - we use a tb_storage node for storing export containers
cmds.loadPlugin('zooStorageNode.py', quiet=True)

NODE_TYPE = 'zooStorageNode'

def classFullname(cls):
    module = inspect.getmodule(cls)
    return '%s.%s' % (module.__name__, cls.__name__)

class Storage(object):

    @classmethod
    def IsA(cls, node):
        if cmds.nodeType(node) == NODE_TYPE:
            return True

        return False

    @classmethod
    def Iter(cls, skipReferenced=True):
        for node in cmds.ls(type=NODE_TYPE) or []:

            # this test exists so that subclasses can implement their own IsA methods
            try:
                if not cls.IsA(node):
                    continue

            # if a node gets deleted while we're iterating then the node may not actually
            # exist.  So catch runtime errors and assume they're because the node is gone
            except RuntimeError: continue

            if skipReferenced and cmds.referenceQuery(node, inr=True):
                continue

            yield cls(node)

    @classmethod
    @maya_decorators.d_maintainSceneSelection
    def Create(cls):
        node = apiExtensions.asMObject(cmds.createNode(NODE_TYPE))
        node.rename('tb_data')

        cmds.addAttr(node, ln='zooStorageClients', dt='string', multi=True)

        return cls(node)

    @classmethod
    def Get(cls):
        '''
        returns the first storage node found in this scene, otherwise None
        '''
        for storage in cls.Iter(True):
            return storage

    @classmethod
    def GetOrCreate(cls):
        return cls.Get() or cls.Create()

    @classmethod
    def Exists(cls):
        for storage in cls.Iter(True):
            return True

        return False

    def __init__(self, node):
        self._node = node

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self._node)
    __str__ = __repr__

    def __eq__(self, other):
        return self._node == other._node

    @property
    def node(self):
        return self._node

    def registerClient(self, storageClientCls):

        # before we do anything, make sure the client cls implements the IsA class method
        if 'isUsed' not in storageClientCls.__dict__:
            raise TypeError("The client class must implement the isUsed method")

        indices = cmds.getAttr('%s.zooStorageClients' % self._node, multiIndices=True) or []
        index = 0
        if indices:
            index = indices[-1] + 1

        attrname = 'zooStorageClients[%d]' % index
        clientDict = serialization.TypedSerializableDict(self._node, attrname)
        clientDict['clientClsPath'] = classFullname(storageClientCls)

    def getClientCls(self, index):
        attrname = 'zooStorageClients[%d]' % index
        clientDict = serialization.TypedSerializableDict(self._node, attrname)
        clientClsPath = clientDict['clientClsPath']
        toks = clientClsPath.split('.')
        clientClsName = toks.pop()
        clientClsModule = __import__('.'.join(toks))
        clientCls = getattr(clientClsModule, clientClsName)

        return clientCls

    def iterRegisteredClients(self):
        indices = cmds.getAttr('%s.zooStorageClients' % self._node, multiIndices=True) or []
        for idx in indices:
            yield self.getClientCls(idx)

    def isRegistered(self, storageClientCls):
        for clientCls in self.iterRegisteredClients():
            if clientCls is storageClientCls:
                return True

    def deregisterClient(self, storageClientCls):
        clsName = storageClientCls.__name__

    def isUsed(self):
        for clientCls in self.iterRegisteredClients():
            if clientCls(self._node).isUsed():
                return True

        return False

class StorageClient(object):
    '''
    basic super class for storage clients to inherit from
    '''

    @classmethod
    def Iter(cls, skipReferenced=True):
        for storage in Storage.Iter(skipReferenced):
            if storage.isRegistered(cls):
                yield cls(storage)

    @classmethod
    def Create(cls):
        storage = Storage.GetOrCreate()
        storage.registerClient(cls)

        return cls(storage)

    @classmethod
    def GetOrCreate(cls):
        for client in cls.Iter():
            return client

        return cls.Create()

#end
