
import os
import re
import inspect
import zipfile
import logging
import StringIO

from maya import cmds

logger = logging.getLogger(__name__)

IMPORT_COMMENT = '# Importing the zoo tools'

def installAutoLoad():
    userSetupFilepath = os.path.join(
        cmds.internalVar(userScriptDir=True), 'userSetup.py')

    # Set the default mode to write
    mode = 'w'

    # Does the file already exist?
    if os.path.exists(userSetupFilepath):

        # If so, set the mode to append
        mode = 'a'

        # Is there a line in the user setup already to load zoo?
        with open(userSetupFilepath) as f:
            for line in f.readlines():
                line = line.strip()

                # There are probably corner cases where these tests fail, but I'm
                # assuming in those cases that the user knows that they're doing...
                if line == 'import zoo.zmaya' or 'zoo.zmaya' in line:
                    return

    # Ok so it seems like we need to add zoo toolbox loading to the user setup
    with open(userSetupFilepath, mode) as f:
        f.write('\n\n')
        f.write(IMPORT_COMMENT)
        f.write('\nimport zoo.zmaya\n')

def uninstallAutoLoad():
    userSetupFilepath = os.path.join(
        cmds.internalVar(userScriptDir=True), 'userSetup.py')

    # Bail if the user setup script doesn't exist...
    if not os.path.exists(userSetupFilepath):
        return

    # Read the contents of the user setup script and see if it has the
    containsZooImport = False
    with open(userSetupFilepath) as f:
        for line in f.readlines():
            if 'zoo.zmaya' in line:
                containsZooImport = True
                break

    # If the script doesn't contain the zoo import, bail
    if not containsZooImport:
        return

    # Otherwise, open the file again, read its contents, strip the zoo import lines
    # and re-write the contents
    lines = []
    with open(userSetupFilepath) as f:
        for line in f.readlines():
            if IMPORT_COMMENT in line:
                continue

            if 'import zoo.zmaya' in line:
                continue

            lines.append(line)

    # If the file is empty, delete it, otherwise write the remaining files
    hasData = any(l.strip() for l in lines)
    if hasData:
        with open(userSetupFilepath, 'w') as f:
            f.write(''.join(lines))
    else:
        os.remove(userSetupFilepath)

def installFromContents(distributionContents):
    buts = y, n = 'OK', 'Cancel'
    ret = cmds.confirmDialog(
        t='Are you sure?',
        m='Do you want to install the zoo tools?',
        b=buts,
        db=y)

    if ret != y:
        return

    # Figure out the install location - this may be modified if an existing
    # installation is found
    scriptsDirpath = cmds.internalVar(userScriptDir=True)
    installDirpath = os.path.join(scriptsDirpath, 'zoo')

    # Check to see if the zoo tools are already installed
    zooToolsExists = False
    try:
        import zoo.zmaya
        zooToolsExists = True
    except ImportError: pass

    # If they are, ask if the user wants to uninstall the existing package first
    if zooToolsExists:
        ret = cmds.confirmDialog(
            t='zooTools Already Installed!',
            m='Looks like the zoo tools are already installed.\nDo you want to replace the existing installation?',
            b=buts,
            db=y)

        if ret != y:
            logger.info('zooTools installation aborted')
            return

        # If the user responds yes, then change the install dirpath and uninstall
        # the existing package
        installDirpath = getZooPackageDirpath()
        uninstall(False)

    # Log the install location
    logger.info('Installing zooTools into %s' % installDirpath)

    # Unzip the data in the distribution contents
    f = StringIO.StringIO(distributionContents)
    zipF = zipfile.ZipFile(f)
    zipF.extractall(str(installDirpath))

    # Install the auto load command to the user's userSetup script
    logger.info('Adding zooTools maya startup')
    installAutoLoad()

    # Finally, load the zoo tools
    try:
        import zoo.zmaya
        logging.debug(zoo.zmaya)
        logging.info('Successfully installed zoo tools')
    except ImportError, x:
        logger.error('Failed to import zoo tools after installation!', exc_info=x)

def installFromZipFilepath(distributionFilepath):
    with open(distributionFilepath) as f:
        installFromContents(f.read())

def getZooPackageDirpath():

    # Figure out where the path module lives
    from zoo import path
    pathModuleFilepath = path.Path(inspect.getfile(path))

    # The zoo package is the dir the path module lives in
    return pathModuleFilepath.up()

def uninstall(ask=True):
    if ask:
        buts = Y, CANCEL = 'Yes', 'Cancel'
        ret = cmds.confirmDialog(
            t='Are You Sure?',
            m='Are you sure you want to uninstall zooTools?',
            b=buts,
            db=CANCEL)

        if ret != Y:
            return

    # Make sure these are absolute imports...
    from zoo import path, flush
    from zoo.zmaya import tool_menu

    # Does the zoo package live under the user scripts?
    zooModuleDirpath = getZooPackageDirpath()
    userScriptsDirpath = path.Path(cmds.internalVar(userScriptDir=True))

    # If it doesn't, then we should ask the user if we have the location correct
    if not zooModuleDirpath.isUnder(userScriptsDirpath):
        buts = Y, CANCEL = 'Yes', 'Cancel'
        ret = cmds.confirmDialog(
            t='zooTools Not In Default Location',
            m='It looks like the zooTools on your machine is installed here:\n%s\n\n'
              'This isn\'t the default installation location which means it wasn\'t\n'
              'installed in the normal fashion.\n\n'
              'Should I try to uninstall anyway?' % zooModuleDirpath,
            b=buts,
            db=CANCEL)

        if ret != Y:
            return

    logger.info('Deleting zoo python package')
    zooModuleDirpath.delete()

    # Try to uninstall the auto load
    try:
        logger.info('Removing zooTools startup commands from userSetup script')
        uninstallAutoLoad()
    except Exception, x:
        logger.error('Failed to uninstall auto loading from user setup', exc_info=x)

    # Try to remove the Zoo Tools main menu
    try:
        if cmds.menu(tool_menu.ToolMenu.MENU_NAME, q=True, ex=True):
            logger.info('Removing Zoo Tools main menu')
            cmds.deleteUI(tool_menu.ToolMenu.MENU_NAME)
    except: pass

    # Flush all imported zoo tools
    logger.info('Flushing zoo tools from memory')
    flush.flushUnder(zooModuleDirpath)

