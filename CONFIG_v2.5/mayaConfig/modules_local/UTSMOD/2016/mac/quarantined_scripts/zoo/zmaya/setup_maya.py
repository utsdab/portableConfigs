
import os
import logging

from maya import cmds, mel

import setupDagMenu

from .. import path

logger = logging.getLogger('startup')

BASE_DIRPATH = path.Path(__file__).up()
MAYA_VERSION = int(mel.eval('getApplicationVersionAsFloat()'))

def setMayaEnv(env, value):
    os.environ[env] = value
    mel.eval('putenv %s "%s";' % (env, value))

FUNCTIONS_TO_EXECUTE = []

def isDebug():
    return os.environ.get('PYTHONDEBUGLOGGING', False) != '0'

def d_executeInMain(f):
    '''
    simply registers the function to be executed in the main function
    '''
    FUNCTIONS_TO_EXECUTE.append(f)
    return f

@d_executeInMain
def setupPythonPaths():
    '''
    sets up python paths for maya specific tools
    '''
    pass

@d_executeInMain
def setupMELPaths():
    '''
    sets up MEL paths
    '''
    basePaths = os.environ['MAYA_SCRIPT_PATH'].split(os.pathsep)
    extraPaths = [BASE_DIRPATH.up() / 'mel',
                  ]

    setMayaEnv('MAYA_SCRIPT_PATH', os.pathsep.join(extraPaths + basePaths))

@d_executeInMain
def setupPlugins():
    '''
    sets up paths for plugins (both binary and python ones) and loads them
    '''
    basePaths = os.environ['MAYA_PLUG_IN_PATH'].split(os.pathsep)
    extraPaths = []

    # Append zoo plugins
    versionAgnosticPlugins = BASE_DIRPATH / 'plugins'
    extraPaths.append(versionAgnosticPlugins)

    # Set the plug-in path
    setMayaEnv('MAYA_PLUG_IN_PATH', os.pathsep.join(basePaths + extraPaths))

@d_executeInMain
def setupIcons():
    '''
    sets up paths for icons
    '''
    basePaths = os.environ['XBMLANGPATH'].split(os.pathsep)
    extraPaths = []

    # Add the mel paths
    extraPaths.append(BASE_DIRPATH / 'icons')

    # Add the mel paths
    extraPaths.append(BASE_DIRPATH / 'mel')

    # Add the plugin paths
    extraPaths.append(BASE_DIRPATH / 'plugins')

    setMayaEnv('XBMLANGPATH', os.pathsep.join(extraPaths + basePaths))

@d_executeInMain
def setupMenus():

    # NOTE: this import happens in here because the module uses skeletonBuilder which attempts
    # to load a plugin.  Plugin paths aren't setup when this module is imported so if this is
    # a top level import it will raise an error
    import tool_menu

    # evalDeferred required because the UI hasn't been built yet
    cmds.evalDeferred(tool_menu.ToolMenu)

@d_executeInMain
def setLogging():
    if isDebug():
        rootLogger = logging.getLogger()
        rootLogger.level = logging.DEBUG
        for handler in rootLogger.handlers:
            handler.level = logging.DEBUG
            logger.debug('Changed log handler %s to DEBUG level' % handler)

def main():
    for func in FUNCTIONS_TO_EXECUTE:
        try:
            func()
        except:
            logger.error("Failed the startup function %s" % func, exc_info=1)

    try:
        setupDagMenu.setup()
    except:
        logger.error("Failed to setup the dag proc menu!", exc_info=1)

main()

#end
