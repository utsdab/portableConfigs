
import logging

from xml.etree import cElementTree as ElementTree

from maya import cmds, mel

import path
import misc
import events
import apiExtensions
import cls_types
import simple_p4

import maya_p4
import maya_decorators
import scene_storage

from serialization import TypedSerializableDict

logger = logging.getLogger(__name__)

EVT_SET_ATTR = events.EventManager().createEventId()
EVT_EXPORTABLE_CREATED = events.EventManager().createEventId()
EVT_EXPORTABLE_DELETED = events.EventManager().createEventId()
EVT_EXPORTABLE_ISOLATED = events.EventManager().createEventId()

def getScene():
    filepath = path.Path(cmds.file(q=True, sn=True))
    if not filepath:
        raise ValueError("Scene isn't saved!")

    return filepath

def getVisibleEditors():
    editors = []
    for panel in cmds.getPanel(visiblePanels=True) or []:
        if cmds.getPanel(typeOf=panel) == 'modelPanel':
            editors.append(cmds.modelPanel(panel, q=True, modelEditor=True))

    return editors

class ExportableContainer(scene_storage.StorageClient):
    '''
    These act like lists for Exportable instances.

    Basically a node gets marked as a container which holds actual exportable items.

    For example, in an animation file there might be a container for the skeleton and
    5 exportables for the different animations within the scene as well as an
    exportable for the skinned mesh being animated
    '''

    ATTR_BASE = 'TB_exportableContainer'

    ATTR_VERSION = '_version'

    ATTR_PARENT_SET = '_exportables'
    ATTR_NODES = '_nodes'
    ATTR_DATA = '_data'

    VERSION = 1

    @classmethod
    def Create(cls):
        storage = scene_storage.Storage.GetOrCreate()
        storage.registerClient(cls)

        node = storage.node
        cmds.addAttr(node, ln=cls.ATTR_BASE, at='compound', numberOfChildren=4)
        cmds.addAttr(node, ln=cls.ATTR_VERSION, p=cls.ATTR_BASE, at='long')
        cmds.addAttr(node, ln=cls.ATTR_PARENT_SET, p=cls.ATTR_BASE, at='message')
        cmds.addAttr(node, ln=cls.ATTR_NODES, p=cls.ATTR_BASE, at='message', multi=True, indexMatters=True)
        cmds.addAttr(node, ln=cls.ATTR_DATA, p=cls.ATTR_BASE, dt='string', multi=True, indexMatters=True)

        # set the version
        cmds.setAttr('%s.%s' % (node, cls.ATTR_VERSION), cls.VERSION)

        return cls(storage)

    def getIsolatedExportable(self):
        '''
        Returns the exportable that is currently isolated

        NOTE: returns the first exportable found.  Multiple matches are possible if more than
        one exportable shares the same nodes set
        '''
        name = Exportable.SEL_CON_NAME
        if cmds.selectionConnection(name, q=True, ex=True):
            for editor in getVisibleEditors():
                editorCon = cmds.modelEditor(editor, q=True, mainListConnection=True)
                if editorCon == name:
                    nodes = cmds.selectionConnection(name, q=True, object=True)
                    for exportable in self:
                        if exportable.nodes() == nodes:
                            return exportable

        return None

    def __init__(self, storage):
        self._storage = storage
        self.upconvert()

    def upconvert(self):
        node = self._storage.node

        # run any upconversion on the exportable node...
        versionAttrpath = '%s.%s' % (node, self.ATTR_VERSION)
        version = cmds.getAttr(versionAttrpath)
        for ver in xrange(version, self.VERSION):
            upconvertMethodName = '_upconvert_to_%s' % (ver+1)
            if hasattr(self, upconvertMethodName):
                getattr(self, upconvertMethodName)()

                # update the version
                cmds.setAttr(versionAttrpath, ver+1)

    def _upconvert_to_1(self):
        for exportable in self:
            if type(exportable) is Animation:
                relativePath = getScene().up() - path.TB_DATA
                relativePath = '%s/morpheme/%s' % (relativePath[0], relativePath[1:])
                exportable.setAttr('path', relativePath)

    def _getIndices(self):
        return cmds.getAttr('%s.%s' % (self.node, self.ATTR_DATA), multiIndices=True) or []

    def __repr__(self):
        return 'ExportableContainer(%r)' % self._storage

    def __len__(self):
        return len(self._getIndices())

    def __eq__(self, other):
        return self._storage == other._storage

    def __ne__(self, other):
        return not self.__eq__(other)

    def __getitem__(self, idx):
        '''
        returns an Exportable instance at the given index
        '''
        if type(idx) is int:
            return Exportable(self, idx)

        raise TypeError("Indices must be integers!")

    def __iter__(self):
        for idx in self._getIndices():
            yield self[idx]

    @property
    def node(self):
        return self._storage.node

    def getParentSet(self):
        attrpath = '%s.%s' % (self.node, self.ATTR_PARENT_SET)
        cons = cmds.listConnections(attrpath, d=False)
        if cons:
            return cons[0]

        # create the parent set if we don't have one yet
        parentSet = apiExtensions.asMObject(cmds.createNode('objectSet', n='exportables'))
        cmds.connectAttr('%s.message' % parentSet, '%s.%s' % (self.node, self.ATTR_PARENT_SET), f=True)

        return parentSet

    def getNodesSet(self, index):
        '''
        Returns the objectSet used to store nodes for the exportable at the given index.

        If no objectSet is found None is returned
        '''
        attrpath = '%s.%s[%d]' % (self.node, self.ATTR_NODES, index)
        cons = cmds.listConnections(attrpath, d=False)
        if cons:
            if cmds.nodeType(cons[0]) == 'objectSet':
                return cons[0]

        return None

    def setNodesSet(self, index, setNode):
        attrpath = '%s.%s[%d]' % (self.node, self.ATTR_NODES, index)
        cmds.connectAttr('%s.message' % setNode, attrpath, f=True)

        # add this exportables set to the parent set - this is purely so we dont' clog the outliner with object sets
        cmds.sets(setNode, add=self.getParentSet())

    def nodes(self, index):
        attrpath = '%s.%s[%d]' % (self.node, self.ATTR_NODES, index)
        cons = cmds.listConnections(attrpath, d=False)
        if cons:
            node = cons[0]
            if cmds.nodeType(node) == 'objectSet':
                return cmds.sets(node, q=True) or []
            else:
                return [node]

        return []

    def setNodes(self, index, nodes):
        if isinstance(nodes, (basestring, apiExtensions.MObject)):

            # if the node we've been given is an object set, plug it in and bail
            if cmds.nodeType(nodes) == 'objectSet':
                self.setNodesSet(index, nodesSet)
                return

            # otherwise plug it into a list
            else:
                nodes = [str(nodes)]

        attrpath = '%s.%s[%d]' % (self.node, self.ATTR_NODES, index)
        nodesSet = self.getNodesSet(index)

        # if we don't have a set to contain the nodes, create one
        if not nodesSet:
            nodesSet = cmds.createNode('objectSet', n='exportable')
            self.setNodesSet(index, nodesSet)

        # clear any existing nodes in the set
        cmds.sets(clear=nodesSet)

        # add the nodes to the set
        cmds.sets(nodes, add=nodesSet)

    def create(self, exportableCls, nodes):
        if not issubclass(exportableCls, Exportable):
            raise TypeError("%s isn't a subclass of Exportable!" % exportableCls)

        existingIndices = self._getIndices()
        idx = 0
        if existingIndices:
            idx = existingIndices[-1] + 1

        attrname = '%s[%d]' % (self.ATTR_DATA, idx)
        if nodes:
            self.setNodes(idx, nodes)

        exportable = exportableCls(self, idx)
        events.EventManager().triggerEvent(EVT_EXPORTABLE_CREATED, exportable)

        return exportable

    def deleteExportable(self, idx):
        '''
        deletes all attribute for the given exportable
        '''
        cmds.removeMultiInstance('%s.%s[%d]' % (self.node, self.ATTR_NODES, idx), b=True)
        cmds.removeMultiInstance('%s.%s[%d]' % (self.node, self.ATTR_DATA, idx), b=True)

        events.EventManager().triggerEvent(EVT_EXPORTABLE_DELETED, idx)

    def delete(self):
        '''
        deletes all of this ExportableContainer instance's attribute data

        NOTE: this method DOES NOT delete the maya node, it merely removes all
        markup on the node identifying it as an Exportable instance
        '''

        # first delete all contained exportables
        for idx in self._getIndices():
            self.deleteExportable(idx)

    def isUsed(self):
        return bool(len(self))

