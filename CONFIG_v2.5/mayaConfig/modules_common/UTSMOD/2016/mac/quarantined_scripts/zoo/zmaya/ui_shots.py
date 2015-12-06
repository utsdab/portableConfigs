
import logging

from PySide.QtGui import *
from PySide.QtCore import Qt, Signal, QRect, QRectF, QPoint

from maya import cmds

from . import shots
from . import base_ui
from . import maya_decorators
from . import viewport_utils

logger = logging.getLogger(__name__)

def clamp(value, minValue, maxValue):
    if value < minValue:
        return minValue

    if value > maxValue:
        return maxValue

    return value

class ShotsWidget(QWidget):
    class _DragState(object):
        def __init__(self):
            self.startPos = QPoint()
            self.idx = -1
            self.time = 0

        def getDragTime(self, widget, pos):
            assert isinstance(widget, ShotsWidget)

            delta = self.startPos - pos
            deltaPerc = delta.x() / float(widget.width())

            return self.time - deltaPerc * widget.range

    timeChangeBegin = Signal()
    timeChangeEnd = Signal()

    timeChanged = Signal(int) # arg is the time idx

    # Some UI pixel type padding magic numbers
    VPAD = 3
    HPAD = 3

    # Radius of rounded rect corners
    CORNER_RAD = 2

    # Width of the shot handle
    HANDLE_W = 20

    # Handle colour
    HANDLE_COLOR = QColor(150, 50, 0)
    NO_CAM_COLOR = QColor(128, 20, 0)

    def __init__(self):
        super(ShotsWidget, self).__init__()

        # This needs to be turned on so the widget receives mouse move events
        self.setMouseTracking(True)

        # Store a separate rect for drawing the shot widgets
        self._shotRect = QRect()

        # State variables
        self._time = 0
        self._dragging = False
        self._dragState = self._DragState()
        self._undoOpen = False

        # Defines whether handles snap to integer time values
        self.snap = True
        self.startTime = 0
        self.endTime = 100

        # These are expected to be instances of the Shot class
        self.shots = []

        self.update()

    @property
    def currentTime(self):
        return self._time

    @currentTime.setter
    def currentTime(self, time):
        self._time = time
        self.update()

    @property
    def times(self):
        return tuple(s.time for s in self.shots)

    @property
    def range(self):
        return float(self.endTime - self.startTime)

    def setRange(self, start, end):
        self.startTime = start
        self.endTime = end
        self.update()

    def autoSetRange(self):
        times = sorted(s.time for s in self.shots)
        self.startTime = times[0]
        self.endTime = times[-1]

    def _timeToX(self, t):
        tPerc = (t - self.startTime) / self.range
        return self._shotRect.left() + self._shotRect.width() * tPerc

    def xToTime(self, x):
        xPerc = x / float(self._shotRect.width())
        xPerc = clamp(xPerc, 0, 1)

        return self.startTime + xPerc * self.range

    def getShotLbl(self, shot):
        cam = shot.camera
        if not cam:
            return '<no camera>'

        return cmds.listRelatives(cam, p=True)[0]

    def _getShotIdxRect(self, idx):
        t = self.shots[idx].time
        x = self._timeToX(t)

        if idx == len(self.shots) - 1:

            # This is deliberately self.rect.right() so it fills to the end of the widget
            xNext = self.rect().right()
        else:
            tNext = self.shots[idx + 1].time
            xNext = self._timeToX(tNext)

        w = xNext - x - self.HPAD * 2

        return QRectF(x, self.VPAD, w, self._shotRect.height() - self.VPAD * 2 - 1)

    def _getShotIdxHandleRectFromShotRect(self, shotRect):
        pad = 3

        return QRectF(
            shotRect.left() + pad, shotRect.top() + pad,
            self.HANDLE_W, shotRect.height() - pad * 2)

    def _getShotIdxHandleRect(self, idx):
        return self._getShotIdxHandleRectFromShotRect(self._getShotIdxRect(idx))

    def getShotIdxUnder(self, pos):
        for idx, shot in enumerate(self.shots):
            shotRect = self._getShotIdxRect(idx)
            if shotRect.contains(pos):
                return idx

    def getShotIdxHandleUnder(self, pos):
        for idx, shot in enumerate(self.shots):
            shotRect = self._getShotIdxRect(idx)
            if shotRect.contains(pos):
                handleRect = self._getShotIdxHandleRectFromShotRect(shotRect)
                if handleRect.contains(pos):
                    return idx

    def update(self):

        # Arbitrary numbers to fudge min size
        minHFudge = 20
        minWFudge = 0 + self.HANDLE_W * 2

        # Update min bounds
        metrics = QFontMetrics(self.font())
        minW = sum(metrics.width(s.camera) + minWFudge for s in self.shots)
        minH = metrics.height() + self.VPAD * 2 + minHFudge

        self.setMinimumWidth(minW)
        self.setMinimumHeight(minH)

        # Call the super's update
        QWidget.update(self)

    def _drawHandle(self, shotIdx, painter, rectf, mouseInside):
        path = QPainterPath()
        path.addRoundedRect(rectf, self.CORNER_RAD, self.CORNER_RAD)

        # Fill and draw the rect
        fillColor = self.HANDLE_COLOR.lighter() if mouseInside else self.HANDLE_COLOR
        painter.fillPath(path, QBrush(fillColor))
        painter.setPen(QPen(self.HANDLE_COLOR.darker()))
        painter.drawPath(path)

        # Draw the time string
        metrics = QFontMetrics(self.font())
        time = self.shots[shotIdx].time
        timeLbl = str(int(time)) if time == int(time) else str(time)

        painter.drawText(
            rectf.center().x() - metrics.width(timeLbl) / 2.0,
            rectf.bottom() - self.VPAD,
            timeLbl)

    def resizeEvent(self, event):
        rect = self._shotRect = self.rect()
        rect.setLeft(rect.left() + self.HPAD)
        rect.setRight(rect.right() - self.HANDLE_W)

        # Call the super's resize event
        QWidget.resizeEvent(self, event)

    def paintEvent(self, event):
        painter = QPainter(self)

        # Draw the background
        palette = self.palette()
        bgBrush = QBrush(palette.window())
        painter.fillRect(0, 0, self.width(), self.height(), bgBrush)

        painter.setPen(QPen(palette.shadow().color()))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        # Construct the border pen
        borderPen = QPen(palette.dark().color())

        # Construct the text pen
        textPen = QPen(palette.buttonText().color())
        textNoCamPen = QPen(self.NO_CAM_COLOR)

        # Get the mouse position
        mousePos = self.mapFromGlobal(QCursor.pos())

        metrics = QFontMetrics(self.font())
        lblH = metrics.height()
        if not self.shots:
            noShotsLbl = 'Right click to add shots'
            center = self.rect().center()
            painter.setPen(textPen)
            painter.drawText(
                center.x() - metrics.width(noShotsLbl) / 2.0,
                center.y() + lblH / 2.0,
                noShotsLbl)

        for idx, shot in enumerate(self.shots):
            shotRect = self._getShotIdxRect(idx)

            # Figure out if the mouse is within this shot
            mouseInside = shotRect.contains(mousePos)

            # Create a rounded rect
            path = QPainterPath()
            path.addRoundedRect(shotRect, self.CORNER_RAD, self.CORNER_RAD)

            # Fill then draw the rect
            fillBrush = QBrush(palette.button().color().lighter()) if mouseInside else palette.button()
            painter.fillPath(path, fillBrush)
            painter.setPen(borderPen)
            painter.drawPath(path)

            # Draw the handle
            handleRect = self._getShotIdxHandleRectFromShotRect(shotRect)
            self._drawHandle(idx, painter, handleRect, handleRect.contains(mousePos))

            # Now draw the label on the shot
            painter.setPen(textPen if shot.camera else textNoCamPen)
            textRect = QRectF(shotRect)
            textRect.setLeft(handleRect.right() + self.HPAD)
            lbl = self.getShotLbl(shot)
            lblW = metrics.width(lbl)

            if lblW > textRect.width():
                lbl = '...'
                lblW = metrics.width(lbl)

            painter.drawText(
                textRect.center().x() - lblW / 2,
                shotRect.center().y() + lblH / 2,
                lbl)

        # Draw the current time rect
        x = self._timeToX(self._time)
        timeRect = QRectF(x, 0, self.HANDLE_W, self.height() - 1)
        timeBrush = QBrush(QColor(255, 0, 0, 64))
        timePen = QPen(QColor(255, 0, 0, 128))
        painter.fillRect(timeRect, timeBrush)
        painter.setPen(timePen)
        painter.drawRect(timeRect)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            return

        if event.button() == Qt.LeftButton:

            # Figure out which handle we're over
            idx = self.getShotIdxHandleUnder(event.pos())
            if idx is not None:

                # Set the dragging flag
                self._dragging = True

                # Store the initial state data
                self._dragState.startPos = event.pos()
                self._dragState.idx = idx
                self._dragState.time = self.shots[idx].time

                # Emit the change begin signal
                self.timeChangeBegin.emit()

        elif event.button() == Qt.MiddleButton:

            # Set the dragging flag
            self._dragging = True

            # Open an undo chunk
            cmds.undoInfo(openChunk=True)
            self._undoOpen = True

            # Set the current time
            time = round(self.xToTime(event.pos().x()))
            cmds.currentTime(time, e=True)

            # Store the initial state data
            self._dragState.startPos = event.pos()
            self._dragState.idx = None
            self._dragState.time = time

    def mouseReleaseEvent(self, event):
        if self._undoOpen:
            cmds.undoInfo(closeChunk=True)

        if self._dragging:

            # Clear the dragging flag and reset the drag state attr
            self._dragging = False
            self._dragState = self._DragState()

            # Emit the time change ended signal
            self.timeChangeEnd.emit()

    def mouseMoveEvent(self, event):
        if self._dragging:
            if self._dragState.idx is None:
                time = round(self._dragState.getDragTime(self, event.pos()))
                cmds.currentTime(time, e=True)

            else:

                # Get the new time and construct new shot data
                time = self._dragState.getDragTime(self, event.pos())
                shot = self.shots[self._dragState.idx]

                if self.snap:
                    time = round(time)

                # Clamp the time so its within the start/end times
                time = clamp(time, self.startTime, self.endTime)

                # Store the new data on the appropriate Shot
                shot.time = time

                # Emit the time changed event
                self.timeChanged.emit(self._dragState.idx)

        self.update()

