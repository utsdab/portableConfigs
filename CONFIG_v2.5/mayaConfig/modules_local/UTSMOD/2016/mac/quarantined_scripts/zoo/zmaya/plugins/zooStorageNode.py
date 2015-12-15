
import logging

import maya.OpenMaya as OpenMaya
import maya.OpenMayaMPx as OpenMayaMPx

logger = logging.getLogger('zooNodes')

class ZooStorageNode(OpenMayaMPx.MPxTransform):
    '''
    This is a typed node (for fast discovery) that can be used for scene level storage.
    '''

    NODE_ID = OpenMaya.MTypeId(0x00115970)
    NODE_TYPE_NAME = "zooStorageNode"

    @classmethod
    def Creator(cls):
        return OpenMayaMPx.asMPxPtr(cls())

    @classmethod
    def Init(cls):
        pass

def initializePlugin(mobject):
    mplugin = OpenMayaMPx.MFnPlugin(mobject, 'macaronikazoo', '1')

    try:
        mplugin.registerTransform(ZooStorageNode.NODE_TYPE_NAME, ZooStorageNode.NODE_ID,
                                  ZooStorageNode.Creator, ZooStorageNode.Init,
                                  OpenMayaMPx.MPxTransformationMatrix.creator,

                                  # baseTransformationMatrixId is an instance property, hence the instantiation
                                  OpenMayaMPx.MPxTransformationMatrix().baseTransformationMatrixId)
    except:
        logger.error("Failed to load zooNodes plugin:")
        raise

def uninitializePlugin(mobject):
    mplugin = OpenMayaMPx.MFnPlugin(mobject)

    try:
        mplugin.deregisterNode(ZooStorageNode.NODE_ID)
    except:
        logger.error("Failed to unload zooNodes plugin:")
        raise

#end