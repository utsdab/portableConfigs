
import logging

from maya import cmds
from maya import OpenMaya

from ... import vectors

from .. import apiExtensions
from .. import maya_decorators
from .. import skinWeights

from . import constants
from . import rig_utils
from . import baseSkeletonPart

logger = logging.getLogger(__name__)
VOLUME_SUFFIX = '__sbVolume'

def cylinderCreationDelegate(item, size, center):
    height = float(size[constants.BONE_AIM_AXIS])

    geo = cmds.polyCylinder(
        h=height * 0.95, r=0.01, ax=constants.BONE_AIM_VECTOR,
        sx=8, sy=round(height / 5.0), ch=False)[0]

    cmds.parent(geo, item, r=True)

    cmds.setAttr('%s.t' % geo, *center)

    # Finally remove the top and bottom cylinder caps - they're
    # always the last 2 faces
    #numFaces = mesh_utils.numFaces(geo)
    #cmds.delete('%s.f[%d:%d]' % (geo, numFaces - 2, numFaces - 1))

    return [geo]

def sphereCreationDelegate(item, size, centre):
    geo = cmds.polyPrimitive(ch=False)[0]

    cmds.parent(geo, item, r=True)
    cmds.setAttr('%s.t' % geo, *centre)
    cmds.setAttr('%s.s' % geo, *size)

    return [geo]

def cubeCreationDelegate(item, size, centre):
    height = float(size[constants.BONE_AIM_AXIS])

    geo = cmds.polyCube(ch=False)[0]
    cmds.polySmooth(geo, ch=False)

    cmds.parent(geo, item, r=True)
    cmds.setAttr('%s.t' % geo, *centre)
    cmds.setAttr('%s.s%s' % (geo, constants.BONE_AIM_AXIS.asName()), height)

    return [geo]

@maya_decorators.d_undoBlock
def buildVolumes(items, creationDelegate=cubeCreationDelegate, performShrinkWrap=False):
    """
    attempts to create volumes for the skeleton that reasonably tightly fits the character mesh.  these
    volumes can then be modified quickly using standard modelling tools, and can be then used to generate
    a fairly good skinning solution for the character mesh
    """

    # get the list of character meshes
    characterMeshes = baseSkeletonPart.getCharacterMeshes()

    for item in items:
        size, center = rig_utils.getJointSizeAndCentre(item, ignoreSkinning=True)

        # We just want to move the joint to the center of the
        # primary bone axis - not all axes...
        otherAxes = constants.BONE_AIM_AXIS.otherAxes()
        center[otherAxes[0]] = 0
        center[otherAxes[1]] = 0

        volumes = creationDelegate(item, size, center)
        for v in volumes:
            v = cmds.rename(v, '%s%s#' % (item, VOLUME_SUFFIX))

            # Freeze transforms
            # cmds.makeIdentity(v, a=True, t=True, r=True, s=True)

            # Perform the shrink wrap if appropriate
            if performShrinkWrap:
                shrinkWrap(v, characterMeshes)

def iterItemVolumes(items):
    """
    generator to yield a 2-tuple of each part item, and the list of volumes associated with it
    """
    for item in items:
        children = cmds.listRelatives(item, pa=True)
        if children:
            childMeshes = cmds.listRelatives(children, pa=True, type='mesh')

            if childMeshes:
                meshParents = [m for m in cmds.listRelatives(childMeshes, p=True, pa=True) if
                               cmds.nodeType(m) != 'joint']  # make sure not to remove joints...
                yield item, meshParents

@maya_decorators.d_undoBlock
def removeVolumes(items):
    """
    handles removing any existing volumes on the skeleton
    """
    for item, volumes in iterItemVolumes(items):
        if volumes:
            cmds.delete(volumes)

@maya_decorators.d_showWaitCursor
@maya_decorators.d_undoBlock
@maya_decorators.d_maintainSceneSelection
def buildAllVolumes():

    # align all parts first
    for part in baseSkeletonPart.SkeletonPart.Iter():
        if not part.compareAgainstHash():
            part.align()

    for part in baseSkeletonPart.SkeletonPart.Iter():
        buildVolumes(part.getItems())

