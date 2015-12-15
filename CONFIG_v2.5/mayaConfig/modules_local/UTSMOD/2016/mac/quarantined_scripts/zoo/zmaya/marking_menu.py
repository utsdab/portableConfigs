
import logging

from maya import cmds
from maya import mel

logger = logging.getLogger(__name__)

class MarkingMenu(object):
    MENU_NAME = 'tempMM'
    IS_CLICKED = False
    INSTANCE = None

    def __init__(self):
        MarkingMenu.IS_CLICKED = False
        MarkingMenu.INSTANCE = self
        panel = mel.eval('findPanelPopupParent')

        if cmds.popupMenu(self.MENU_NAME, ex=True):
            cmds.deleteUI(self.MENU_NAME)

        cmds.popupMenu(self.MENU_NAME, parent=panel,
                       ctrlModifier=False, altModifier=False, shiftModifier=False,
                       markingMenu=True, button=1, allowOptionBoxes=True,
                       pmc=self.__createAndShowMenu)

    def __createAndShowMenu(self, menu, menuParent):
        MarkingMenu.IS_CLICKED = True
        cmds.setParent(menu, m=True)
        cmds.menu(menu, e=True, dai=True)
        self.show(menu, menuParent)

    def show(self, menu, menuParent):
        """
        implement in subclass
        """
        raise Exception('Must implement the show method!')

    def press(self):
        """
        implement in subclass
        """
        logger.debug('%s has no press method implemented' % type(self).__name__)

    @classmethod
    def kill(cls):
        if not MarkingMenu.IS_CLICKED and isinstance(cls.INSTANCE, cls):
            cls.INSTANCE.press()

        MarkingMenu.IS_CLICKED = False
        cls.INSTANCE = None

        if cmds.popupMenu(cls.MENU_NAME, ex=True):
            cmds.deleteUI(cls.MENU_NAME)

#end
