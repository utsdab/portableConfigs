
'''
this script contains a bunch of useful poly mesh functionality.  at this stage its not really
much more than a bunch of functional scripts - there hasn't been any attempt to objectify any
of this stuff yet.  as it grows it may make sense to step back a bit and think about how to
design this a little better
'''

from maya.cmds import *
from maya.OpenMayaAnim import MFnSkinCluster

from maya import cmds
from maya import mel
from maya import OpenMaya

from ..vectors import Vector

import apiExtensions

def numVerts(mesh):
    return len(cmds.ls("%s.vtx[*]" % mesh, fl=True))

def numFaces(mesh):
    return len(cmds.ls("%s.f[*]" % mesh, fl=True))

def extractFaces(faceList, delete=False):
    '''
    extracts the given faces into a separate object - unlike the maya function, this is actually
    useful...  the given faces are extracted to a separate object, and can be optionally deleted from
    the original mesh if desired, or just duplicated out.
    '''
    newMeshes = []

    #get a list of meshes present in the facelist
    cDict = componentListToDict(faceList)
    for mesh, faces in cDict.iteritems():
        #is the mesh a shape or a transform - if its a shape, get its transform
        if cmds.nodeType(mesh) == 'mesh':
            mesh = cmds.listRelatives(mesh, pa=True, p=True)[ 0 ]

        dupeMesh = cmds.duplicate(mesh, renameChildren=True)[ 0 ]
        children = cmds.listRelatives(dupeMesh, pa=True, typ='transform')
        if children:
            cmds.delete(children)

        #unlock transform channels - if possible anyway
        try:
            for c in ('t', 'r', 's'):
                cmds.setAttr('%s.%s' % (dupeMesh, c), l=False)
                for ax in ('x', 'y', 'z'):
                    cmds.setAttr('%s.%s%s' % (dupeMesh, c, ax), l=False)
        except RuntimeError:
            pass

        #now delete all faces except those we want to keep
        cmds.select([ '%s.f[%d]' % (dupeMesh, idx) for idx in range(numFaces(dupeMesh)) ])
        cmds.select([ '%s.f[%d]' % (dupeMesh, idx) for idx in faces ], deselect=True)
        cmds.delete()

        newMeshes.append(dupeMesh)

    if delete:
        cmds.delete(faceList)

    return newMeshes

def extractMeshForEachJoint(joints, tolerance=1e-4):
    extractedMeshes = []
    for j in joints:
        meshes = extractFaces(jointFacesForMaya(j, tolerance))
        extractedMeshes += meshes
        for m in meshes:
            #unlock all xform attrs
            for at in 't', 'r', 's':
                cmds.setAttr('%s.%s' % (m, at), l=False)
                for ax in 'x', 'y', 'z':
                    cmds.setAttr('%s.%s%s' % (m, at, ax), l=False)

            cmds.parent(m, j)
            args = cmds.xform(j, q=True, ws=True, rp=True) + [ '%s.rotatePivot' % m, '%s.scalePivot' % m ]
            cmds.move(*args)
            cmds.makeIdentity(m, a=True, t=True, r=True, s=True)
            cmds.parent(m, world=True)

    return extractedMeshes

def extractMeshForJoints(joints, tolerance=0.25, expand=0):
    '''
    given a list of joints this will extract the mesh influenced by these joints into
    a separate object.  the default tolerance is high because verts are converted to
    faces which generally results in a larger than expected set of faces
    '''
    faces = []
    joints = map(str, joints)
    for j in joints:
        faces += jointFacesForMaya(j, tolerance, False)

    if not faces:
        return None

    theJoint = joints[ 0 ]

    meshes = extractFaces(faces)
    grp = cmds.group(em=True, name='%s_mesh#' % theJoint)
    cmds.delete(cmds.parentConstraint(theJoint, grp))

    for m in meshes:
        #unlock all xform attrs
        for at in 't', 'r', 's':
            cmds.setAttr('%s.%s' % (m, at), l=False)
            for ax in 'x', 'y', 'z':
                cmds.setAttr('%s.%s%s' % (m, at, ax), l=False)

        if expand > 0:
            cmds.polyMoveFacet("%s.vtx[*]" % m, ch=False, ltz=expand)

        #parent to the grp and freeze transforms to ensure the shape's space is the same as its new parent
        cmds.parent(m, grp)
        cmds.makeIdentity(m, a=True, t=True, r=True, s=True)

        #parent all shapes to the grp
        cmds.parent(cmds.listRelatives(m, s=True, pa=True), grp, add=True, s=True)

        #delete the mesh transform
        cmds.delete(m)

    #remove any intermediate objects...
    for shape in cmds.listRelatives(grp, s=True, pa=True):
        if cmds.getAttr('%s.intermediateObject' % shape):
            cmds.delete(shape)

    return grp

