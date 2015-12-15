
import re
import logging

from .. import path

from maya import cmds, mel

import triggered

logger = logging.getLogger(__name__)

def setup():
    '''
    Installs modifications to the dagProcMenu script for the current session
    '''
    try:
        dagMenuScriptpath = path.findFirstInEnv('dagMenuProc.mel', 'MAYA_SCRIPT_PATH')
    except:
        logger.warning("Cannot find the dagMenuProc.mel script - aborting auto-override!")
        return

    tmpScriptpath = path.Path(cmds.internalVar(usd=True)) / 'zooDagMenuProc_override.mel'

    def writeZooLines(fStream, parentVarStr, objectVarStr):
        fStream.write('\n/// ZOO MODS ########################\n')
        fStream.write('\tsetParent -m $parent;\n')
        fStream.write('\tmenuItem -d 1;\n')
        fStream.write('\tpython("from zoo.zmaya import triggered");\n')
        fStream.write("""\tint $killState = python("triggered.buildMenuItems('"+ %s +"', '"+ %s +"')");\n""" % (parentVarStr, objectVarStr))
        fStream.write('\tif($killState) return;\n')
        fStream.write('/// END ZOO MODS ####################\n\n')

    globalProcDefRex = re.compile("^global +proc +dagMenuProc *\(*string *(\$[a-zA-Z0-9_]+), *string *(\$[a-zA-Z0-9_]+) *\)")
    with open(dagMenuScriptpath) as f:
        dagMenuScriptLineIter = iter(f)
        with open(tmpScriptpath, 'w') as f2:
            hasDagMenuProcBeenSetup = False
            for line in dagMenuScriptLineIter:
                f2.write(line)

                globalProcDefSearch = globalProcDefRex.search(line)
                if globalProcDefSearch:
                    parentVarStr, objectVarStr = globalProcDefSearch.groups()

                    if '{' in line:
                        writeZooLines(f2, parentVarStr, objectVarStr)
                        hasDagMenuProcBeenSetup = True

                    if not hasDagMenuProcBeenSetup:
                        for line in dagMenuScriptLineIter:
                            f2.write(line)
                            if '{' in line:
                                writeZooLines(f2, parentVarStr, objectVarStr)
                                hasDagMenuProcBeenSetup = True
                                break

        if not hasDagMenuProcBeenSetup:
            logger.error("Couldn't auto setup dagMenuProc!", exc_info=1)
            return

        # NOTE: this needs to be done twice to actually take...  go figure
        mel.eval('source "%s";' % tmpScriptpath)
        mel.eval('source "%s";' % tmpScriptpath)

    # Now delete the tmp script - we don't want the "mess"
    tmpScriptpath.delete()

    # The dag menu customizations are centered around triggered, so load it up!
    triggered.Load()

#end
