
from ... import vectors

from . import rig_utils

# this is the axis the joint should bank around, in general the axis the "aims" at the child joint
BONE_AIM_VECTOR = rig_utils.MAYA_SIDE

# this is the axis of "primary rotation" for the joint.  for example, the elbow would rotate primarily
# in this axis, as would knees and fingers
BONE_ROTATE_VECTOR = rig_utils.MAYA_FWD

BONE_AIM_AXIS = vectors.Axis.FromVector(BONE_AIM_VECTOR)
BONE_ROTATE_AXIS = vectors.Axis.FromVector(BONE_ROTATE_VECTOR)

_tmp = BONE_AIM_AXIS.otherAxes()
_tmp.remove(BONE_ROTATE_AXIS)

# this is the "other" axis - ie the one thats not either BONE_AIM_AXIS or BONE_ROTATE_AXIS
BONE_OTHER_AXIS = _tmp[0]
BONE_OTHER_VECTOR = BONE_OTHER_AXIS.asVector()

del _tmp

#end
