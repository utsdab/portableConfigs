
from ..vectors import Matrix

MAYA_ROTATION_ORDER_VALUES = ROO_XYZ, ROO_YZX, ROO_ZXY, ROO_XZY, ROO_YXZ, ROO_ZYX = range(6)
MAYA_ROTATE_ORDER_STRS = "xyz", "yzx", "zxy", "xzy", "yxz", "zyx"

MATRIX_ROTATION_ORDER_CONVERSIONS_TO = Matrix.ToEulerXYZ, Matrix.ToEulerYZX, Matrix.ToEulerZXY, Matrix.ToEulerXZY, Matrix.ToEulerYXZ, Matrix.ToEulerZYX
MATRIX_ROTATION_ORDER_CONVERSIONS_FROM = Matrix.FromEulerXYZ, Matrix.FromEulerYZX, Matrix.FromEulerZXY, Matrix.FromEulerXZY, Matrix.FromEulerYXZ, Matrix.FromEulerZYX

#end
