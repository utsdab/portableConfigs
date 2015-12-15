
import math

from maya import OpenMaya, OpenMayaUI, OpenMayaMPx, OpenMayaRender

from zoo import vectors
from zoo.zmaya import apiExtensions

glRenderer = OpenMayaRender.MHardwareRenderer.theRenderer()
glFuncTable = glRenderer.glFunctionTable()

def drawCircle(x, y, radius, sides=18):
    glFuncTable.glBegin(OpenMayaRender.MGL_TRIANGLE_FAN)
    glFuncTable.glVertex2f(x, y)
    angles = math.pi * 2
    for side in xrange(sides + 1):
        angle = angles / sides * side
        glFuncTable.glVertex2f(x + math.sin(angle) * radius, y + math.cos(angle) * radius)

    glFuncTable.glEnd()

def toPyMatrix(mmatrix):
    values = []
    for i in range(4):
        for j in range(4):
            values.append(mmatrix(i, j) )

    return vectors.Matrix(values)

def printMat(mat):
    for i in range(4):
        for j in range(4):
            print '%0.2f' % mat(i, j),

        print

class SelectoLocator(OpenMayaMPx.MPxLocatorNode):
    NODE_TYPE_NAME = 'selectoLocator'
    NODE_ID = OpenMaya.MTypeId(0x00115930)

    _size = None
    _colour = None
    alpha = None

    @classmethod
    def Creator(cls):
        return OpenMayaMPx.asMPxPtr(cls())

    @classmethod
    def Init(cls):
        def addToCb(mfn):
            mfn.setChannelBox(True)
            mfn.setKeyable(False)

        unit = OpenMaya.MFnUnitAttribute()

        cls._size = unit.create('size', 'sz', unit.kDistance, 100.0)
        unit.setMin(0.0)
        addToCb(unit)
        cls.addAttribute(cls._size)

        numeric = OpenMaya.MFnNumericAttribute()

        cls._colour = numeric.createColor('colour', 'clr')
        numeric.setDefault(1.0, 0.0, 0.0)  # NOTE: these need to be floats or maya throws an exception...
        addToCb(numeric)
        cls.addAttribute(cls._colour)

        cls._alpha = numeric.create('alpha', 'a', OpenMaya.MFnNumericData.kFloat, 0.8)
        numeric.setMin(0.0)
        numeric.setMax(1.0)
        addToCb(numeric)
        cls.addAttribute(cls._alpha)

    @property
    def pos(self):
        worldMatrix = self.thisMObject().dagPath().inclusiveMatrix()
        worldMatrixT = OpenMaya.MTransformationMatrix(worldMatrix)
        pos = OpenMaya.MPoint(worldMatrixT.getTranslation(OpenMaya.MSpace.kWorld))

        return pos

    @property
    def size(self):
        return OpenMaya.MPlug(self.thisMObject(), self._size).asFloat()

    @property
    def colour(self):
        colour = OpenMaya.MPlug(self.thisMObject(), self._colour)
        r, g, b = [colour.child(n).asFloat() for n in range(3)]

        return r, g, b

    @property
    def alpha(self):
        return OpenMaya.MPlug(self.thisMObject(), self._alpha).asFloat()

    def getScreenSize(self, view):
        '''
        Returns the size in screen space of the locator
        '''

        # Stupid, verbose API...
        xUtil = OpenMaya.MScriptUtil()
        yUtil = OpenMaya.MScriptUtil()
        xPtr = xUtil.asShortPtr()
        yPtr = yUtil.asShortPtr()

        # Get the centre point of the locator in the view
        view.worldToView(self.pos, xPtr, yPtr)
        x = OpenMaya.MScriptUtil.getShort(xPtr)

        # The locator's radius is in world units so transform this radius to screen space
        modelViewMat = OpenMaya.MMatrix()
        view.modelViewMatrix(modelViewMat)

        # Transform the world matrix to a view matrix
        path = self.thisMObject().dagPath()
        modelMat = path.inclusiveMatrix()
        viewMat = modelMat.inverse() * modelViewMat
        viewMatInv = toPyMatrix(viewMat.inverse())

        # Offset the x axis by the locator size
        modelViewMat = toPyMatrix(modelViewMat)
        modelViewMat[3][0] += self.size
        offsetModelMat = modelViewMat * viewMatInv
        offsetPos = OpenMaya.MPoint(*offsetModelMat[3][:3])

        # Determine the offset in view space
        view.worldToView(offsetPos, xPtr, yPtr)
        offsetScreenX = OpenMaya.MScriptUtil.getShort(xPtr)
        screenSize = abs(x - offsetScreenX)

        return screenSize

    def draw(self, view, path, style, status):
        shouldDraw = style & view.kGouraudShaded or style & view.kFlatShaded
        if not shouldDraw:
            return

        xUtil = OpenMaya.MScriptUtil()
        yUtil = OpenMaya.MScriptUtil()
        xPtr = xUtil.asShortPtr()
        yPtr = yUtil.asShortPtr()

        view.worldToView(self.pos, xPtr, yPtr)
        x = OpenMaya.MScriptUtil.getShort(xPtr)
        y = OpenMaya.MScriptUtil.getShort(yPtr)

        view.beginGL()
        glFuncTable.glPushAttrib(OpenMayaRender.MGL_CURRENT_BIT)

        glFuncTable.glMatrixMode(OpenMayaRender.MGL_PROJECTION)
        glFuncTable.glPushMatrix()
        glFuncTable.glLoadIdentity()

        glFuncTable.glOrtho(0, view.portWidth(), view.portHeight(), 0, 0, 1)
        glFuncTable.glMatrixMode(OpenMayaRender.MGL_MODELVIEW)
        glFuncTable.glPushMatrix()
        glFuncTable.glLoadIdentity()

        # set the colour
        r, g, b = self.colour

        isLead = status & view.kLead
        isSelected = status == 0
        if isLead or isSelected:
            col = self.colorRGB(status)
            r = col.r
            g = col.g
            b = col.b

        glFuncTable.glColor4f(r, g, b, 1 - self.alpha)

        # the y transform here is because the gl viewport seems to be flipped horizontally...
        drawCircle(x, view.portHeight() - y, self.getScreenSize(view))

        glFuncTable.glMatrixMode(OpenMayaRender.MGL_PROJECTION)
        glFuncTable.glPopMatrix()
        glFuncTable.glMatrixMode(OpenMayaRender.MGL_MODELVIEW)
        glFuncTable.glPopMatrix()

        glFuncTable.glPopAttrib()
        view.endGL()

    def drawLast_(self):
        return True

    def isTransparent_(self):
        return True

    def isBounded_(self):
        return False

    def boundingBox_(self):
        size = OpenMaya.MPlug(self.thisMObject(), self._size).asFloat()
        size *= 10

        bbox = OpenMaya.MBoundingBox()
        bbox.expand(OpenMaya.MPoint(size, size, size))
        bbox.expand(OpenMaya.MPoint(-size, -size, -size))

        return bbox

    def useClosestPointForSelection(self):
        return True

    def closestPoint(self, cursorRayPoint, cursorRayDir):

        # so this is a bit weird, but we need to do this in view space because
        # selectors are inherently view based selection regions.  So iterate
        # over all 3d views and see if the cursor ray point is inside the
        # selecto.  If it is, return the point
        nViews = OpenMayaUI.M3dView.numberOf3dViews()
        aView = OpenMayaUI.M3dView()
        for n in xrange(nViews):
            OpenMayaUI.M3dView.get3dView(n, aView)
            if not aView.isVisible():
                continue

            xUtil = OpenMaya.MScriptUtil()
            yUtil = OpenMaya.MScriptUtil()
            xPtr = xUtil.asShortPtr()
            yPtr = yUtil.asShortPtr()

            aView.worldToView(cursorRayPoint, xPtr, yPtr)
            x1 = OpenMaya.MScriptUtil.getShort(xPtr)
            y1 = OpenMaya.MScriptUtil.getShort(yPtr)

            aView.worldToView(self.pos, xPtr, yPtr)
            x2 = OpenMaya.MScriptUtil.getShort(xPtr)
            y2 = OpenMaya.MScriptUtil.getShort(yPtr)

            size = self.getScreenSize(aView)

            dist = vectors.Vector((x1, y1)) - vectors.Vector((x2, y2))
            cam = OpenMaya.MDagPath()
            aView.getCamera(cam)
            if dist.length() <= size:
                return cursorRayPoint

        return OpenMaya.MPoint(0, 0, 0)

def initializePlugin(mobject):
    mplugin = OpenMayaMPx.MFnPlugin(mobject, 'macaronikazoo', '1')

    try:
        mplugin.registerNode(SelectoLocator.NODE_TYPE_NAME,
                             SelectoLocator.NODE_ID,
                             SelectoLocator.Creator,
                             SelectoLocator.Init,
                             OpenMayaMPx.MPxNode.kLocatorNode)
    except:
        OpenMaya.MGlobal.displayError("Failed to load zooSelecto plugin:")
        raise

def uninitializePlugin(mobject):
    mplugin = OpenMayaMPx.MFnPlugin(mobject)

    try:
        mplugin.deregisterNode(SelectoLocator.NODE_ID)
    except:
        OpenMaya.MGlobal.displayError( "Failed to unload zooSelecto plugin:" )
        raise

#end
