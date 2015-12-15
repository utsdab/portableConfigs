
import logging

from maya import cmds
from maya import mel

from .. import cls_types

logger = logging.getLogger(__name__)

class PythonToolLoader(str):
    def __call__(self, *a):
        exec self

class MELToolLoader(object):
    def __init__(self, cmdStr):
        self._cmdStr = cmdStr

    def __call__(self, *a):
        mel.eval(self._cmdStr)

class BaseMenu(object):
    __metaclass__ = cls_types.SingletonType

    # subclasses should set to True and imlpement a "rebuild" method to make menu creation dynamic
    DYNAMIC_BUILD = False

    def __init__(self):
        self.subMenus = {}

        kw = {}
        if self.DYNAMIC_BUILD:
            kw['pmc'] = self._rebuild

        # this awkward idiom queries the MEL global that stores the maya UI top level window name
        # needed for parenting menus to
        mainWindow = mel.eval('string $x=$gMainWindow;')
        if not cmds.menu(self.MENU_NAME, q=True, ex=True):
            cmds.menu(self.MENU_NAME, p=mainWindow, l=self.MENU_LABEL, tearOff=True, **kw)

        if not self.DYNAMIC_BUILD:
            self.build()

    def clear(self):
        self.subMenus = {'': self.MENU_NAME}
        cmds.menu(self.MENU_NAME, e=True, dai=True)
        cmds.setParent(self.MENU_NAME, m=True)

    def build(self):
        pass

    def _rebuild(self, *a):

        self.clear()
        self.rebuild()

    def rebuild(self):
        pass

    def delete(self):
        if self.MENU_NAME:
            cmds.deleteUI(self.MENU_NAME)

class ToolMenu(BaseMenu):
    MENU_NAME = 'zoo_main_tools_menu'
    MENU_LABEL = 'Zoo Tools'

    DYNAMIC_BUILD = True

    def rebuild(self):
        from zoo.zmaya import populateZooMenu
        reload(populateZooMenu)
        populateZooMenu.populateMenu(self.MENU_NAME)

#end