class Exportable(object):
    __metaclass__ = cls_types.trackableTypeFactory()

    TYPE_DICT = {}

    SEL_CON_NAME = 'TB_exportableIsolationSelection'

    @classmethod
    def DefaultName(cls, scene=None):
        if scene is None:
            scene = getScene()

        return scene.name()

    DEFAULTS_DICT = {}

    def __new__(cls, container, idx):
        attrDict = TypedSerializableDict(container.node,
                                         '%s[%d]' % (ExportableContainer.ATTR_DATA, idx),
                                         cls.TYPE_DICT)

        if '_type' in attrDict:
            cls = cls.GetNamedSubclass(attrDict['_type'])
        else:
            defaultDict = dict(_type=cls.__name__, name=cls.DefaultName())

            # set any default attributes
            for attr, default in cls.DEFAULTS_DICT.iteritems():
                if callable(default):
                    default = default()

                defaultDict[attr] = default

            attrDict.update(defaultDict)

        return object.__new__(cls)

    def __init__(self, container, idx):
        self.container = container
        self._index = idx
        self._dict = TypedSerializableDict(container.node,
                                           '%s[%d]' % (ExportableContainer.ATTR_DATA, idx),
                                           self.TYPE_DICT)

    def __str__(self):
        return '%s[%d]: %s.%s' % (type(self).__name__, self._index, self.getAttr('name'), self.EXTENSION)

    def __repr__(self):
        return '%s(%r, %d)' % (type(self).__name__, self.container, self._index)

    def __eq__(self, other):
        return (self.container == other.container) and (self._index == other._index)

    def __ne__(self, other):
        return not self.__eq__(other)

    def setType(self, exportableCls):
        if not issubclass(exportableCls, Exportable):
            raise TypeError('%s is not an Exportable subclass' % exportableCls)

        # early out if this isn't actually a change
        if self.getAttr('_type') == exportableCls.__name__:
            return self

        # set the type attribute to the appropriate value
        self.setAttr('_type', exportableCls.__name__)

        # return a new instance - the type has been changed
        return exportableCls(self.container, self._index, self._dict)

    def nodes(self):
        return self.container.nodes(self._index)

    def setNodes(self, nodes):
        self.container.setNodes(self._index, nodes)

    def getNodesSet(self):
        return self.container.getNodesSet(self._index)

    def setNodesSet(self, setNode):
        self.container.setNodesSet(self._index, setNode)

    def filepath(self):
        relativePath = self.getAttr('path')
        if relativePath is None:
            relativePath = getScene().up() - path.TB_DATA

        filename = '%s.%s' % (self.getAttr('name'), self.EXTENSION)

        return path.TB_DATA / relativePath / filename

    def setFilepath(self, filepath):
        filepath = path.Path(filepath)
        relativePath = filepath.up() - path.TB_DATA
        if relativePath:
            self.setAttr('path', relativePath)

        self.setAttr('name', filepath.name())

    def dict(self):
        return self._dict

    def getAttr(self, attr):
        return self._dict.get(attr, None)

    def setAttr(self, attr, value):
        if value is not None:

            # this is a little hacky because the TypedSerializedDict already does this, but there is
            # no clean way to communicate that the value has changed, plus its an implementation
            # detail...  so just check it again
            d = self._dict
            oldValue = d.get(attr)

            self._dict[attr] = value
            if attr == 'name' and oldValue != value:
                nodesSet = self.getNodesSet()

                # if we have a non-referenced nodes set, try to rename it
                if nodesSet and not cmds.referenceQuery(nodesSet, inr=True):
                    try:
                        cmds.rename(nodesSet, value)

                    # if we fail to rename the node, no big deal...  This should really only happen
                    # if the node is locked for some reason, so leave it.
                    except RuntimeError: pass

        # if the value is None, this is interpreted as a delete attr
        else:
            self.delAttr(attr)

        events.EventManager().triggerEvent(EVT_SET_ATTR, self, attr, value)

    def hasAttr(self, attr):
        return attr in self._dict

    def delAttr(self, attr):
        del self._dict[attr]

    def iterAttrValueTypes(self, skipProtected=True):
        for attr, value in self._dict.iteritems():
            if skipProtected and attr.startswith('_'):
                continue

            yield attr, value, self.TYPE_DICT.get(attr, unicode)

    def delete(self):
        self.container.deleteExportable(self._index)

    @maya_decorators.d_showWaitCursor
    @maya_decorators.d_maintainSceneSelection
    def export(self):

        thisScene = getScene()
        defaultChangeDesc = 'Exported from %s' % thisScene
        exportFilepath = self.filepath()

        cmds.select(self.nodes())
        try:
            exportFilepath.up().create()

            # now perform the export with the EditAddContext on the file
            with simple_p4.ChangeContext(defaultChangeDesc, True) as change:
                with simple_p4.EditAddContext(exportFilepath, change):
                    self._performExport(exportFilepath)

                # add this maya scene to the changelist if its not already in one
                change.addFileIfInDefaultChange(thisScene)

        except:
            logger.error('Failed to export "%r"' % self, exc_info=1)

        logger.info('Successfully exported %s' % exportFilepath)

    def _performExport(self, filepath):
        '''
        should be defined by typed subclasses

        This gets called when the Exportable instance is actually exported.  The export
        method (which calls this one) handles all perforce integration, so this method
        can just implement the export logic
        '''
        raise NotImplemented

    def isolate(self):
        # create a selection connection to store the visible objects
        if cmds.selectionConnection(self.SEL_CON_NAME, q=True, ex=True):
            con = self.SEL_CON_NAME
            cmds.selectionConnection(self.SEL_CON_NAME, e=True, clear=True)
        else:
            con = cmds.selectionConnection(self.SEL_CON_NAME)

        # add the nodes to it and make its set the same as this exportable's nodes set so we can identify
        # the active exportable later
        #cmds.selectionConnection(con, e=True, object=self.getNodesSet())
        for node in self.nodes():
            cmds.selectionConnection(con, e=True, select=node)

        # now iterate over all model editors and set the selection
        for editor in getVisibleEditors():
            cmds.modelEditor(editor, e=True, viewSelected=True, mainListConnection=con)

        # trigger an event to let the world know that an exportable has been isolated
        events.EventManager().triggerEvent(EVT_EXPORTABLE_ISOLATED, self)

    def isIsolated(self):
        name = self.SEL_CON_NAME
        if cmds.selectionConnection(name, q=True, ex=True):
            for editor in getVisibleEditors():
                editorCon = cmds.modelEditor(editor, q=True, mainListConnection=True)

                # ok so we've determined that AN exportable is being isolated, but is it THIS one?
                if editorCon == name:
                    return self.nodes() == cmds.selectionConnection(name, q=True, object=True)

        return False

    @classmethod
    def UnIsolate(cls):
        '''
        This is a class method for semantic distinction.

        Un-isolating isn't a function that belongs to an instance - it is more a function of the
        application...
        '''
        for editor in getVisibleEditors():
            cmds.modelEditor(editor, e=True, viewSelected=False)

        if cmds.selectionConnection(cls.SEL_CON_NAME, q=True, ex=True):
            cmds.deleteUI(cls.SEL_CON_NAME)

        events.EventManager().triggerEvent(EVT_EXPORTABLE_ISOLATED, None)

    def setIsolatedState(self, state):
        '''
        Convenience method to simplify isolation toggling
        '''
        if state:
            self.isolate()
        else:
            self.UnIsolate()

