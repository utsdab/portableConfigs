
from PySide.QtGui import *
from PySide.QtCore import Signal

from . import path

class _filesystemSelectionWidget(QWidget):
    pathChanged = Signal(str)

    def __init__(self):
        super(_filesystemSelectionWidget, self).__init__()

        # Construct the widgets
        self.labelWidget = QLabel()
        self.pathWidget = QLineEdit()
        self.browseWidget = QPushButton('Browse...')

        # Setup a directory completer for the line edit
        completer = QCompleter(self.pathWidget)
        filesystemModel = QFileSystemModel()
        completer.setModel(filesystemModel)
        self.pathWidget.setCompleter(completer)

        # Connect signals
        self.pathWidget.textEdited.connect(self._onEdited)
        self.pathWidget.textChanged.connect(self.pathChanged)
        self.browseWidget.clicked.connect(self._onBrowse)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.labelWidget)
        layout.addWidget(self.pathWidget, 1)
        layout.addWidget(self.browseWidget)

        self.setLayout(layout)

    @property
    def label(self):
        return self.labelWidget.text()

    @label.setter
    def label(self, label):
        self.labelWidget.setText(label)

    @property
    def path(self):
        return path.Path(self.pathWidget.text())

    @path.setter
    def path(self, path):
        self.pathWidget.setText(str(path))

    def _onEdited(self, text):
        if not text:
            return

        p = path.Path(text)
        while p:
            if p.exists():
                break

            p = p.up()

        if p:
            completer = self.pathWidget.completer()
            completer.model().setRootPath(p)
            completer.complete()

class FileSelectionWidget(_filesystemSelectionWidget):
    FILE_MODE = QFileDialog.FileMode.ExistingFile

    def _onBrowse(self):
        dlg = QFileDialog()

        # Only browse directories
        dlg.setFileMode(self.FILE_MODE)

        # Set a sensible default if possible
        if self.path.exists():
            if self.path.isFile():
                dlg.selectFile(self.path)
            elif self.path.isDir():
                dlg.setDirectory(self.path)

        # Display the dialog and set the dirpath if the dialog isn't cancelled
        if dlg.exec_() and dlg.selectedFiles():
            self.path = path.Path(dlg.selectedFiles()[0])

class DirSelectionWidget(_filesystemSelectionWidget):

    def _onBrowse(self):
        dlg = QFileDialog()

        # Only browse directories
        dlg.setFileMode(QFileDialog.FileMode.DirectoryOnly)

        # Set a sensible default if possible
        if self.path.exists():
            dlg.setDirectory(self.path)

        # Display the dialog and set the dirpath if the dialog isn't cancelled
        if dlg.exec_():
            self.path = dlg.directory().absolutePath()

#end
