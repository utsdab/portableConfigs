import logging

from maya import cmds

from .. import misc
from . import apiExtensions
from . import viewport_utils

logger = logging.getLogger(__name__)

# Make sure the storage node plugin is loaded
cmds.loadPlugin('zooStorageNode.py', quiet=True)

class Shot(object):
    def __init__(self, time, camera, shotIdx):
        self.time = time
        self.camera = camera
        self.shotIdx = shotIdx

class Shots(object):
    NODE_TYPE = 'zooStorageNode'

    # Attr name for identifying shots nodes
    ID_ATTR_NAME = 'zooShots'
    _ID_ATTR_TEMPLATE = '%s.' + ID_ATTR_NAME

    CAM_ATTR_NAME = 'cameras'
    _CAM_ATTR_TEMPLATE = '%s.' + CAM_ATTR_NAME
    _CAM_MULTI_ATTR_TEMPLATE = _CAM_ATTR_TEMPLATE + '[%d]'

    CUTS_ATTR_NAME = 'times'
    _CUTS_ATTR_TEMPLATE = '%s.' + CUTS_ATTR_NAME
    _CUTS_MULTI_ATTR_TEMPLATE = _CUTS_ATTR_TEMPLATE + '[%d]'

    SYNC_PANELS_ATTR_NAME = 'syncPanels'
    _SYNC_PANELS_ATTR_TEMPLATE = '%s.' + SYNC_PANELS_ATTR_NAME
    _SYNC_PANELS_MULTI_ATTR_TEMPLATE = _SYNC_PANELS_ATTR_TEMPLATE + '[%d]'

    SYNC_MODE_ATTR_NAME = 'syncMode'
    _SYNC_MODE_ATTR_TEMPLATE = '%s.' + SYNC_MODE_ATTR_NAME

    # These are the camera attributes that get connected together
    _CAMERA_ATTRS_TO_CONNECT = (
        'focalLength',
        'focusDistance',
        'fStop',
        'shutterAngle',
        'horizontalFilmAperture',
        'verticalFilmAperture',
        'lensSqueezeRatio',
        'filmFit',
        # 'overscan',
        'nearClipPlane',
        'farClipPlane',
    )

    # Sync mode enums
    SYNC_MODES = SYNC_AUTO, SYNC_NAMED, SYNC_NONE = range(3)

    @classmethod
    def IterSceneCameras(cls, includeOrtho=False, includeDefault=False):
        masterCams = set(s.masterCamera for s in cls.Iter())
        defaultCameras = set(('perspShape', 'topShape', 'frontShape', 'sideShape'))
        for cam in cmds.ls(type='camera'):

            # Always skip master cameras...
            if cam in masterCams:
                continue

            # Skip ortho cameras if desired
            if not includeOrtho and cmds.getAttr('%s.orthographic' % cam):
                continue

            # Skip default cameras if desired
            if not includeDefault and cam in defaultCameras:
                continue

            yield cam

    @classmethod
    def GetMasterCamera(cls, storageNode):

        # NOTE: not sure why, but if I don't use p=True here, maya returns the camera
        # transform instead of the shape node... Weird...
        cons = cmds.listConnections(cls._ID_ATTR_TEMPLATE % storageNode, d=False, type='camera', p=True)
        if cons:
            return cons[0].split('.')[0]

    @classmethod
    def Iter(cls):
        for node in cmds.ls(type=cls.NODE_TYPE):
            if cmds.objExists(cls._ID_ATTR_TEMPLATE % node):
                yield cls(node)

    @classmethod
    def Create(cls, camera=None):

        # Create a storage node to store data on
        storageNode = cmds.createNode(cls.NODE_TYPE)

        # Create the id attribute
        cmds.addAttr(storageNode, ln=cls.ID_ATTR_NAME, at='message')

        # If no existing camera exists and no camera has been defined, create one
        if camera is None:
            cameraTransform, camera = cmds.camera(name='zooShotsMasterCam')

        self = cls(storageNode)
        self._ensureAttrsExist()
        self.masterCamera = camera
        self.rebuild()

        return self

    @classmethod
    def Get(cls, create=True):
        for s in cls.Iter():
            return s

        if create:
            return cls.Create()

    def __init__(self, storageNode):
        self.node = apiExtensions.asMObject(storageNode)

    def _ensureAttrsExist(self):
        if not cmds.objExists(self._CAM_ATTR_TEMPLATE % self.node):
            cmds.addAttr(self.node, ln=self.CAM_ATTR_NAME, at='message', multi=True, indexMatters=True)

        if not cmds.objExists(self._CUTS_ATTR_TEMPLATE % self.node):
            cmds.addAttr(self.node, ln=self.CUTS_ATTR_NAME, at='double', multi=True, indexMatters=True)

        if not cmds.objExists(self._SYNC_PANELS_ATTR_TEMPLATE % self.node):
            cmds.addAttr(self.node, ln=self.SYNC_PANELS_ATTR_NAME, dt='string', multi=True, indexMatters=False)

        if not cmds.objExists(self._SYNC_MODE_ATTR_TEMPLATE % self.node):
            cmds.addAttr(self.node, ln=self.SYNC_MODE_ATTR_NAME, at='long')

    @property
    def masterCamera(self):
        return self.GetMasterCamera(self.node)

    @masterCamera.setter
    def masterCamera(self, camera):
        if cmds.nodeType(camera) != 'camera':
            raise Exception('%s isn\'t a camera node!')

        try:
            cmds.connectAttr('%s.message' % camera, self._ID_ATTR_TEMPLATE % self.node)

        # This happens if the camera is already connected...
        except RuntimeError:
            pass

    @property
    def syncMode(self):
        self._ensureAttrsExist()
        return cmds.getAttr(self._SYNC_MODE_ATTR_TEMPLATE % self.node)

    @syncMode.setter
    def syncMode(self, mode):
        self._ensureAttrsExist()
        if mode not in self.SYNC_MODES:
            raise Exception('Invalid mode')

        cmds.setAttr(self._SYNC_MODE_ATTR_TEMPLATE % self.node, mode)

    def clearShots(self):
        for idx in cmds.getAttr(self._CAM_ATTR_TEMPLATE % self.node, multiIndices=True) or []:
            cmds.removeMultiInstance(self._CAM_MULTI_ATTR_TEMPLATE % (self.node, idx), b=True)

        for idx in cmds.getAttr(self._CUTS_ATTR_TEMPLATE % self.node, multiIndices=True) or []:
            cmds.removeMultiInstance(self._CUTS_MULTI_ATTR_TEMPLATE % (self.node, idx), b=True)

    def setShotCamera(self, shotIdx, camera):
        try:
            cmds.connectAttr('%s.message' % camera, self._CAM_MULTI_ATTR_TEMPLATE % (self.node, shotIdx), f=True)
        except RuntimeError:
            pass

    def getShotTime(self, shotIdx):
        attrpath = self._CUTS_ATTR_TEMPLATE % self.node

        return cmds.keyframe(attrpath, q=True, index=(shotIdx,), tc=True)

    def setShotTime(self, shotIdx, time):
        cmds.setAttr(self._CUTS_MULTI_ATTR_TEMPLATE % (self.node, shotIdx), time)

    def isCutAtTime(self, time):
        indices = cmds.getAttr(self._CUTS_ATTR_TEMPLATE % self.node, multiIndices=True) or []
        for idx in indices:
            t = cmds.getAttr(self._CUTS_MULTI_ATTR_TEMPLATE % (self.node, idx))
            if t == time:
                return True

        return False

    def createShot(self, time, camera=None):
        shotIdx = 0

        # If there is already a shot at the given time, don't do anything
        if self.isCutAtTime(time):
            return

        indices = cmds.getAttr(self._CUTS_ATTR_TEMPLATE % self.node, multiIndices=True)
        if indices:
            shotIdx = indices[-1] + 1

        self.setShotTime(shotIdx, time)
        if camera is not None:
            cmds.connectAttr('%s.message' % camera, self._CAM_MULTI_ATTR_TEMPLATE % (self.node, shotIdx))

    def deleteShot(self, shotIdx):
        cmds.removeMultiInstance(self._CAM_MULTI_ATTR_TEMPLATE % (self.node, shotIdx), b=True)
        cmds.removeMultiInstance(self._CUTS_MULTI_ATTR_TEMPLATE % (self.node, shotIdx), b=True)

    def iterShotData(self):
        '''
        Yields a 3-tuple containing: time, camera, index
        NOTE: yields unsorted data. To iterate over sorted data, use getSortedShotData
        '''
        indices = cmds.getAttr(self._CUTS_ATTR_TEMPLATE % self.node, multiIndices=True) or []
        for idx in indices:
            time = cmds.getAttr(self._CUTS_MULTI_ATTR_TEMPLATE % (self.node, idx))
            cam = None

            cons = cmds.listConnections(self._CAM_MULTI_ATTR_TEMPLATE % (self.node, idx), type='camera', p=True)
            if cons:
                cam = cons[0].split('.')[0]

            yield time, cam, idx

    def getSortedShotData(self):
        return sorted(self.iterShotData())

    def getShotAtTime(self, time):
        shotData = self.getSortedShotData()

        # If there is no shot data, return None
        if not shotData:
            return None

        # If the time is before the first shot, return None
        if time < shotData[0][0]:
            return None

        # If the time is after the cut time of the last shot, return it
        if time >= shotData[-1][0]:
            return Shot(*shotData[-1])

        # Otherwise find the interval the time falls within
        for n, (t, c, idx) in enumerate(shotData[:-1]):
            tNext = shotData[n + 1][0]

            # Check to see if it falls within this shot
            if time < tNext and t <= time:
                return Shot(t, c, idx)

    def addSyncPanel(self, panel):
        if not isinstance(panel, viewport_utils.Viewport):
            panel = viewport_utils.Viewport(panel)

        if panel in self.syncPanels:
            return

        indices = cmds.getAttr(self._SYNC_PANELS_ATTR_TEMPLATE % self.node, multiIndices=True) or []
        if indices:
            indices.sort()
            nextIdx = indices[-1] + 1
        else:
            nextIdx = 0

        cmds.setAttr(self._SYNC_PANELS_MULTI_ATTR_TEMPLATE % (self.node, nextIdx), panel.panel, type='string')

    def removeSyncPanel(self, panel):
        if isinstance(panel, viewport_utils.Viewport):
            panelName = panel.panel
        else:
            panelName = panel

        self._ensureAttrsExist()
        indices = cmds.getAttr(self._SYNC_PANELS_ATTR_TEMPLATE % self.node, multiIndices=True)
        for idx in indices:
            if cmds.getAttr(self._SYNC_PANELS_MULTI_ATTR_TEMPLATE % (self.node, idx)) == panelName:
                cmds.removeMultiInstance(self._SYNC_PANELS_MULTI_ATTR_TEMPLATE % (self.node, idx), b=True)
                break

    @property
    def syncPanels(self):
        syncMode = self.syncMode
        if syncMode == self.SYNC_NONE:
            return ()

        elif syncMode == self.SYNC_AUTO:
            cameras = set(cmds.listRelatives(c, p=True)[0]
                          for t, c, idx in self.iterShotData())

            return [p for p in viewport_utils.Viewport.Iter() if p.camera in cameras]

        elif syncMode == self.SYNC_NAMED:
            indices = cmds.getAttr(
                self._SYNC_PANELS_ATTR_TEMPLATE % self.node,
                multiIndices=True) or []

            return [viewport_utils.Viewport(cmds.getAttr(self._SYNC_PANELS_MULTI_ATTR_TEMPLATE % (self.node, idx)))
                    for idx in indices]

    def _clearMachinery(self):
        masterCamera = self.masterCamera
        if masterCamera is None:
            return

        # Remove the constraint
        camTransform = cmds.listRelatives(masterCamera, p=True)[0]
        cons = cmds.listConnections(camTransform, d=False, type='parentConstraint')
        if cons:
            cmds.delete(cons[0])

        # Remove the expression
        for attr in self._CAMERA_ATTRS_TO_CONNECT:
            cons = cmds.listConnections('%s.%s' % (masterCamera, attr), d=False, type='expression')
            if cons:
                cmds.delete(cons[0])
                break

    def rebuild(self):

        # Delete any existing machinery
        self._clearMachinery()

        # Get appropriate data from the shots node
        cameraCutPairs = []
        cameraTransforms = []
        for time, camera, shotIdx in self.getSortedShotData():

            # Skip this shot if it has no camera
            if camera is None:
                continue

            # The camera is the shape node, so get its transform
            cameraTransform = cmds.listRelatives(camera, p=True)[0]
            cameraTransforms.append(cameraTransform)

            # Find the index (if any) of the camera in the list
            cameraCutPairs.append((cameraTransform, time))

        if not cameraCutPairs:
            return

        # Remove duplicate values (but preserve order) from the camera transforms
        cameraTransforms = misc.removeDupes(cameraTransforms)

        # Now that we have the data, construct the constraint
        masterCamTransform = cmds.listRelatives(self.masterCamera, p=True)[0]
        constraint = cmds.parentConstraint(cameraTransforms + [masterCamTransform], mo=False)[0]

        # Remove the stupid attribute alias'
        for attr in cmds.listAttr(constraint, ud=True) or []:
            cmds.deleteAttr('%s.%s' % (constraint, attr))

        # Create the switching anim curves
        minTime = min(t for t, c, n in self.iterShotData())
        for n, cameraTransform in enumerate(cameraTransforms):
            attrpath = '%s.target[%d].targetWeight' % (constraint, n)

            # Create the anim curve the frame before the first cut
            cmds.setKeyframe(attrpath, t=minTime - 1, v=0, ott='step')

            # Now create a key for each cut for each camera
            for cutTransform, time in cameraCutPairs:
                value = 1 if cutTransform == cameraTransform else 0
                cmds.setKeyframe(attrpath, t=time, v=value, ott='step')
                # if n != len(startFrames) - 1:
                # cmds.setKeyframe(attrpath, t=startFrames[n+1], v=0, ott='step')

        # Create the switching expression for the constraint and all camera attrs
        expressionLines = []
        for attr in self._CAMERA_ATTRS_TO_CONNECT:

            # Construct the expression tokens
            lineToks = []
            for n, cameraTransform in enumerate(cameraTransforms):
                if cmds.getAttr('%s.%s' % (cameraTransform, attr), settable=True):
                    lineToks.append('(%s.%s * %s.target[%d].targetWeight)' % (cameraTransform, attr, constraint, n))
                else:
                    logger.info('The attribute %s on the shot camera (%s) is already connected - skipping' % (
                        attr, cameraTransform))

            # Construct the expression string
            expressionLine = '%s.%s = %s;' % (self.masterCamera, attr, ' + '.join(lineToks))
            expressionLines.append(expressionLine)

        # Create the expression
        expressionStr = '\n'.join(expressionLines)
        cmds.expression(s=expressionStr, name='zooShotsSwitchExpression')

        # Force a dg re-eval. Not sure why this is necessary, but it is...
        cmds.dgdirty(allPlugs=True)

# end