class SkinableExportable(Exportable):

    def nodes(self):
        nodes = super(SkinableExportable, self).nodes()
        if not nodes:
            return []

        allMeshes = cmds.listRelatives(nodes, ad=True, pa=True, type='mesh') or []
        if allMeshes:
            allMeshes = cmds.listRelatives(allMeshes, p=True, pa=True)

        # now get a list of joint influences from each mesh
        allJoints = []
        for mesh in allMeshes:
            skin = mel.eval('findRelatedSkinCluster %s' % mesh)
            if skin:
                allJoints += cmds.skinCluster(skin, q=True, influence=True) or []

        # now figure out the top joint in the skeleton
        skeletonRoots = []
        for j in allJoints:
            jTopParent = None
            for jParent in apiExtensions.iterParents(j):
                if cmds.nodeType(jParent) == 'joint':
                    jTopParent = jParent

            if jTopParent is not None:
                skeletonRoots.append(jTopParent)

        return misc.removeDupes(nodes + skeletonRoots)

class Model(SkinableExportable):
    EXTENSION = 'mdl'

    def _performExport(self, filepath):

        # <HACK!>
        # re-arrange the hierarchy - because the exporter currently is a bit broken.  It assumes everything being
        # exported lives in a single hierarchy...  So create that situation
        tmpXform = cmds.group(em=True)
        cmds.parent(self.nodes(), tmpXform)
        cmds.select(tmpXform)
        # </HACK!>

        cmds.file(filepath, f=True, type='Fury', es=True, ch=True, chn=False)

        # <HACK!>
        # undo the re-parenting shinanigans done above
        cmds.undo()
        cmds.undo()
        cmds.undo()
        # </HACK!>

