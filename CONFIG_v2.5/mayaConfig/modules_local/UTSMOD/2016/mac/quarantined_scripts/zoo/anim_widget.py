
from PySide.QtCore import QPoint, QSize
from PySide.QtGui import *

import imgSequence

class AnimWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)

        # enable mouse tracking so that we receive mouse move events
        self.setMouseTracking(True)

        self._image = None
        self._sequence = None

    def setSequence(self, filenamePrefix):
        self._sequence = imgSequence.ImgSequence(filenamePrefix)
        self._image = self._sequence.getImageFromPercent(0)
        self.updateGeometry()
        self.update()

    def setIcon(self, iconFilepath):
        self._sequence = None
        self._image = QImage(iconFilepath)
        self.updateGeometry()
        self.update()

    def mouseMoveEvent(self, moveEvent):
        if self._sequence is None:
            return

        xPercent = moveEvent.x() / float(self.width())
        self._image = self._sequence.getImageFromPercent(xPercent)
        self.update()

    def paintEvent(self, paintEvent):
        painter = QPainter(self)
        painter.drawImage(QPoint(0,0), self._image)

    def sizeHint(self):
        if self._image is None:
            return QSize(0, 0)

        return self._image.size()

#end
