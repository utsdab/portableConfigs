
from maya.OpenMaya import MObjectArray, MIntArray
from maya.OpenMayaAnim import MFnBlendShapeDeformer
from maya import cmds, mel

import apiExtensions

class BlendShapeNode(object):
    """
    Abstracts maya's blendShape node and adds some high level functionality
    """

    @classmethod
    def FromTransform(cls, transform):
        '''
        this constructor takes a transform as an arg instead of the actual
        blendShape node
        '''
        shapes = cmds.listRelatives(transform, type='mesh')
        historyNodes = cmds.listHistory(shapes)
        if historyNodes is None:
            raise ValueError("Couldn't find a blendShape node connected to any of the shapes under %s" % transform)

        blendShapeNodes = []
        for node in historyNodes:
            if cmds.nodeType(node) =='blendShape':
                blendShapeNodes.append(node)

        if len(blendShapeNodes) != 1:
            raise ValueError("Found more than one blendShape node driving shapes under under %s" % transform)

        return cls(blendShapeNodes[0])

    def __init__(self, node):
        self._node = apiExtensions.asMObject(node)
        self._mfn = MFnBlendShapeDeformer(self._node)

        tmp = MObjectArray()
        self._mfn.getBaseObjects(tmp)

        if len(tmp) > 1:
            raise Exception("Not sure what to do here - multiple dest objs found!")

        # NOTE: need to copy the MObject here otherwise the maya API seems to gc it when the object array
        # goes out of scope
        self._mesh = apiExtensions.MObject(tmp[0])
        self._transform = self._mesh.getParent()

    def iterTargetIndexPairs(self):
        aliasList = cmds.aliasAttr(self._node, q=True)
        if aliasList is None:
            raise AttributeError("No aliasAttr found on %s" % self._node)

        aliasIter = iter(aliasList)
        for alias in aliasIter:
            indexStr = aliasIter.next()
            idx = indexStr[7:][:-1]
            yield alias, int(idx)

    def getTargets(self):
        '''
        returns the list of targets (ie sliders)
        '''
        return [alias for alias, idx in self.iterTargetIndexPairs()]

    def getTargetIdx(self, name):
        name = str(name)
        for alias, idx in self.iterTargetIndexPairs():
            if alias == name:
                return idx

        raise AttributeError("target doesn't exist")

    def getTargetInbetweenWeights(self, name):
        '''
        will return a list of weight values for all the inbetween shapes for a given target
        '''
        idx = self.getTargetIdx(name)
        inbetweenWeights = MIntArray()
        self._mfn.targetItemIndexList(idx, self._mesh, inbetweenWeights)

        weights = []
        for val in inbetweenWeights:

            # NOTE: see the maya docs for MFnBlendShapeDeformer on what this voodoo code means...
            weights.append((val - 5000) / 1000.0)

        return weights

    def renameTarget(self, name, newName):
        idx = self.getTargetIdx(name)
        cmds.aliasAttr(newName, '%s.weight[%d]' % (self._node, idx))

    def expandTargetShapes(self, name):
        '''
        explodes all blend shape targets to actual meshes
        '''
        targetIdxPairs = list(self.iterTargetIndexPairs())

        # first set all weight values to zero
        for target, idx in targetIdxPairs:
            cmds.setAttr('%s.%s' % (self._node, target), 0)

        meshWeightPairs = []

        # now for each target, set the weights and extract the resulting shapes, putting them in groups as we go
        for target, idx in targetIdxPairs:
            cleanupCb = None
            targetAttrpath = '%s.%s' % (self._node, target)
            weights = self.getTargetInbetweenWeights(target)
            weights.sort()

            # maya is retarded - if the weight is over 10 you can't setAttr because blendshape weights have an
            # arbitrary range of -10 -> +10...  But we can set it beyond this limit by driving the attribute
            # via a connection, so create a temp
            if weights[-1] > 10:
                cmds.addAttr(self._node, ln='__blend_manager_shape_expander', at='double')
                tmpAttrpath = '%s.__blend_manager_shape_expander' % self._node
                cmds.connectAttr(tmpAttrpath, targetAttrpath)
                targetAttrpath = tmpAttrpath
                cleanupCb = lambda: cmds.deleteAttr(tmpAttrpath)

            for weight in self.getTargetInbetweenWeights(target):
                cmds.setAttr(targetAttrpath, weight)
                dupe = cmds.duplicate(self._mesh, returnRootsOnly=True, renameChildren=True)[0]
                dupe = apiExtensions.asMObject(dupe)
                cmds.rename(dupe, '%s__%s' % (target, weight))
                meshWeightPairs.append((dupe, weight))

                # delete any children
                dupeChildren = cmds.listRelatives(dupe, type='transform')
                if dupeChildren:
                    cmds.delete(dupeChildren)

            # set the weight value back to zero
            cmds.setAttr(targetAttrpath, 0)

            # run any tidy up callback
            if cleanupCb: cleanupCb()

        return meshWeightPairs

    def deleteHistory(self):
        '''
        deletes history while preserving blend shapes.  Useful for topology
        changes on meshes with blendshapes
        '''
        data = []
        for target in self.getTargets():
            meshWeightPairs = self.expandTargetShapes(target)
            data.append((target, meshWeightPairs))

        self._mfn = None
        self._node = None
        cmds.delete(self._mesh, ch=True)

        # construct a new blendShape node
        node = cmds.blendShape(self._transform)[0]
        self._node = apiExtensions.asMObject(node)
        self._mfn = MFnBlendShapeDeformer(self._node)

        for idx, (target, meshWeightPairs) in enumerate(data):
            for mesh, weight in meshWeightPairs:
                cmds.blendShape(self._node, e=True, target=(self._mesh, idx, mesh, weight))
                cmds.delete(mesh)

            self.renameTarget(mesh, target)

#end