def defaultAnimExportPath():
    relativePath = getScene().up() - path.TB_DATA

    return '%s/morpheme/%s' % (relativePath[0], relativePath[1:])

class Animation(Exportable):
    EXTENSION = 'xmd'

    TYPE_DICT = {'start': int,
                 'end': int,
                 }

    DEFAULTS_DICT = Exportable.DEFAULTS_DICT.copy()
    DEFAULTS_DICT['start'] = lambda: cmds.playbackOptions(q=True, min=True)
    DEFAULTS_DICT['end'] = lambda: cmds.playbackOptions(q=True, max=True)
    DEFAULTS_DICT['path'] = defaultAnimExportPath

    def nodes(self):
        nodes = super(Animation, self).nodes()
        if nodes:
            nodes += cmds.listRelatives(nodes, ad=True, pa=True, type='joint') or []

        return nodes

    def _performExport(self, filepath):

        # not sure if there is a nicer way to specify these options, but...  This seems to export the data we need
        optionStr = "-anim=1;-ascii=1;-xmd_new_anims=1;-blendshape=1;-camera=0;-clusters=0;-constraints=0;-compact=0;" \
            "-field=0;-ik=0;-jiggle=0;-jointcluster=0;-lattice=0;-layers=0;-light=0;-locator=0;-material=0;-mesh=0;" \
            "-particles=0;-vtxcolours=0;-vtxnormals=0;-nonlinear=0;-nurbscurve=0;-nurbssurface=0;-rlayers=0;" \
            "-sculpt=0;-sets=0;-selective=0;-shaders=0;-skinning=0;-textures=0;-volumes=0;-wire=0;-wrap=0;-timeline=0;" \
            "-remove_scale=1;-texture_filtering=0;-fbxskinfix=0;-stripNamespaces=1;-dynamic_attrs=0;" \
            "-exportTopLevelInWorldSpace=1;-xmd_version=4;-animTakeOptions=1;-scaling_factor=1;" \
            "-start=%d;-end=%d;" % (self.getAttr('start'), self.getAttr('end'))

        cmds.file(filepath, f=True, type='XMD Export', es=True, pr=True, options=optionStr)

    def getRoot(self):
        nodes = self.nodes()
        joints = cmds.ls(nodes, type='joint')
        joints = apiExtensions.sortByHierarchy(joints)
        if joints:
            return joints[0]

        return nodes[0]

    def getMeshes(self):
        nodes = self.nodes()
        meshes = cmds.ls(nodes + cmds.listRelatives(nodes, ad=True, pa=True), type='mesh')

        return [mesh for mesh in meshes if not cmds.getAttr('%s.intermediateObject' % mesh)]

    def playblastFilepath(self):
        filepath = getScene().up() / self.getAttr('name')

        return filepath.setExtension('mov')

    @maya_decorators.d_maintainSceneSelection
    def generatePlayblast(self, **kwargs):
        kwargs.setdefault('format', kwargs.pop('fmt', 'qt'))
        kwargs.setdefault('compression', kwargs.pop('c', 'H.264'))
        kwargs.setdefault('width', kwargs.pop('w', 800))
        kwargs.setdefault('height', kwargs.pop('h', 450))
        kwargs.setdefault('quality', kwargs.pop('qlt', 70))

        meshes = self.getMeshes()
        filepath = self.playblastFilepath()

        # set time to the start of the anim
        cmds.currentTime(self.getAttr('start'), e=True)

        # determine the root
        root = self.getRoot()

        # create a camera for the playblast
        cameraGrp = cmds.group(em=True)
        tempWin = cmds.window(title='%s playblast' % self, widthHeight=(kwargs['width'] + 10, kwargs['height'] + 50), menuBar=False)
        try:
            camera = cmds.camera()[0]
            cmds.parent(camera, cameraGrp)

            # finish setup of the playblast window - its easier to create a new one and delete it than it is
            # to find an existing one and set it up properly and then tearing that down again...  maya is
            # kinda painful when it comes to interacting with viewports...
            pane = cmds.paneLayout()
            panel = cmds.modelPanel(camera=camera)
            cmds.showWindow(tempWin)
            editor = cmds.modelPanel(panel, q=True, modelEditor=True)
            cmds.modelEditor(editor, e=True, allObjects=False, viewSelected=True)
            cmds.modelEditor(editor, e=True, displayAppearance='smoothShaded',
                             displayTextures=True, polymeshes=True, grid=True,
                             nurbsCurves=False, nurbsSurfaces=False, subdivSurfaces=False,
                             manipulators=False, selectionHiliteDisplay=False)

            # align the camera group to the root
            cmds.delete(cmds.parentConstraint(root, cameraGrp))

            # point constrain the camera to the root
            cmds.pointConstraint(root, cameraGrp)

            # fit the camera to the geometry
            bbox = cmds.exactWorldBoundingBox(meshes)
            centre = bbox[3]-bbox[0], bbox[4]-bbox[1], bbox[5]-bbox[2]
            cmds.select(meshes)
            cmds.move(centre[0], centre[1], centre[2], camera)
            cmds.move(-2, 0, 2, camera, r=True, os=True)
            cmds.viewLookAt(camera, position=centre)
            cmds.viewFit(camera, f=0.9)

            # create a selection connection to store the visible objects
            con = cmds.selectionConnection(parent=tempWin)
            for m in meshes:
                cmds.selectionConnection(con, e=True, select=m)

            cmds.modelEditor(editor, e=True, mainListConnection=con)
            cmds.setFocus(editor)

            # perform the playblast
            f = cmds.playblast(startTime=self.getAttr('start'),
                                  endTime=self.getAttr('end'),
                                  forceOverwrite=True, percent=100,
                                  sequenceTime=False, viewer=False,
                                  **kwargs)

            # playblast only goes to a tmp location - so copy it to the desired location
            # also, playblast returns the file without an extension...  win!
            path.Path(f).setExtension('mov').move(filepath)

            return filepath

        # set everything back to the way it was
        finally:
            cmds.deleteUI(tempWin)
            cmds.delete(cameraGrp)