class Shots(base_ui.MayaQWidget):
    def __init__(self):
        super(Shots, self).__init__()

        # Get any existing shots node
        self.shots = shots.Shots.Get(False)

        # Create the UI
        self.syncCameraWidget = QCheckBox('Sync Viewport To Shot Camera')
        self.updateAllViewsWidget = QCheckBox('Update All Viewports')
        self.shotsWidget = ShotsWidget()

        # Set UI state
        self.syncCameraWidget.setEnabled(self.shots is not None)
        self.syncCameraWidget.setChecked(self.shots.syncMode != shots.Shots.SYNC_NONE
                                         if self.shots else False)

        # Hook up signals/slots
        self.syncCameraWidget.stateChanged.connect(self._syncChanged)
        self.shotsWidget.timeChangeEnd.connect(self._storeCuts)
        self.shotsWidget.contextMenuEvent = self._contextMenuEvt

        # Create and setup layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.syncCameraWidget, 0)
        layout.addWidget(self.shotsWidget, 1)

        self.setContentsMargins(10, 10, 10, 10)
        self.setLayout(layout)

        self._populate()

    def dockChanged(self):

        # Listen to playback range changes
        self.setSceneChangeCB(self.close)
        self.setPlaybackRangeCB(self._updateRange)
        self.setTimeChangeCB(self._updateTime)
        self.setTimeChangeCB(self._syncViewportCamera)
        self.setUndoCB(self._populate)

    def _populate(self):
        if self.shots is None:
            return

        s = self.shotsWidget.shots = []
        for time, cam, idx in self.shots.getSortedShotData():
            s.append(shots.Shot(time, cam, idx))

        # Set the range
        self._updateRange()

        # Set the current time
        self.shotsWidget.currentTime = cmds.currentTime(q=True)

    def _ensureNodeExists(self):
        if self.shots is None:
            self.shots = shots.Shots.Get(True)
            self.syncCameraWidget.setChecked(self.shots.syncMode != shots.Shots.SYNC_NONE)
            self.syncCameraWidget.setEnabled(True)

    def _updateRange(self):
        self.shotsWidget.setRange(
            cmds.playbackOptions(q=True, min=True),
            cmds.playbackOptions(q=True, max=True))

    def _updateTime(self, time, _):
        self.shotsWidget.currentTime = time.value()

    def syncViewportCamera(self, time):

        # If we don't have a shots instance yet, bail
        if not self.shots:
            return

        # Bail if the sync mode is none
        if self.shots.syncMode == shots.Shots.SYNC_NONE:
            return

        # Get the shot at the current time
        currentShot = self.shots.getShotAtTime(time)
        if currentShot is None:
            return

        # If the current shot doesn't have a camera, bail
        if not currentShot.camera:
            return

        # Change viewport cameras to the current shot's camera
        for viewport in self.shots.syncPanels:
            viewport.camera = currentShot.camera

    def _syncViewportCamera(self, mtime, _):
        self.syncViewportCamera(mtime.value())

    def _syncChanged(self, state):
        self.shots.syncMode = shots.Shots.SYNC_AUTO if state else shots.Shots.SYNC_NONE
        if state:
            self.syncViewportCamera(cmds.currentTime(q=True))

    def _buildSyncMenu(self):
        if self.shots is None:
            return

        menu = QMenu()

        def togglePanelSyncFactory(panel):
            def _():
                if panel in self.shots.syncPanels:
                    self.shots.removeSyncPanel(panel)
                else:
                    self.shots.addSyncPanel(panel)

            return _

        syncPanels = self.shots.syncPanels
        for panel in viewport_utils.Viewport.Iter(True):
            act = menu.addAction(
                '%s (panel: "%s")' % (panel.camera, panel.panel),
                togglePanelSyncFactory(panel))

            act.setCheckable(True)
            act.setChecked(panel in syncPanels)

        menu.addSeparator()

        updateAllViews = cmds.optionVar(q='timeSliderPlayView') == 'all'
        def toggleViewUpdate():
            cmds.optionVar(sv=('timeSliderPlayView', 'active' if updateAllViews else 'all'))

        act = menu.addAction('Update All Views When Scrubbing', toggleViewUpdate)
        act.setCheckable(True)
        act.setChecked(updateAllViews)

        menu.exec_(QCursor.pos())

    @maya_decorators.d_undoBlock
    def _storeCuts(self):
        self._ensureNodeExists()
        self.shots.clearShots()
        for shot in self.shotsWidget.shots:
            self.shots.createShot(shot.time, shot.camera)

        self.shots.rebuild()
        self.syncViewportCamera(cmds.currentTime(q=True))

    @maya_decorators.d_undoBlock
    def _createShot(self, time):
        self._ensureNodeExists()

        # If there aren't any shots, create the first one at the start frame
        if not self.shots.getSortedShotData():
            time = cmds.playbackOptions(min=True)

        if self.shotsWidget.snap:
            time = round(time)

        self.shots.createShot(time)
        self.shots.rebuild()
        self._populate()

    @maya_decorators.d_undoBlock
    def _setShotToCurrentTime(self, shot):
        self.shots.setShotTime(shot.shotIdx, cmds.currentTime(q=True))
        self.shots.rebuild()
        self._populate()

    @maya_decorators.d_undoBlock
    def _deleteShot(self, shot):
        self.shots.deleteShot(shot.shotIdx)
        self.shots.rebuild()
        self._populate()

    def _contextMenuEvt(self, event):
        menu = QMenu()

        time = self.shotsWidget.xToTime(event.pos().x())
        menu.addAction('Create Shot Here', lambda: self._createShot(time))

        # Store data about the shot under the cursor
        idx = self.shotsWidget.getShotIdxUnder(event.pos())
        if idx is not None:
            shot = self.shotsWidget.shots[idx]

            setCutItem = menu.addAction('Move Cut to Current Time', lambda: self._setShotToCurrentTime(shot))
            setCutItem.setEnabled(shot is not None)

            def setCamFactory(cam):
                def _():
                    self.shots.setShotCamera(shot.shotIdx, cam)
                    self.shots.rebuild()

                    logger.debug('Setting camera to %s for shot %d' % (cam, shot.shotIdx))
                    self.shotsWidget.shots[idx].camera = cam
                    self.shotsWidget.update()
                    self.syncViewportCamera(cmds.currentTime(q=True))

                return _

            changeMenuItem = menu.addMenu('Change Camera...')
            for cam in shots.Shots.IterSceneCameras():
                lbl = cmds.listRelatives(cam, p=True)[0]
                a = changeMenuItem.addAction(lbl, setCamFactory(cam))
                a.setCheckable(True)
                a.setChecked(cam == shot.camera)

            # If there are existing items, add a separator
            if changeMenuItem.actions():
                changeMenuItem.addSeparator()

            def createNewCameraAndSet():
                camera = cmds.camera()[1]
                setCamFactory(camera)()

            # Now add an option to create a new camera and set the shot to it
            changeMenuItem.addAction('Create New Camera', createNewCameraAndSet)

            # Add a camera selection item
            menu.addSeparator()
            menu.addAction('Select Camera', lambda: cmds.select(shot.camera))

            # Add a shot deletion option
            menu.addSeparator()
            lbl = self.shotsWidget.getShotLbl(shot)
            menu.addAction(
                'Delete Shot %d (using %s)' % (idx + 1, lbl),
                lambda: self._deleteShot(shot))

        menu.exec_(event.globalPos())

#end