def writeDistributionZipfile(f):
    import zoo
    from zoo import path
    zooModuleFilepath = inspect.getfile(zoo)
    zooModuleDirpath = os.path.dirname(zooModuleFilepath)

    # Now zip all files under this directory into a zip file
    zipF = zipfile.ZipFile(f, 'w')

    skipDirs = ('.git',
                )

    ignorePatterns = (re.compile('.*\.txt'),
                      re.compile('\.gitignore'),
                      re.compile('.*\.psd'),
                      re.compile('.*\.xcf'),
                      )

    for dirpath, dirname, filenames in os.walk(zooModuleDirpath):
        dirpath = path.Path(dirpath)

        # Should we skip this dir?
        skipDir = False
        for d in skipDirs:
            if d in dirpath:
                skipDir = True

        if skipDir:
            continue

        # Should we skip this file?
        for filename in filenames:
            skipFile = False
            for pat in ignorePatterns:
                if pat.match(filename):
                    skipFile = True
                    break

            if skipFile:
                continue

            # Write the file into the zip
            filepath = dirpath / filename
            zipF.write(str(filepath), str(filepath - zooModuleDirpath))

    return zipF

def writeDistributionZipfileToFilepath(filepath):
    f = open(filepath, 'w')
    return createDistributionZipfile(f)

def getInstallVersionStr():
    versionFilepath = getZooPackageDirpath() / '.version'
    if versionFilepath.exists():
        with open(str(versionFilepath)) as f:
            return f.read()

    return 'dev.' + getDevVersionStr()

def getDevVersionStr():
    import subprocess
    from zoo import path

    devDirpath = path.Path(inspect.getfile(path)).up()

    # Try to determine a version string using the latest commit hash
    verStr = ''
    try:

        # First we get the commit count
        p1 = subprocess.Popen(
            ['git', 'rev-list', 'HEAD', '--count'],
            cwd=str(devDirpath), shell=True, stdout=subprocess.PIPE)

        p1.wait()
        if p1.returncode == 0:
            verStr += p1.stdout.read().strip()

            # Now we append the commit SHA
            # So a version string looks like this: _v174.7b6a827
            p2 = subprocess.Popen(
                ['git', 'log', '-n', '1', '--pretty=format:"%h"'],
                cwd=str(devDirpath), shell=True, stdout=subprocess.PIPE)

            p2.wait()
            if p2.returncode == 0:
                verStr += '.' + p2.stdout.read().strip()[1:-1]
    except: pass

    return verStr

def writeInstallVersionStr(verStr):
    versionFilepath = str(getZooPackageDirpath() / '.version')
    with open(versionFilepath, 'w') as f:
        f.write(verStr)

def createDistributionScene():
    version = getDevVersionStr()
    verStr = '_v' + version if version else ''

    cmds.file(new=True, f=True)
    cmds.file(rename=os.path.expanduser('~/zooInstaller%s.ma' % verStr))
    cmds.file(save=True, type='mayaAscii')
    dataStorageModuleNode = cmds.createNode('script', n='installZooScripts')

    # Set the script node to execute on load
    cmds.setAttr('%s.scriptType' % dataStorageModuleNode, 1)

    # Set the source type to python
    cmds.setAttr('%s.sourceType' % dataStorageModuleNode, 1)

    # Write the contents of the distribution into scene storage
    from . import data_storage
    storage = data_storage.DataStorage.Create('zooToolsZipContents')
    f = StringIO.StringIO()
    writeDistributionZipfile(f)
    f.seek(0)
    storage.write(f.read())
    f.close()

    # Now we need to create a script node that will unzip the distribution to
    # an appropriate location
    from . import install_zoo

    # Read the contents of the script and write to the before attribute
    dataStorageSrc = inspect.getsource(data_storage) + '\n\n'
    dataStorageSrc += inspect.getsource(install_zoo)
    dataStorageSrc += '\n\nstorage = DataStorage("%s") # Instantiate the storage object\n' % storage.node
    dataStorageSrc += 'installFromContents(storage.read()) # Install the tools\n' \
                      'cmds.file(new=True, f=True) # Load a new scene\n' \
                      'cmds.confirmDialog(t="Success", m="The zooTools have been installed. Notice the Zoo Tools menu?")\n'

    dataStorageSrc += 'writeInstallVersionStr("%s") # Write the version string to disk\n' % version
    cmds.setAttr('%s.before' % dataStorageModuleNode, dataStorageSrc, type='string')

    cmds.file(save=True, f=True)

#end