def isNodeVisible(node):
    '''
    its actually a bit tricky to determine whether a node is visible or not.  A node is hidden if any parent is hidden
    by either having a zero visibility attribute.  It could also be in a layer or be parented to a node in a layer that
    is turned off...

    This function will sort all that crap out and return a bool representing the visibility of the given node
    '''

    def isVisible(n):
        #obvious check first
        if not cmds.getAttr('%s.v' % node):
            return False

        #now check the layer
        displayLayer = cmds.listConnections('%s.drawOverride' % n, d=False, type='displayLayer')
        if displayLayer:
            if not cmds.getAttr('%s.v' % displayLayer[0]):
                return False

        return True

    #check the given node
    if not isVisible(node):
        return False

    #now walk up the DAG and check visibility on parents
    parent = cmds.listRelatives(node, p=True, pa=True)
    while parent:
        if not isVisible(parent[0]):
            return False

        parent = cmds.listRelatives(parent, p=True, pa=True)

    return True

def jointVerts(joint, tolerance=None, onlyVisibleMeshes=True):
    '''
    returns a dict containing data about the verts influences by the given joint - dict keys are mesh names the
    joint affects.  each dict value is a list of tuples containing (weight, idx) for the verts affected by the joint
    '''
    meshVerts = {}

    joint = apiExtensions.asMObject(joint)
    jointMDag = joint.dagPath()
    skins = list(set(cmds.listConnections(joint, s=False, type='skinCluster') or []))

    MObject = OpenMaya.MObject
    MDagPath = OpenMaya.MDagPath
    MDoubleArray = OpenMaya.MDoubleArray
    MSelectionList = OpenMaya.MSelectionList
    MIntArray = OpenMaya.MIntArray
    MFnSingleIndexedComponent = OpenMaya.MFnSingleIndexedComponent
    for skin in skins:
        skin = apiExtensions.asMObject(skin)
        mfnSkin = MFnSkinCluster(skin)

        mSel = MSelectionList()
        mWeights = MDoubleArray()
        mfnSkin.getPointsAffectedByInfluence(jointMDag, mSel, mWeights)

        for n in range(mSel.length()):
            mesh = MDagPath()
            component = MObject()
            mSel.getDagPath(n, mesh, component)

            #if we only want visible meshes - check to see that this mesh is visible
            if onlyVisibleMeshes:
                if not isNodeVisible(mesh):
                    continue

            c = MFnSingleIndexedComponent(component)
            idxs = MIntArray()
            c.getElements(idxs)

            if tolerance:
                meshVerts[mesh.partialPathName()] = [(w, idx) for idx, w in zip(idxs, mWeights) if w > tolerance]
            else:
                meshVerts[mesh.partialPathName()] = [(w, idx) for idx, w in zip(idxs, mWeights)]

    return meshVerts

def jointVertsForMaya(joint, tolerance=None, onlyVisibleMeshes=True):
    '''
    converts the dict returned by jointVerts into maya useable component names
    '''
    items = []
    for mesh, data in jointVerts(joint, tolerance, onlyVisibleMeshes).iteritems():
        items.extend(['%s.vtx[%d]' % (mesh, n) for w, n in data])

    return items

def jointFacesForMaya(joint, tolerance=None, contained=True):
    '''
    returns a list containing the faces influences by the given joint
    '''
    verts = jointVertsForMaya(joint, tolerance)
    if not verts:
        return []

    if contained:
        faceList = cmds.polyListComponentConversion(verts, toFace=True)
        if faceList:
            faceList = set(cmds.ls(faceList, fl=True))
            for f in cmds.ls(cmds.polyListComponentConversion(verts, toFace=True, border=True), fl=True):
                faceList.remove(f)

        jointFaces = list(faceList)
    else:
        jointFaces = cmds.ls(cmds.polyListComponentConversion(verts, toFace=True), fl=True)

    return jointFaces

