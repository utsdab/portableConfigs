
import os
import glob

from zoo import path

class ImgSequence(object):
    """
    Represents a simple image sequence. The following assumptions are baked in:
    	* frame numbers are sequentially increasing
    	* filename has the convention <prefix>.####.<suffix>
    	  where the #### is a 4 number frame counter
    	* the sequence frame count discoverable by counting files matching the above convention
    """
    def __init__(self, filenamePrefix, suffix = '.jpg'):
        self.prefix = str(filenamePrefix)
        self.suffix = suffix
        self._fileCount = None
        self._startFrame = None
        self._imageCacheDict = {}

    @property
    def filenameGlob(self):
        return self.prefix + '.*' + self.suffix

    @property
    def filenameTemplate(self):
        return self.prefix + '.%04d' + self.suffix

    def setCounts(self):
        """
        If the files exist on disk, this method will set the start time based on the
        first file in the sequence
        """
        # try to discover the start frame
        self._fileCount = 0
        frameNumbers = []
        for f in glob.glob(self.filenameGlob):
            self._fileCount += 1
            d, fname = os.path.split(f)
            frameNumbers.append(int(fname.split('.')[-2]))

        self._startFrame = 0
        if len(frameNumbers) != 0:
            self._startFrame = min(frameNumbers)

    @property
    def startFrame(self):
        if self._startFrame is None:
            self.setCounts()

        return self._startFrame

    @property
    def fileCount(self):
        if self._fileCount is None:
            self.setCounts()

        return self._fileCount

    @property
    def endFrame(self):
        return self.startFrame + self.fileCount

    def getFrameFromPercent(self, percentage):
        return self.startFrame + int(self.fileCount * percentage)

    def getImage(self, n):
        from PySide.QtGui import QImage
        image = self._imageCacheDict.get(n, None)
        if image is None:
            filepath = self.filenameTemplate % n
            if path.Path(filepath).exists():
                image = self._imageCacheDict[n] = QImage(filepath)

        return image

    def getFiles(self):
        if self.fileCount is None:
            self.setCounts()

        start = self.startFrame
        end = self.startFrame + self.fileCount

        return [path.Path(self.filenameTemplate % n) for n in range(start, end)]

    def getImageFromPercent(self, percentage):
        return self.getImage(self.getFrameFromPercent(percentage))

#end