class MorphemeRig(SkinableExportable):
    EXTENSION = 'xmd'

    DEFAULTS_DICT = Exportable.DEFAULTS_DICT.copy()
    DEFAULTS_DICT['path'] = defaultAnimExportPath

    def nodes(self):
        nodes = super(MorphemeRig, self).nodes()
        if not nodes:
            return []

        allMeshes = cmds.listRelatives(nodes, ad=True, pa=True, type='mesh') or []
        if allMeshes:
            allMeshes = cmds.listRelatives(allMeshes, p=True, pa=True)

        # now get a list of joint influences from each mesh
        allJoints = []
        allMeshes = misc.removeDupes(allMeshes)
        for mesh in allMeshes:
            skin = mel.eval('findRelatedSkinCluster %s' % mesh)
            allJoints += cmds.skinCluster(skin, q=True, influence=True) or []

        allJoints += cmds.listRelatives(allJoints, pa=True, ad=True, type='joint') or []

        allNodes = nodes + allMeshes + allJoints

        return misc.removeDupes(allNodes)

    def _performExport(self, filepath):
        optionStr = "-anim=0;-ascii=1;-xmd_new_mesh=1;-xmd_new_anims=1;-vtxuvs=0;-blendshape=0;-camera=0;-clusters=0;" \
            "-constraints=0;-compact=0;-field=0;-ik=0;-jiggle=0;-jointcluster=0;-lattice=0;-layers=0;-light=0;" \
            "-locator=0;-material=0;-mesh=1;-particles=0;-vtxcolours=0;-vtxnormals=1;-nonlinear=0;-nurbscurve=0;" \
            "-nurbssurface=0;-rlayers=0;-sculpt=0;-sets=0;-selective=0;-shaders=0;-skinning=1;-textures=0;-volumes=0;" \
            "-wire=0;-wrap=0;-timeline=0;-remove_scale=1;-texture_filtering=0;-fbxskinfix=0;-stripNamespaces=1;" \
            "-dynamic_attrs=0;-exportTopLevelInWorldSpace=1;-xmd_version=4;-animTakeOptions=1;-scaling_factor=1;-start=0;-end=0;"

        cmds.file(filepath, f=True, type='XMD Export', es=True, pr=True, options=optionStr)