def jointFaces(joint, tolerance=1e-4, contained=True):
    '''
    takes the list of maya component names from jointFacesForMaya and converts them to a dict with teh same format
    as jointVerts().  this is backwards for faces simply because its based on grabbing the verts, and transforming
    them to faces, and then back to a dict...
    '''
    return componentListToDict(jointFacesForMaya(joint, tolerance, contained))

def componentListToDict(componentList):
    componentDict = {}
    if not componentList:
        return componentDict

    #detect the prefix type
    suffix = componentList[ 0 ].split('.')[ 1 ]
    componentPrefix = suffix[ :suffix.find('[') ]

    prefixLen = len(componentPrefix) + 1  #add one because there is always a "[" after the component str
    for face in componentList:
        mesh, idStr = face.split('.')
        idx = int(idStr[ prefixLen:-1 ])

        try: componentDict[ mesh ].append(idx)
        except KeyError: componentDict[ mesh ] = [ idx ]

    return componentDict

class SkinWeightServer(object):

    def __init__(self, meshStr, skinCluster=None):
        self.mesh = meshStr

        if skinCluster is None:
            skinCluster = mel.eval('findRelatedSkinCluster("%s")' % meshStr)

        self.skinCluster = apiExtensions.asMObject(skinCluster)
        self.skinFn = MFnSkinCluster(self.skinCluster)

        # construct a dict mapping joint names to joint indices
        self._jIndices = {}
        self.refreshJointIndices()

    def refreshJointIndices(self):

        # Clear the existing joint indices dict
        self._jIndices = {}

        # getAttr -mi .matrix
        actualIndices = cmds.getAttr('%s.matrix' % self.skinCluster, mi=True)
        for actualIdx in actualIndices:
            self._jIndices[actualIdx] = cmds.listConnections(
                '%s.matrix[%d]' % (self.skinCluster, actualIdx), d=False)[0]

    def indexForJoint(self, joint):
        for jointIdx, aJoint in self._jIndices.iteritems():
            if apiExtensions.cmpNodes(aJoint, joint):
                return jointIdx

        #raise ValueError("No joint named '%s' exists in the skin cluster" % joint)

    def getVertWeightDict(self, vertIdx):
        weightDict = {}

        weights = cmds.getAttr('%s.weightList[%d].weights' % (self.skinCluster, vertIdx))[0]
        weightIndices = cmds.getAttr('%s.weightList[%d].weights' % (self.skinCluster, vertIdx), mi=True)

        for weight, weightIdx in zip(weights, weightIndices):
            jointName = self._jIndices.get(weightIdx, None)
            if jointName is not None:
                weightDict[str(jointName)] = weight

        return weightDict

    def setVertWeightDict(self, vertIdx, weightDict):

        # grab a list of existing weight indices
        weightIndices = cmds.getAttr('%s.weightList[%d].weights' % (self.skinCluster, vertIdx), mi=True)

        # now add values
        for jointStr, weight in weightDict.iteritems():
            jointIdx = self.indexForJoint(jointStr)
            cmds.setAttr('%s.weightList[%d].weights[%d]' % (self.skinCluster, vertIdx, jointIdx), weight)
            try:
                weightIndices.remove(jointIdx)
            except ValueError:
                pass

        # finally clear out all existing values from the skinning array for the vert
        for idx in weightIndices:
            #cmds.setAttr('%s.weightList[%d].weights[%d]' % (self.skinCluster, vertIdx, idx), 0)
            cmds.removeMultiInstance('%s.weightList[%d].weights[%d]' % (self.skinCluster, vertIdx, idx))

    def getInfluences(self):
        return cmds.skinCluster(self.skinCluster, q=True, inf=True)

    def addInfluence(self, joint):
        cmds.skinCluster(self.skinCluster, e=True, ignoreBindPose=True, addInfluence=joint, weight=0)
        self.refreshJointIndices()

