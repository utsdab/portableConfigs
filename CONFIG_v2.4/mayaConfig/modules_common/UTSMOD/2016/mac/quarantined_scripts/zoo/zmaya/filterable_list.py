
import os

from PySide.QtGui import *
from PySide.QtCore import Qt, Signal

from maya import cmds, mel

from .. import path
from .. import list_widget

from base_ui import MayaQWidget, CommonMixin
from mel_utils import MEL

def isMayaFile(filepath):
    filepath = path.Path(filepath)
    return filepath.hasExtension('ma') or filepath.hasExtension('mb')

def openFile(filepath, silent=False):
    if isMayaFile(filepath):
        MEL.saveChanges('file -f -prompt %d -o "%s"' % (silent, filepath))
        MEL.addRecentFile(filepath, 'mayaAscii' if str.endswith(filepath, '.ma') else 'mayaBinary')

class FilterableListWidget(list_widget.FilterableListWidget, CommonMixin):
    pass

class ItemCls(list_widget.ItemCls):
    def displayStr(self):
        return self._item - self._args[0]

class FilterableFileListWidget(FilterableListWidget):

    def __init__(self):
        self._dir = None

        super(FilterableFileListWidget, self).__init__(ItemCls)

    def itemargs(self):
        return (self._dir,)

    @property
    def dir(self):
        return self._dir

    @dir.setter
    def dir(self, dirpath):
        self._dir = path.Path(dirpath)
        self.populate()

    def populate(self):
        self.clear()
        filterStr = self._filter.text()
        if self._dir:
            def test(f):
                fl = f.lower()
                isMayaFile = fl.endswith('.ma') or fl.endswith('mb')
                return isMayaFile and os.path.isfile(f)

            for f in self._dir._list_filesystem_items(test, True):
                if isMayaFile(f):
                    self.append(f)

#end