
import gc
import sys
import inspect
import logging

from . import path

logger = logging.getLogger(__name__)

def flushUnder(dirpath):
    '''
    Flushes all modules that live under the given directory
    '''
    for name, module in sys.modules.items():
        if module is None:
            continue

        try:
            moduleDirpath = path.Path(inspect.getfile(module)).up()
            if moduleDirpath.isUnder(dirpath):
                del sys.modules[name]
                logger.info('unloaded module: %s ' % name)

        except: continue

    # Force a garbage collection
    gc.collect()

def flushZoo():
    '''
    Flushes all zoo modules from sys.modules

    This makes it trivial to make changes to tools that have potentially
    complex reload dependencies. Eg:

    import flush;flush.flush()
    import toolWithComplexDependencies
    toolWithComplexDependencies.run()

    The above will force all zoo modules to be reloaded
    '''
    zooPackageDirpath = path.Path(inspect.getfile(path)).up()
    flushUnder(zooPackageDirpath)

#end
