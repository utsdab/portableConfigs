
'''
Referencing in maya kinda sucks.  Getting reference information from nodes/files is split across at least
3 different mel commands in typically awkward autodesk fashion, and there is a bunch of miscellaneous
functionality that just doesn't exist at all.  So this module is supposed to be a collection of
functionality that alleviates this somewhat...
'''

from maya import cmds

from .. import path

def isFileReferenced(filepath):
    return ReferencedFile.IsFilepathReferenced(filepath)

def stripNamespaceFromNamePath(name, namespace):
    '''
    strips out the given namespace from a given name path.

    example:
    stripNamespaceFromNamePath('moar:ns:wow:some|moar:ns:wow:name|moar:ns:wow:path', 'ns')

    returns:
    'wow:some|wow:name|wow:path'
    '''
    if namespace.endswith(':'):
        namespace = namespace[:-1]

    cleanPathToks = []
    for pathTok in name.split('|'):
        namespaceToks = pathTok.split(':')
        if namespace in namespaceToks:
            idx = namespaceToks.index(namespace)
            namespaceToks = namespaceToks[idx+1:]

        cleanPathToks.append(':'.join(namespaceToks))

    return '|'.join(cleanPathToks)

def addNamespaceTokNamePath(name, namespace):
    '''
    adds the given namespace to a name path.

    example:
    addNamespaceTokNamePath('some|name|path', 'ns')

    returns:
    'ns:some|ns:name|ns:path'
    '''
    if namespace.endswith(':'):
        namespace = namespace[:-1]

    namespacedToks = []
    for pathTok in name.split(name, '|'):
        namespacedToks.append('%s:%s' % (namespace, name))

    return '|'.join(namespacedToks)

class ReferencedFile(object):

    @classmethod
    def Iter(cls, recursive=False, copyNumber=False):
        yielded = set()
        for referenceNode in ReferenceNode.Iter(recursive):
            filepath = referenceNode.getFilepath(copyNumber)
            if filepath in yielded:
                continue

            yielded.add(filepath)
            yield filepath

    @classmethod
    def IsFilepathReferenced(cls, filepath):
        for refFilepath in cls.Iter():
            if refFilepath == filepath:
                return True

        return False

    def __init__(self, filepath):
        self._filepath = filepath

    def getReferenceNode(self):
        node = cmds.file(self._filepath, q=True, referenceNode=True)

        return ReferenceNode(node)

    def isReferenced(self):
        '''
        returns whether this reference is nested
        '''
        return self.getReferenceNode().isReferenced()

def referenceFile(filepath, namespace):
    return ReferencedFile(cmds.file(filepath, reference=True, ns=namespace))

class ReferenceNode(object):

    @classmethod
    def InitFromNode(cls, node):
        '''
        constructs an instance from a referenced node
        '''
        if not cmds.referenceQuery(node, inr=True):
            raise ValueError("The node %s isn't a referenced node!" % node)

        if cmds.nodeType(node) != 'reference':
            node = cmds.referenceQuery(node, referenceNode=True)

        return cls(node)

    @classmethod
    def Iter(cls, recursive=False):
        for node in cmds.ls(type='reference'):

            # If we're not "recursing" then skip any reference nodes
            # that are themselves referenced
            if not recursive:
                if cmds.referenceQuery(node, inr=True):
                    continue

            try:
                cmds.referenceQuery(node, filename=True)

            # Maya throws an exception on "shared" references - whatever
            # the F they are.  so catch and skip when this happens
            except RuntimeError:
                continue

            yield cls(node)

    def __init__(self, node):
        self._node = node
        self._isReferenced = cmds.referenceQuery(node, inr=True)

    def isReferenced(self):
        return self._isReferenced

    def isLoaded(self):
        return cmds.referenceQuery(self._node, isLoaded=True)

    def removeEdits(self):
        raise NotImplemented

    def load(self, filepath=None):
        if not self.isLoaded():
            filepath = filepath or self.getFilepath()

            # make sure the file exists
            if not filepath.exists():
                raise IOError("Couldn't find the file:  %s" % filepath)

            try:
                cmds.file(filepath, loadReference=self._node)

            # really hard to know what to do here - if there are errors loading the file this happens.  For the most
            # part there is nothing we can do about that and the errors may be "normal".  But it may also be for other
            # valid reasons.  Maya only ever seems to throw RuntimeErrors so...  cross your fingers!
            except RuntimeError:
                pass

    def unload(self):
        cmds.file(unloadReference=self._node)

    def getFilepath(self, copyNumber=False):
        '''
        will return the filepath to the scene file this node comes from.  If copyNumber=True then the "copy number" will
        be included in the filepath - see the docs for the referenceQuery mel command for more information
        '''
        return path.Path(cmds.referenceQuery(self._node, filename=True, withoutCopyNumber=not copyNumber))

    def setFilepath(self, filepath):

        # If the filepath is the same as the current filepath, early out
        if self.getFilepath() == path.Path(filepath):
            return

        self.unload()
        self.load(filepath)

    def getParentReferenceNode(self):
        '''
        returns the parent ReferenceNode of this one

        Ie: if this node is referenced it returns the ReferenceNode that contains this one

        Returns None is this node isn't referenced
        '''
        if self.isReferenced():
            node = cmds.referenceQuery(self._node, referenceNode=True, parent=True)

            return ReferenceNode(node)

    def iterParents(self):
        parent = self.getParentReferenceNode()
        while parent is not None:
            yield parent
            parent = parent.getParentReferenceNode()

    def getNamespace(self):
        '''
        returns the namespace for the reference

        NOTE: this is the namespace on the reference only - ie if this node is also referenced, containing
        namespaces aren't included.  See getNodePrefix to get the resolved namespace prefix for nodes
        '''
        return cmds.file(self.getFilepath(True), q=True, namespace=True)

    def setNamespace(self, namespace):
        if not self.isLoaded():
            raise Exception('Reference must be loaded to set the namespace')

        cmds.file(self.getFilepath(True), e=True, namespace=namespace)

    def getNodePrefix(self):
        '''
        returns the actual namespace prefix for all nodes within this reference
        '''
        namespaceToks = [node.getNamespace() for node in self.iterParents()]

        return ':'.join(namespaceToks)

    def getReferenceNamespace(self):
        '''
        returns the namespace for this reference - this doesn't include referenced namespaces if this reference is nested
        '''
        return cmds.file(self.getFilepath(True), q=True, namespace=True)

    def getNode(self):
        return self._node

    def getNodes(self):
        '''
        returns the list of nodes in this referenced scene
        '''
        return cmds.referenceQuery(self._node, nodes=True, dagPath=True) or []

    def getUnreferencedNode(self):
        '''
        returns the node name as it would be in the scene the node comes from
        '''
        return stripNamespaceFromNamePath(self._node, self.getReferenceNamespace())

#end
