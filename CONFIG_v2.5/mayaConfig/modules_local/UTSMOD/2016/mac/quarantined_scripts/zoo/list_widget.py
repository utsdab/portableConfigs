
import os

from PySide.QtGui import *
from PySide.QtCore import Qt, Signal

import path

import ui_utils

class ButtonLineEdit(QLineEdit, ui_utils.CommonMixin):
    clicked = Signal()

    def __init__(self, filename=None):
        super(ButtonLineEdit, self).__init__()

        self._button = QToolButton(self)
        self._button.hide()
        if filename:
            self.setIcon(filename)

    def setIcon(self, filename):
        icon = self.getIcon(filename)

        self._button.setIcon(icon)
        self._button.setCursor(Qt.ArrowCursor)
        self._button.setStyleSheet("QToolButton { border: none; padding: 0px; }")
        self._button.clicked.connect(self.clicked)

        frameWidth = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        self.setStyleSheet("QLineEdit { padding-right: %dpx; }" % (self._button.sizeHint().width() + frameWidth + 1))

        minSz = self.minimumSizeHint()
        self.setMinimumSize(max(minSz.width(), self._button.sizeHint().height() + frameWidth * 2 + 2),
                            max(minSz.height(), self._button.sizeHint().height() + frameWidth * 2 + 2))

        self._button.show()

    def resizeEvent(self, event):
        sz = self._button.sizeHint()
        frameWidth = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        self._button.move(self.rect().right() - frameWidth - sz.width(),
                          (self.rect().bottom() + 1 - sz.height()) / 2)

class ItemCls(QListWidgetItem):
    def __init__(self, item, *args):
        self._item = item
        self._args = args

        QListWidgetItem.__init__(self, self.displayStr())

    def displayStr(self):
        return '%s' % self._item

class ItemListWidget(QListWidget):
    ITEM_CLS = ItemCls

    def itemargs(self):
        return ()

    def append(self, item):
        listItem = self.ITEM_CLS(item, *self.itemargs())
        self.addItem(listItem)

        return listItem

    def iteritems(self):
        return (qitem._item for qitem in self.iterqitems())

    def items(self):
        return list(self.iteritems())

    def selectedItems(self):
        return [x._item for x in QListWidget.selectedItems(self) or []]

    def select(self, items):
        self.clearSelection()
        for qitem in self.iterqitems():
            if qitem._item in items:
                qitem.setSelected(True)

    def updateItems(self):
        for qitem in self.iterqitems():
            qitem.setText(qitem.displayStr())

    def iterqitems(self):
        for n in xrange(self.count()):
            yield self.item(n)

    def qitems(self):
        return list(self.iterqitems())

    def itemToQItem(self, item):
        for qitem in self.iterqitems():
            if qitem._item == item:
                return qitem

    def selectedQItems(self):
        return QListWidget.selectedItems(self) or []

def itemListWidgetFactory(itemCls):
    class CustomItemListWidget(ItemListWidget):
        ITEM_CLS = itemCls

    return CustomItemListWidget

class FilterableListWidget(QWidget):
    def __init__(self, itemCls=ItemCls):
        super(FilterableListWidget, self).__init__()

        self._filter = ButtonLineEdit('remove.png')
        self._filter.textEdited.connect(self.on_filterChange)
        self._filter.clicked.connect(self.on_filterClear)

        self._list = ItemListWidget()
        self._list.ITEM_CLS = itemCls

        hlayout = QHBoxLayout()
        hlayout.addWidget(QLabel('Filter:'))
        hlayout.addWidget(self._filter, 1)

        layout = QVBoxLayout()
        layout.addLayout(hlayout)
        layout.addWidget(self._list, 1)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

    def setSelectionMode(self, mode):
        self._list.setSelectionMode(mode)

    def itemargs(self):
        return ()

    def append(self, item):
        return self._list.append(item)

    def selectedItems(self):
        return self._list.selectedItems()

    def select(self, items):
        self._list.select(items)

    def updateItems(self):
        self._list.updateItems()

    def clear(self):
        self._list.clear()

    def filter(self):
        filterToks = self._filter.text().lower().split()
        if filterToks:
            for qitem in self._list.iterqitems():
                qItemStr = str(qitem).lower()
                qItemText = qitem.text().lower()
                hidden = not any((tok in qItemStr or tok in qItemText) for tok in filterToks)
                qitem.setHidden(hidden)
        else:
            for qitem in self._list.iterqitems():
                qitem.setHidden(False)

    def iteritems(self):
        return self._list.iteritems

    def items(self):
        return self._list.items()

    def iterqitems(self):
        return self._list.iterqitems

    def qitems(self):
        return self._list.qitems()

    def itemToQItem(self, item):
        return self._list.itemToQItem(item)

    def selectedQItems(self):
        return self._list.selectedQItems()

    def on_filterChange(self, newFilter):
        self.filter()

    def on_filterClear(self):
        self._filter.clear()
        self.filter()

#end