def removeAllVolumes():
    for part in baseSkeletonPart.SkeletonPart.Iter():
        removeVolumes(part.getItems())

def shrinkWrap(obj, shrinkTo=None, performReverse=False):
    if shrinkTo is None:
        shrinkTo = baseSkeletonPart.getCharacterMeshes()

    if not isinstance(shrinkTo, (list, tuple)):
        shrinkTo = [shrinkTo]

    kWorld = OpenMaya.MSpace.kWorld

    obj = apiExtensions.asMObject(obj)
    shrinkTo = map(apiExtensions.asMObject, shrinkTo)

    # get the shape nodes...
    dagObj = OpenMaya.MDagPath.getAPathTo(obj)
    dagObj.extendToShape()

    dagShinkTo = map(OpenMaya.MDagPath.getAPathTo, shrinkTo)
    for dag in dagShinkTo:
        dag.extendToShape()

    fnShrinkTo = map(OpenMaya.MFnMesh, dagShinkTo)

    # construct the MMeshIntersector instances
    accellerators = []
    for _ in fnShrinkTo:
        a = OpenMaya.MFnMesh.autoUniformGridParams()
        accellerators.append(a)

    # now iterate over the verts in the obj, shoot rays outward in the direction of
    # the normal and try to fit as best as possible to the given shrink meshes
    itObjVerts = OpenMaya.MItMeshVertex(dagObj)
    vertPositions = []
    while not itObjVerts.isDone():
        intersects = []

        pos = itObjVerts.position(kWorld)
        actualPos = vectors.Vector((pos.x, pos.y, pos.z))

        normal = OpenMaya.MVector()
        itObjVerts.getNormal(normal, kWorld)

        # holy BAWLS maya is shite...  MVector and MFloatVector are COMPLETELY different
        # classes, and you can't construct one from the other?!  What kind of retard
        # wrote this API
        pos = OpenMaya.MFloatPoint(pos.x, pos.y, pos.z)
        normal = OpenMaya.MFloatVector(normal.x, normal.y, normal.z)
        normal.normalize()

        # now get ray intersections with the shrinkTo meshes
        for fnShrinkMesh, accel in zip(fnShrinkTo, accellerators):
            hitPoints = OpenMaya.MFloatPointArray()

            def go(rev=False):
                fnShrinkMesh.allIntersections(pos, normal,  # raySource, rayDirection
                                              None, None, False,  # faceIds, triIds, idsSorted

                                              kWorld, 1000, rev,  # space, maxParam, testBothDirs
                                              accel, True,  # accelParams, sortHits

                                              hitPoints,  # this is all we really care about...
                                              None, None, None, None, None)

            go()
            if performReverse and not hitPoints.length():
                go(performReverse)

            for n in range(hitPoints.length()):
                p = hitPoints[n]
                intersects.append(vectors.Vector((p.x, p.y, p.z)))  # deal with native vectors for now...

        # if there is just one intersection, easy peasy
        if len(intersects) == 1:
            newPosition = intersects[0]

        # otherwise we need to figure out which one is the best match...
        elif intersects:
            # first sort them by their distance to the vert - I
            # think they should be sorted already, but...
            sortByDist = [((p - actualPos).get_magnitude(), p) for p in intersects]
            sortByDist.sort()

            # not sure how much guesswork to do here - so just use the closest...
            newPosition = sortByDist[0][1]

        # if there are no matches just use the actual vert
        # position so we don't have to handle this case below...
        else:
            newPosition = actualPos

        vertPositions.append((actualPos, newPosition))

        itObjVerts.next()

    # now we have a list of vertex positions, figure out the
    # average delta and clamp deltas that are too far away
    # from this average
    deltaSum = 0
    numZeroDeltas = 0
    for pos, newPos in vertPositions:
        delta = (pos - newPos).get_magnitude()
        if not delta:
            numZeroDeltas += 1

        deltaSum += delta

    # if all deltas are zero, there is nothing to do... bail!
    if len(vertPositions) == numZeroDeltas:
        return

    deltaAverage = float(deltaSum) / (len(vertPositions) - numZeroDeltas)  # don't count deltas that are zero...
    clampedVertPositions = []

    MAX_DIVERGENCE = 1.1  # the maximum allowable variance from the average delta

    acceptableDelta = deltaAverage * MAX_DIVERGENCE
    for pos, newPos in vertPositions:
        if newPos is None:
            clampedVertPositions.append(None)
            continue

        delta = (pos - newPos).get_magnitude()

        # if the magnitude of the delta is too far from the average, scale down the magnitude
        if delta > acceptableDelta:
            deltaVector = newPos - pos
            deltaVector *= acceptableDelta / delta
            clampedVertPositions.append(pos + deltaVector)
        else:
            clampedVertPositions.append(newPos)

    # now set the vert positions
    n = 0
    itObjVerts.reset()
    while not itObjVerts.isDone():
        newPos = clampedVertPositions[n]

        position = OpenMaya.MPoint(*newPos)
        itObjVerts.setPosition(position, kWorld)

        n += 1
        itObjVerts.next()