def weightsToOther(joint, other):
    skinClusters = []
    for mesh, data in jointVerts(joint, None, False).iteritems():
        weightServer = SkinWeightServer(mesh)
        skinClusters.append(weightServer.skinCluster)

        if other not in weightServer.getInfluences():
            weightServer.addInfluence(other)

        for weight, vertIdx in data:
            weightDict = weightServer.getVertWeightDict(vertIdx)
            existingWeight = weightDict.pop(joint)
            try:
                weightDict[other] += existingWeight
            except KeyError:
                weightDict[other] = existingWeight

            weightServer.setVertWeightDict(vertIdx, weightDict)

    # now remove the joint from the skin
    for skinCluster in skinClusters:
        cmds.skinCluster(skinCluster, e=True, ri=joint)

def weightsToParent(joint):
    parent = cmds.listRelatives(joint, p=True, pa=True)
    if parent:
        weightsToOther(joint, parent[0])

def getBoundsForJoint(joint):
    '''
    returns bounding box data (as a 6-tuple: xmin, xmax, ymin etc...) for the geometry influenced by a given joint
    '''
    verts = jointVertsForMaya(joint, 0.01)
    Xs, Ys, Zs = [], [], []
    for v in verts:
        x, y, z = cmds.xform(v, q=True, ws=True, t=True)
        Xs.append(x)
        Ys.append(y)
        Zs.append(z)

    Xs.sort()
    Ys.sort()
    Zs.sort()

    try:
        return Xs[0], Xs[-1], Ys[0], Ys[-1], Zs[0], Zs[-1]
    except IndexError:
        drawSize = cmds.getAttr('%s.radius' % joint)
        drawSize /= 2
        return -drawSize, drawSize, -drawSize, drawSize, -drawSize, drawSize

def getAlignedBoundsForJoint(joint, threshold=0.65, onlyVisibleMeshes=True):
    '''
    looks at the verts the given joint/s and determines a local space (local to the first joint
    in the list if multiple are given) bounding box of the verts, and positions the hitbox
    accordingly

    if onlyVisibleMeshes is True, then only meshes that are visible in the viewport will
    contribute to the bounds
    '''
    theJoint = joint
    verts = []

    #so this is just to deal with the input arg being a tuple, list or string.  you can pass in a list
    #of joint names and the verts affected just get accumulated into a list, and the resulting bound
    #should be the inclusive bounding box for the given joints
    if isinstance(joint, (tuple,list)):
        theJoint = joint[0]
        for joint in joint:
            verts += jointVertsForMaya(joint, threshold, onlyVisibleMeshes)
    else:
        verts += jointVertsForMaya(joint, threshold, onlyVisibleMeshes)

    jointDag = apiExtensions.asMDagPath(theJoint)
    jointMatrix = jointDag.inclusiveMatrix()
    vJointPos = OpenMaya.MTransformationMatrix(jointMatrix).rotatePivot(OpenMaya.MSpace.kWorld) + OpenMaya.MTransformationMatrix(jointMatrix).getTranslation(OpenMaya.MSpace.kWorld)
    vJointPos = Vector([vJointPos.x, vJointPos.y, vJointPos.z])
    vJointBasisX = OpenMaya.MVector(-1, 0, 0) * jointMatrix
    vJointBasisY = OpenMaya.MVector(0, -1, 0) * jointMatrix
    vJointBasisZ = OpenMaya.MVector(0, 0, -1) * jointMatrix

    bbox = OpenMaya.MBoundingBox()
    for vert in verts:
        #get the position relative to the joint in question
        vPos = Vector(cmds.xform(vert, query=True, ws=True, t=True))
        vPos = vJointPos - vPos

        #now transform the joint relative position into the coordinate space of that joint
        #we do this so we can get the width, height and depth of the bounds of the verts
        #in the space oriented along the joint
        vPosInJointSpace = Vector((vPos.x, vPos.y, vPos.z))
        vPosInJointSpace = vPosInJointSpace.change_space(vJointBasisX, vJointBasisY, vJointBasisZ)
        bbox.expand(OpenMaya.MPoint(*vPosInJointSpace))

    minB, maxB = bbox.min(), bbox.max()

    return minB[0], minB[1], minB[2], maxB[0], maxB[1], maxB[2]

def getJointScale(joint):
    '''
    basically just returns the average bounding box side length...  is useful to use as an approximation for a
    joint's "size"
    '''
    xmn, xmx, ymn, ymx, zmn, zmx = getBoundsForJoint(joint)
    x = xmx - xmn
    y = ymx - ymn
    z = zmx - zmn

    return (x + y + z) / 3

#end
