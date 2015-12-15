
import re
import inspect
import logging

from maya import OpenMaya
from maya import cmds
from maya import mel

from .. import path

def pyArgToMelArg(arg):
    # given a python string object, this method will attempt to convert it to a mel string
    if isinstance(arg, basestring):
        return u'"%s"' % cmds.encodeString( arg )

    # if the object is iterable then turn it into a mel array string
    elif hasattr(arg, '__iter__'):
        return '{%s}' % ','.join(pyArgToMelArg(a) for a in arg)

    # either lower case bools or ints for mel please...
    elif isinstance(arg, bool):
        return unicode(arg).lower()

    # otherwise try converting the sucka to a string directly
    return unicode(arg)

logger = logging.getLogger('MEL')

class _MelType(type):
    ECHO = False

    def __getattr__(self, attr):

        # construct the mel cmd execution method
        def melExecutor(*args):
            cmdStr = '%s(%s);' % (attr, ','.join(pyArgToMelArg(a) for a in args))

            if self.ECHO:
                logger.info(cmdStr)

            try:
                retVal = mel.eval(cmdStr)
            except RuntimeError, x:
                logger.error('executing %s: %s' % (cmdStr, x), exc_info=1)
                raise

            return retVal

        melExecutor.__name__ = attr

        return melExecutor

def indexOfMatchingClosingBrace(theStr, startIdx=0):
    curIdx = startIdx
    braceCount = 1
    while braceCount:
        char = theStr[curIdx]
        curIdx += 1
        if char == '{':
            braceCount += 1
        elif char == '}':
            braceCount -= 1

    return curIdx

class MEL(object):
    '''
    creates an easy to use interface to mel code as opposed to having string formatting
    operations all over the place in scripts that call mel functionality
    '''
    __metaclass__ = _MelType

    class IsRunTimeCommandError(ValueError): pass

    _SpacePattern = '[ \t\n]+'
    _RexPatternTemplate = 'global' + _SpacePattern + 'proc' + _SpacePattern + '.*%s[ \t\n]*\('

    @classmethod
    def Eval(cls, cmdStr):
        if cls.echo:
            logger.debug(cmdStr)

        try:
            return mel.eval(cmdStr)
        except RuntimeError, x:
            logger.error('executing %s: %s' % (cmdStr, x), exc_info=1)
            raise

    @classmethod
    def Source(cls, script):
        return cls.Eval('source "%s";' % script)

    @classmethod
    def WhereIs(cls, procName):
        '''
        returns the script containing the given procedure
        '''
        whatIsRet = mel.eval('whatIs %s' % procName)

        # Make sure we got a valid answer
        if 'no definition seen yet' in whatIsRet:
            raise ValueError("Maya doesn't know where the procedure %s comes from: %s" % (procName, whatIsRet))

        # Maya reports procs that were created via an eval as being "entered interactively"
        if 'entered interactively' in whatIsRet:
            raise ValueError("The procedure %s was created dynamically" % procName)

        # Maya reports procs that were created via an eval as being "entered interactively"
        if 'Run Time Command' in whatIsRet:
            raise cls.IsRunTimeCommandError("The procedure %s is a runtime command" % procName)

        # Annoyingly this returns a string that looks something like this:
        # Mel Procedure found in: c:/whatever/awesomescript.mel
        # But not always that - sometimes it says script or command...  So lets try to remove it
        consistentStrFragment = 'found in: '
        consistentStrFragmentIdx = whatIsRet.find(consistentStrFragment)
        prefixEndIdx = consistentStrFragmentIdx + len(consistentStrFragment)

        return path.Path(whatIsRet[prefixEndIdx:])

    @classmethod
    def GetSourceCode(cls, procName):
        '''
        returns the source code of the given MEL procedure
        '''
        try:
            scriptFilepath = cls.WhereIs(procName)
        except cls.IsRunTimeCommandError:
            return cmds.runTimeCommand(procName, q=True, command=True)

        # Parse the script to find the source code for the given procedure
        with open(scriptFilepath) as f:
            scriptContentsStr = f.read()

        # Find the start
        rex = re.compile(cls._RexPatternTemplate % procName)
        for match in rex.finditer(scriptContentsStr):
            procStartIdx = match.start()

            # This gives us the start of the proc.  Find the opening brace
            curContentsIdx = match.end()
            while True:
                char = scriptContentsStr[curContentsIdx]
                curContentsIdx += 1
                if char == '{':
                    break

            procEndIdx = indexOfMatchingClosingBrace(scriptContentsStr, curContentsIdx)

            return scriptContentsStr[procStartIdx:procEndIdx]

def traceableStrFactory(printFunc):
    '''
    returns 2 functions - the first will generate a traceable message string, while
    the second will print the generated message string.  The second is really a
    convenience function, but is called enough to be worth it
    '''
    def generateTraceableStr(*toPrint, **kw):
        frameInfos = inspect.getouterframes(inspect.currentframe())
        _nFrame = kw.get('_nFrame', 1)

        # frameInfos[0] contains the current frame and associated calling data,
        # while frameInfos[1] is the frame that called this one - which is the
        # frame we want to print data about
        callingFrame, callingScript, callingLine, callingName, _a, _b = frameInfos[_nFrame]
        callingModule = inspect.getmodule(frameInfos[_nFrame][0])
        callingModuleName = callingModule.__name__

        # figure out if this is an instance/cls method or not
        # NOTE: this relies on ppl using self as the name for "self", which is
        # convention, not a requirement...
        if 'self' in callingFrame.f_locals:
            callingModuleName += '.' + callingFrame.f_locals['self'].__class__.__name__

        return '%s.%s(...) #%s:  %s' % (
            callingModuleName, callingName, callingLine, ' '.join(map(str, toPrint)))

    def printTraceableStr(*args):
        msg = generateTraceableStr(_nFrame=2, *args)
        printFunc(msg)

    return printTraceableStr

tracePrint = traceableStrFactory(OpenMaya.MGlobal.displayInfo)
traceWarning = traceableStrFactory(OpenMaya.MGlobal.displayWarning)
traceError = traceableStrFactory(OpenMaya.MGlobal.displayError)

#end