def shrinkWrapSelection(shrinkTo=None):
    for obj in cmds.ls(sl=True, type=('mesh', 'transform')):
        cmds.makeIdentity(obj, a=True, t=True, r=True, s=True)
        shrinkWrap(obj, shrinkTo)

def getAllVolumes():

    # Find all volumes in the scene - this is pretty low tech, just
    # grep for all nodes with the appropriate suffix
    return cmds.ls('*%s*' % VOLUME_SUFFIX, type='transform')

@maya_decorators.d_undoBlock
def volumesToSkinning():

    # first grab all the volumes and combine them into a single mesh,
    # then generate weights from the original volumes (this should
    # result in the duplicates being rigidly skinned to the skeleton)
    # then transfer the weights from the combined mesh to the character
    # meshes
    allVolumes = getAllVolumes()

    # get the character meshes before we build the temp transfer surface
    charMeshes = baseSkeletonPart.getCharacterMeshes()

    # combine them all
    duplicateVolumes = cmds.duplicate(allVolumes, renameChildren=True)
    cmds.makeIdentity(duplicateVolumes, a=True, t=True, r=True, s=True)
    combinedVolumes = cmds.polyUnite(duplicateVolumes, ch=False)[0]

    # generate weights
    skinWeights.saveWeights(allVolumes)
    skinWeights.loadWeights([combinedVolumes], tolerance=2)

    # now transfer weights to the character meshes
    for charMesh in charMeshes:
        targetSkinCluster = skinWeights.transferSkinning(combinedVolumes, charMesh)

        # now lets do a little smoothing
        # skinCluster(targetSkinCluster, e=True, smoothWeights=0.65)

    """
    # JESUS!!!  for some weird as piss reason maya doesn't like this
    # python command: skinCluster(targetSkinCluster, q=True, smoothWeights=0.75)
    # nor this mel command: skinCluster -q -smoothWeights 0.75 targetSkinCluster
    # you NEED to run this mel command: skinCluster -smoothWeights 0.75 -q targetSkinCluster
    # which makes no goddamn sense - fuuuuuuuuuuuuuu alias!
    # not to mention that the stupid as piss command returns vert indices, not
    # components...  what a bullshit api.
    vertIdxs = mel.eval("skinCluster -smoothWeights 0.5 -q %s" % targetSkinCluster)

    baseStr = targetMesh +'.vtx[%d]'
    select([baseStr % idx for idx in vertIdxs])
    polySelectConstraint(pp=1, t=0x0001)  # expand the selection

    skinCluster(targetSkinCluster, e=True, smoothWeights=0.7, smoothWeightsMaxIterations=1)
    """

    # delete the combined meshes - we're done with them
    cmds.delete(combinedVolumes)

# end
