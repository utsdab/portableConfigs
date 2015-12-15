
import contextlib

from maya import OpenMaya, OpenMayaUI

from maya import cmds

class Viewport(object):

    @classmethod
    def Iter(cls, visibleOnly=True):
        panelNames = cmds.getPanel(visiblePanels=True) if visibleOnly else \
            cmds.getPanel(allPanels=True)

        for panelName in panelNames:
            if cmds.modelPanel(panelName, exists=True):
                yield cls(panelName)

    @classmethod
    def Get(cls):
        '''
        return the best viewport available

        NOTE: this will be either the largest resolution viewport found.  It searches
        perspective views first, then orthogonal
        '''
        perspPanels = []
        orthoPanels = []
        view = OpenMayaUI.M3dView()
        for viewport in cls.Iter():
            OpenMayaUI.M3dView.getM3dViewFromModelPanel(viewport.panel, view)
            w = view.portWidth()
            h = view.portHeight()

            data = w*h, viewport
            if viewport.isOrthographic:
                orthoPanels.append(data)
            else:
                perspPanels.append(data)

        if perspPanels:
            perspPanels.sort()

            return perspPanels[-1][1]
        elif orthoPanels:
            orthoPanels.sort()

            return orthoPanels[-1][1]

        raise ValueError("No panels found!")

    def __init__(self, panel):
        self.panel = panel

    def __hash__(self):
        return hash(self.panel)

    def __eq__(self, other):
        return self.panel == other.panel

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return '%s("%s")' % (type(self).__name__, self.panel)

    @property
    def camera(self):
        return cmds.modelPanel(self.panel, q=True, camera=True)

    @camera.setter
    def camera(self, camera):
        cmds.modelPanel(self.panel, e=True, camera=camera)

    @property
    def isOrthographic(self):
        return cmds.getAttr('%s.orthographic' % self.camera)

    @property
    def isPerspective(self):
        return not self.isOrthographic

    @property
    def view(self):
        view = OpenMayaUI.M3dView()
        OpenMayaUI.M3dView.getM3dViewFromModelPanel(self.panel, view)

        return view

    @contextlib.contextmanager
    def _viewSetup(self, displayMask):
        view = self.view
        initDisplayMask = view.objectDisplay()
        initDisplayStyle = view.displayStyle()
        try:
            view.setObjectDisplay(displayMask)
            view.setDisplayStyle(OpenMayaUI.M3dView.kGouraudShaded)
            view.refresh(True, True)
            yield view

        finally:
            view.setObjectDisplay(initDisplayMask)
            view.setDisplayStyle(initDisplayStyle)

    def captureViewportImage(self, displayMask=OpenMayaUI.M3dView.kDisplayMeshes):
        """
        Captures the viewport contents using the readColorBuffer method on the M3dView
        """
        with self._viewSetup(displayMask) as view:

            # grab the buffer and write to disk
            img = OpenMaya.MImage()
            self.view.readColorBuffer(img, True)

            return img

    def generateIcon(self, iconFilepath, w=64, h=64, displayMask=OpenMayaUI.M3dView.kDisplayMeshes):
        """
        Captures the viewport contents using the readColorBuffer method on the M3dView
        """
        img = self.captureViewportImage(displayMask)
        img.resize(w, h)
        img.writeToFile(iconFilepath, 'png')

    def generatePlayblastIcon(self, iconFilepath, w=64, h=64, displayMask=OpenMayaUI.M3dView.kDisplayMeshes):
        """
        Captures the viewport contents using the playblast command
        """
        t = cmds.currentTime(q=True)
        with self._viewSetup(displayMask) as view:
            cmds.playblast(
                width=w, height=h,
                viewer=False,
                startTime=t, endTime=t,
                completeFilename=iconFilepath, format='image', forceOverwrite=True,
                compression='png', percent=100,
                showOrnaments=False, framePadding=4)

    def generatePlayblast(self, iconFilepath, startFrame, endFrame, frameIncrement=1, w=64, h=64, displayMask=OpenMayaUI.M3dView.kDisplayMeshes):
        with self._viewSetup(displayMask) as view:

            # construct a kwargs dict
            kwargs = dict(
                width=w, height=h,
                viewer=False,
                filename=iconFilepath, format='image', forceOverwrite=True,
                compression='jpg', quality=70,
                percent=100, showOrnaments=False, framePadding=4,
            )

            # make sure the frame increment isn't less than 1
            if frameIncrement < 1:
                frameIncrement = 1

            # if its exactly 1, then easy peasy, just define the start and end frames
            if frameIncrement == 1:
                kwargs['startTime'] = startFrame
                kwargs['endTime'] = endFrame
            else:
                # if skip isn't 1, then we need to explicitly define all frames to blast
                def frameGenerator():
                    fr = startFrame
                    while fr <= endFrame:
                        yield(int(fr))
                        fr += frameIncrement

                kwargs['fr'] = list(map(int, frameGenerator()))

            # helpfully (or annoyingly I guess, depending on your needs) the playblast
            # command always writes frames out sequentially, so even with a
            # frameIncrement > 1 the image files on disk go from
            cmds.playblast(**kwargs)

#end
