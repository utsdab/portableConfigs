
import logging

from PySide.QtGui import *
from PySide.QtCore import Signal

from maya import cmds

from .. import path
from .. import file_selection_widget
from . import reference_utils
from . import base_ui

logger = logging.getLogger(__name__)

def getCommonParentDirpath(paths):
    '''
    Returns a common parent path for all the given filesystem paths
    '''

    # First make sure we have path.Path instances
    paths = [path.Path(p) for p in paths]

    # Bail if there are no paths
    if not paths:
        return None

    # Just return if there is only one path
    if len(paths) == 1:
        return paths[0]

    # Otherwise, find a common parent directory
    candidate = paths[0]
    while True:
        allUnder = True
        for p in paths:
            if not p.isUnder(candidate):
                allUnder = False
                if candidate.split() == 1:
                    return None

                candidate = candidate.up()
                break

        if allUnder:
            return candidate

def rebaseReferenceFilepaths(currentBaseDirpath, newBaseDirpath):
    refNodes = list(reference_utils.ReferenceNode.Iter())

    for n, refNode in enumerate(refNodes):
        filepath = refNode.getFilepath()
        if filepath.isUnder(currentBaseDirpath):
            newFilepath = newBaseDirpath / (filepath - currentBaseDirpath)
            print 'rebase data1', filepath, currentBaseDirpath, newBaseDirpath, newFilepath
            print 'rebase data2', newBaseDirpath, newFilepath
            refNode.setFilepath(newFilepath)
            logger.info('Rebasing:  %s to new path:  %s' % (filepath, newFilepath))

            yield refNode, n, len(refNodes)
        else:
            logger.warning('Skipped reference filepath:  %s  It doesn\'t live under %s' % (filepath, currentBaseDirpath))
            continue

    logger.info('Finished rebasing references')

class ReferenceRebaser(base_ui.MayaQWidget):
    REBASE_DIR_OPTIONVAR_NAME = 'zooReferenceRebaserDestDirpath'

    def __init__(self):
        super(ReferenceRebaser, self).__init__()

        self.setMinimumWidth(550)

        self.currentDirpathWidget = file_selection_widget.DirSelectionWidget()
        self.newDirpathWidget = file_selection_widget.DirSelectionWidget()
        self.performRebaseWidget = QPushButton('Perform Rebase')

        self.currentDirpathWidget.label = 'Current base directory'
        self.newDirpathWidget.label = 'New base directory'

        self.newDirpathWidget.pathChanged.connect(self._storeDirpaths)
        self.performRebaseWidget.clicked.connect(self._performRebase)

        # Init the directories
        commonBase = getCommonParentDirpath(reference_utils.ReferencedFile.Iter())
        if commonBase:
            self.currentDirpathWidget.path = commonBase

        if cmds.optionVar(ex=self.REBASE_DIR_OPTIONVAR_NAME):
            self.newDirpathWidget.path = cmds.optionVar(q=self.REBASE_DIR_OPTIONVAR_NAME)

        layout = QVBoxLayout()
        layout.addWidget(self.currentDirpathWidget)
        layout.addWidget(self.newDirpathWidget)
        layout.addWidget(self.performRebaseWidget)
        layout.addStretch(1)

        self.setLayout(layout)

    def _storeDirpaths(self, dirpath):
        cmds.optionVar(sv=(self.REBASE_DIR_OPTIONVAR_NAME, str(dirpath)))

    def _performRebase(self):
        curDirpath, newDirpath = self.currentDirpathWidget.path, self.newDirpathWidget.path
        if curDirpath == newDirpath:
            logging.warn('The rebase directories are identical - nothing to do')
            return

        dlg = QProgressDialog()
        dlg.setMinimum(0)
        dlg.setValue(0)

        for f, n, N in rebaseReferenceFilepaths(curDirpath, newDirpath):
            dlg.setMaximum(N)
            dlg.setValue(n)
            dlg.setLabelText('Rebasing reference: %s' % f)
            if dlg.wasCanceled():
                break

        # Make sure the progress dialog is closed
        dlg.close()

        # Swap the dirpaths
        self.currentDirpathWidget.path, self.newDirpathWidget.path = \
            newDirpath, curDirpath

#end
