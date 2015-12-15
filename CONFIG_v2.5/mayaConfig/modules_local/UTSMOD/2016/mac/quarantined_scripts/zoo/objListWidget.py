
from PySide.QtGui import *

class ObjListWidget(QListWidget):
    def __init__(self, toStrDelegate=None):
        super(ObjListWidget, self).__init__()

        if toStrDelegate is None:
            toStrDelegate = lambda item: str(item)

        self._toStrDelegate = toStrDelegate

    def __contains__(self, item):
        for i in self.iteritems():
            if i == item:
                return True

        return False

    def append(self, obj):
        qitem = QListWidgetItem(self._toStrDelegate(obj))
        qitem._data = obj
        self.addItem(qitem)

    def remove(self, obj):
        idxToTake = []
        for n, item in enumerate(self.iterqitems()):
            if item._data == obj:
                idxToTake.append(n)

        idxToTake.reverse()
        for n in idxToTake:
            self.takeItem(n)

    def iterqitems(self):
        for n in xrange(self.count()):
            yield self.item(n)

    def iteritems(self):
        return (i._data for i in self.iterqitems())

    def items(self):
        return list(self.iteritems())

    def selectedItems(self):
        return [i._data for i in QListWidget.selectedItems(self) or []]

    def select(self, items, addToSelection=False):
        if addToSelection is False:
            self.clearSelection()

        if items is None:
            return

        for qitem in self.iterqitems():
            if qitem._data in items:
                qitem.setSelected(True)

    def updateItems(self):
        for qitem in self.iterqitems():
            qitem.setText(self._toStrDelegate(qitem._data))

#end
