
import logging

from maya import cmds

from .. import path
from . import mel_utils
from . import reference_utils

from . import skinWeights

logger = logging.getLogger(__name__)

def getRefFilepathDictForNodes(nodes):
    """
    returns a dictionary keyed by the referenced filename.  Key values are dictionaries which are
    keyed by reference node (any file can be referenced multiple times) the value of which are the
    given nodes that are referenced.

    example:
    we have a scene with three references:
    refA comes from c:/someFile.ma
    refB comes from c:/someFile.ma
    refC comes from c:/anotherFile.ma

    we have 3 nodes: nodeA, nodeB and nodeC.

    nodeA comes from refA
    nodeB comes from refB
    nodeA comes from refC

    in this example running getRefFilepathDictForNodes( ('nodeA', 'nodeB', 'nodeC') ) would return:

    { 'c:/someFile.ma': { 'refA': [ 'nodeA' ], 'refB': [ 'nodeB' ],
      'c:/anotherFile.ma': { 'refC': [ 'nodeC' ] }
    """
    refFileDict = {}

    # Find the referenced files for the given meshes
    for node in nodes:
        isReferenced = cmds.referenceQuery(node, inr=True)
        if isReferenced:
            refNode = cmds.referenceQuery(node, referenceNode=True)
            refFile = path.Path(cmds.referenceQuery(node, filename=True, withoutCopyNumber=True))

            if refFile in refFileDict:
                refNodeDict = refFileDict[refFile]
            else:
                refNodeDict = refFileDict[refFile] = {}

            refNodeDict.setdefault(refNode, [])
            refNodeDict[refNode].append(node)

    return refFileDict

def storeWeightsById(mesh, namespaceToStrip=None):
    weightData = []

    skinCluster = mel_utils.MEL.findRelatedSkinCluster(mesh)
    verts = cmds.ls(cmds.polyListComponentConversion(mesh, toVertex=True), fl=True)
    for vert in verts:
        jointList = cmds.skinPercent(skinCluster, vert, ib=1e-4, q=True, transform=None)
        weightList = cmds.skinPercent(skinCluster, vert, ib=1e-4, q=True, value=True)

        # If there is a namespace to strip, we need to strip it from the vertex and the joint name...
        if namespaceToStrip is not None:
            vert = reference_utils.stripNamespaceFromNamePath(vert, namespaceToStrip)
            jointList = [reference_utils.stripNamespaceFromNamePath(j, namespaceToStrip) for j in jointList]

        weightData.append((vert, zip(jointList, weightList)))

    return weightData

def propagateWeightChangesToModel(meshes):
    '''
    Given a list of meshes to act on, this function will store the skin weights, remove any
    edits from the skin clusters that affect them, open the scene file the meshes come from
    and apply the weights to the geometry in that scene.

    This makes it possible to fix skinning problems while animating with minimal workflow
    changes
    '''
    curFile = path.Path(cmds.file(q=True, sn=True))
    referencedMeshes = getRefFilepathDictForNodes(meshes)

    if not curFile.name():
        logger.error("The current scene isn't saved - please save the current scene first before proceeding!")
        return

    for refFilepath, refNodeMeshDict in referencedMeshes.iteritems():
        referencesToUnload = []

        # Make sure we don't visit any of the meshes more than once
        meshesToUpdateWeightsOn = []
        meshesToUpdateWeightsOn_withNS = []
        for refNode, refMeshes in refNodeMeshDict.iteritems():

            # Get the maya filepath for the reference (with the "copy number")
            mayaFilepathForRef = cmds.referenceQuery(refNode, f=True)

            # Get the namespace for this reference
            refNodeNamespace = cmds.file(mayaFilepathForRef, q=True, namespace=True)

            # Check to see if there are any meshes in this reference that we need to
            # store weights for
            for mesh_withNS in refMeshes:
                mesh = reference_utils.stripNamespaceFromNamePath(mesh_withNS, refNodeNamespace)
                if mesh in meshesToUpdateWeightsOn:
                    continue

                meshesToUpdateWeightsOn.append(mesh)
                meshesToUpdateWeightsOn_withNS.append((mesh_withNS, refNodeNamespace))

            # Append the file to the list of reference files that we need to unload
            referencesToUnload.append(mayaFilepathForRef)

        # Get a list of skin cluster nodes - its actually the skin cluster nodes we
        # want to remove edits from...
        nodesToCleanRefEditsFrom = []
        for m, ns in meshesToUpdateWeightsOn_withNS:
            nodesToCleanRefEditsFrom.append(mel_utils.MEL.findRelatedSkinCluster(m))

        # Now we want to store out the weighting from the referenced meshes
        weights = []
        for mesh, meshNamespace in meshesToUpdateWeightsOn_withNS:
            weights.append(storeWeightsById(mesh, meshNamespace))

            # Also lets remove any ref edits from the mesh and all of its shape
            # nodes - this isn't strictly necessary, but I can't think of a
            # reason to make edits to these nodes outside of their native file
            nodesToCleanRefEditsFrom.append(mesh)
            nodesToCleanRefEditsFrom += cmds.listRelatives(mesh, s=True, pa=True) or []

        # Remove the skin weights reference edits from the meshes in the
        # current scene
        for f in referencesToUnload:
            cmds.file(f, unloadReference=True)

        # Remove ref edits from the shape node as well - this isn't strictly
        # necessary but there probably shouldn't be changes to the shape node
        # anyway
        for node in nodesToCleanRefEditsFrom:
            cmds.referenceEdit(node, removeEdits=True, successfulEdits=True, failedEdits=True)

        # Re-load references
        for f in referencesToUnload:
            cmds.file(f, loadReference=True)

        # Save this scene now that we've removed ref edits
        cmds.file(save=True, f=True)

        # Load up the referenced file and apply the weighting to the meshes
        # in that scene
        cmds.file(refFilepath, open=True, f=True)

        for mesh, weightData in zip(meshesToUpdateWeightsOn, weights):

            # If there is no weight data to store - keep loopin...
            if not weightData:
                continue

            skinCluster = mel_utils.MEL.findRelatedSkinCluster(mesh)
            if not skinCluster:
                logger.error("Couldn't find a skin cluster driving %s - skipping this mesh" % mesh)
                continue

            skinWeights.setSkinWeights(skinCluster, weightData)

        # Save the referenced scene now that we've applied the weights to it
        cmds.file(save=True, f=True)

    # Reload the original file
    cmds.file(curFile, o=True, f=True)

def propagateWeightChangesToModel_confirm():
    """
    simply wraps the propagateWeightChangesToModel function with a confirmation dialog
    """
    allMeshNodes = cmds.ls(type='mesh')
    allSkinnedMeshes = [mesh for mesh in allMeshNodes if mel_utils.MEL.findRelatedSkinCluster(mesh)]
    if not allSkinnedMeshes:
        logger.error("No skinned meshes can be found in the scene!  Aborting!")
        return

    BUTTONS = OK, CANCEL = 'Ok', 'Cancel'
    ret = cmds.confirmDialog(
        m='Are you sure you want to push skinning changes to the model?',
        t='Are you sure?', b=BUTTONS, db=CANCEL)

    if ret == OK:
        propagateWeightChangesToModel(allSkinnedMeshes)

#end