def exportAll():
    convertPreStorage()
    container = ExportableContainer.GetOrCreate()
    for exportable in container:
        exportable.export()

def exportablesFromNode(node):
    '''
    returns all exportables the given node is contained by
    '''
    node = apiExtensions.asMObject(node)
    exportables = []
    for container in ExportableContainer.Iter():
        for exportable in container:
            containerNodes = apiExtensions.castToMObjects(exportable.nodes())
            if node in containerNodes:
                exportables.append(exportable)

    return exportables

def convertPreStorage():
    '''
    converts any pre-scene_storage nodes
    '''
    oldNodes = cmds.ls(type='objectSet') or []
    for node in oldNodes:

        # check to see if the node still exists - it may have been deleted
        if not cmds.objExists(node):
            continue

        # skip referenced nodes
        if cmds.referenceQuery(node, inr=True):
            continue

        if cmds.sets(node, q=True, text=True) == 'TB_exportableContainer':

            # if we have a candidate node, create the new style container
            container = ExportableContainer.GetOrCreate()

            # copy across version information so upconvert gets run
            oldVersion = cmds.getAttr('%s._version' % node)
            cmds.setAttr('%s.%s' % (container.node, ExportableContainer.ATTR_VERSION), oldVersion)

            # copy across connections to the node
            nodeAttrpath = '%s._nodes' % node
            indices = cmds.getAttr(nodeAttrpath, multiIndices=True) or []
            for idx in indices:

                # suck out the old data and delete it
                oldAttrpath = '%s._nodes[%d]' % (node, idx)
                oldNode = cmds.listConnections(oldAttrpath, d=False)
                cmds.removeMultiInstance(oldAttrpath, b=True)
                if oldNode:

                    # if the old node is a set, just plug it straight in
                    if cmds.nodeType(oldNode) == 'objectSet':
                        cmds.connectAttr('%s.message' % oldNode[0], '%s._nodes[%d]' % (container.node, idx))
                        cmds.sets(oldNode, add=container.getParentSet())

                    else:
                        container.setNodes(idx, oldNode)

            # copy across info from the data attr
            dataAttrpath = '%s._data' % node
            indices = cmds.getAttr(dataAttrpath, multiIndices=True) or []
            for idx in indices:

                # suck out the old data and delete it
                oldAttrpath = '%s._data[%d]' % (node, idx)
                oldData = cmds.getAttr(oldAttrpath)
                cmds.removeMultiInstance(oldAttrpath, b=True)

                # set the new data
                cmds.setAttr('%s._data[%d]' % (container.node, idx), oldData, type='string')

            # delete all old attributes and finally the node
            cmds.lockNode(node, l=False)
            cmds.deleteAttr('%s._version' % node)
            cmds.deleteAttr('%s._exportable' % node)

            cmds.delete(node)

