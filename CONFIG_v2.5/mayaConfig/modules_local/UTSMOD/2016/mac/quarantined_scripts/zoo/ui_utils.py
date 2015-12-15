
import sys
import inspect

from PySide.QtGui import *

import path

def iterParents(widget):
    parent = widget
    while True:
        parent = parent.parentWidget()
        if parent is None:
            break

        yield parent

def makeVariableMarginLayout(layoutCls, hsize, vsize):
    layout = layoutCls()
    layout.setContentsMargins(hsize, vsize, hsize, vsize)

    return layout

def makeHLayout(size=2):
    layout = makeVariableMarginLayout(QHBoxLayout, size, 0)
    layout.setSpacing(size)

    return layout

def makeVLayout(size=2):
    layout = makeVariableMarginLayout(QVBoxLayout, 0, size)
    layout.setSpacing(size)

    return layout

def makeHSeparator():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)

    return line

class CommonMixin(object):
    '''
    Mixin class to add shared functionality to Qt subclasses

    Provides functionality to emulate maya ability to parent script jobs to pieces of native UI
    '''

    @property
    def logger(self):
        try:
            return self._logger
        except AttributeError:
            try:
                thisModuleName = type(self).__module__.__name__
            except AttributeError:
                thisModuleName = 'UNNAMED'

            self._logger = logging.getLogger(thisModuleName)

        return self._logger

    def makeHLayout(self, size=2):
        return makeHLayout(size)

    def makeVLayout(self, size=2):
        return makeVLayout(size)

    def getIconFilepath(self, filename):
        '''
        Returns the filepath the icon with the given filename.
        '''
        pathsToSearch = map(path.Path, sys.path)

        # insert the location of this script first
        pathsToSearch.insert(0, path.Path(__file__).abs().up())

        # then insert the location of the script that is calling this method
        callingScriptFilepath = inspect.getfile(type(self))
        pathsToSearch.insert(1, path.Path(callingScriptFilepath).up())

        try:
            return path.findFirstInPaths(filename, pathsToSearch)
        except:
            return None

    def getIcon(self, filename):
        return QIcon(self.getIconFilepath(filename))

#end
