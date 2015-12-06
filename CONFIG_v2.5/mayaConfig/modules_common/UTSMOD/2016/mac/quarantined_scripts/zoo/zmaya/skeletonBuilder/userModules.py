
import sys
import inspect
import logging

from ... import path

logger = logging.getLogger(__name__)

def _iterScriptFileNames():
    zooPackageDirpath = path.Path(inspect.getfile(path)).up()
    for p in sys.path:
        p = path.Path(p)

        # Skip non-directories or non-existent dirs
        if not p.isDir() or not p.exists():
            continue

        # Skip anything under the zoo package
        if p.isUnder(zooPackageDirpath):
            continue

        # Otherwise, look for scripts with the skeletonPart or rigPart prefixes
        for f in p.files():
            if f.hasExtension('py') or f.hasExtension('pyc'):
                yield f.name()

def importUserModules():
    logger.info('Searching for SkeletonBuilder user modules')

    skeletonPartModuleNames = []
    rigPartModuleNames = []
    for moduleName in _iterScriptFileNames():
        if moduleName.startswith('skeletonPart_'):
            skeletonPartModuleNames.append(moduleName)
        elif moduleName.startswith('rigPart_'):
            rigPartModuleNames.append(moduleName)

    # NOTE: skeleton parts must be imported first, as the rig parts reference the
    # skeleton parts to associate themselves properly
    for moduleName in skeletonPartModuleNames + rigPartModuleNames:
        module = __import__(moduleName)
        logger.info('Imported SkeletonBuilder user module: %s' % module)

    userModulesFound = skeletonPartModuleNames or rigPartModuleNames
    if not userModulesFound:
        logger.info('No SkeletonBuilder user modules found')

#end
