import logging

logger = logging.getLogger('startup')


# NOTE: this script gets execfile'd by maya so useful data such as the __file__
# global doesn't exist...  The solution to this is for this script to simply
# import "setup_maya" which lives next to this script and DOES have access
# to such information.  So all the setup logic actually lives there.
import setup_maya
isDebug = setup_maya.isDebug