def iterExportables(typeCls=None):
    container = ExportableContainer.GetOrCreate()
    for exportable in container:
        if typeCls is not None:
            if type(exportable) is not typeCls:
                continue

        yield exportable

def moveExportable(filepath, newFilepath):
    convertPreStorage()

    filepath = path.Path(filepath)
    filename = filepath.name()
    for exportable in iterExportables():

        # NOTE: we *should* be testing the filepath here, but this isn't reliable in all cases
        # for example, if the scene's storage is pre-V1, then the path attribute isn't explicitly
        # stored in the scene which means post conversion the filepath for the exportable isn't
        # going to be accurate...  So lets assume that the filename is somewhat unique
        if exportable.getAttr('name') == filename:
            exportable.setFilepath(newFilepath)

def fixDisconnectedAnimationExportables():
    for exportable in iterExportables(Animation):
        if exportable.getNodesSet() is None or not exportable.nodes():
            animExportSets = cmds.ls('animExportSet', type='objectSet', r=True)
            if animExportSets:
                if len(animExportSets) > 1:
                    raise ValueError("Oh noez!  More than one rig was found in the scene, not sure which one to use!")

                exportable.setNodesSet(animExportSets[0])

def generatePlayblasts():
    '''
    Returns a list of 2-tuples containing xmdFilepath, playblastFilepath for all scene exportables
    '''
    data = []
    for exportable in iterExportables(Animation):
        playblastFilepath = exportable.generatePlayblast()
        data.append((exportable.filepath(), playblastFilepath))

    return data

#end
