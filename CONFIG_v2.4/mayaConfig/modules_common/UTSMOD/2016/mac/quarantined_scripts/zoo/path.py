import os
import re
import sys
import stat
import shutil

ENV_REGEX = re.compile("\%[^%]+\%")

def resolveAndSplit(path, envDict=None, raiseOnMissing=False):
    """
    recursively expands all environment variables and '..' tokens in a pathname
    """
    if envDict is None:
        envDict = os.environ

    path = os.path.expanduser(str(path))

    # performing this check is faster than doing the regex
    if '%' in path:
        findall = re.findall

        # first resolve any env variables
        matches = findall(ENV_REGEX, path)
        missingVars = set()
        while matches:
            for match in matches:
                try:
                    path = path.replace(match, envDict[match[1:-1]])
                except KeyError:
                    if raiseOnMissing:
                        raise

                    missingVars.add(match)

            matches = set(findall(ENV_REGEX, path))

            # remove any variables that have been found to be missing...
            for missing in missingVars:
                matches.remove(missing)

    # now resolve any subpath navigation
    # NOTE: believe it or not, checking this first is faster
    if '\\' in path:
        path = path.replace('\\', '/')

    # is the path a UNC path?
    isUNC = path.startswith('//')
    if isUNC:
        path = path[2:]

    # remove duplicate separators
    while '//' in path:
        path = path.replace('//', '/')

    pathToks = path.split('/')
    pathsToUse = []
    pathsToUseAppend = pathsToUse.append
    for n, tok in enumerate(pathToks):
        if tok == "..":
            try:
                pathsToUse.pop()
            except IndexError:
                if raiseOnMissing:
                    raise

                pathsToUse = pathToks[n:]
                break
        else:
            pathsToUseAppend(tok)

    # finally convert it back into a path and pop out the last token if its empty
    path = '/'.join(pathsToUse)
    if not pathsToUse[-1]:
        pathsToUse.pop()

    # if its a UNC path, stick the UNC prefix
    if isUNC:
        return '//' + path, pathsToUse, True

    return path, pathsToUse, isUNC

class Path(str):
    CaseMatters = os.name != 'nt'

    @classmethod
    def DoesCaseMatter(cls):
        return cls.CaseMatters

    @classmethod
    def Join(cls, *toks, **kw):
        return cls('/'.join(toks), **kw)

    def __new__(cls, path='', caseMatters=None, envDict=None):
        """
        if case doesn't matter for the path instance you're creating, setting caseMatters
        to False will do things like caseless equality testing, caseless hash generation
        """

        # early out if we've been given a Path instance - paths are immutable so there
        # is no reason not to just return what was passed in
        if type(path) is cls:
            return path

        #set to an empty string if we've been init'd with None
        if path is None:
            path = ''

        resolvedPath, pathTokens, isUnc = resolveAndSplit(path, envDict)
        new = str.__new__(cls, resolvedPath)
        new.isUNC = isUnc
        new.hasTrailing = resolvedPath.endswith('/')
        new._splits = tuple(pathTokens)
        new._passed = path

        #case sensitivity, if not specified, defaults to system behaviour
        if caseMatters is not None:
            new.CaseMatters = caseMatters

        return new

    def __nonzero__(self):
        """
        a Path instance is "non-zero" if its not '' or '/'  (although I
        guess '/' is actually a valid path on *nix)
        """
        selfStripped = self.strip()
        if selfStripped == '':
            return False

        if selfStripped == '/':
            return False

        return True

    def __add__(self, other):
        return self.__class__('%s%s%s' % (self, '/', other), self.CaseMatters)

    def __radd__(self, other):
        return self.__class__(other, self.CaseMatters) + self

    # the / or + operator both concatenate path tokens
    __div__ = __add__
    __rdiv__ = __radd__

    def __getitem__(self, item):
        return self._splits[item]

    def __getslice__(self, a, b):
        isUNC = self.isUNC
        if a:
            isUNC = False

        return self._toksToPath(self._splits[a:b], isUNC, self.hasTrailing)

    def __len__(self):
        if not self:
            return 0

        return len(self._splits)

    def __contains__(self, item):
        if not self.CaseMatters:
            return item.lower() in [s.lower() for s in self._splits]

        return item in list(self._splits)

    def __hash__(self):
        """
        the hash for two paths that are identical should match - the most reliable way to do this
        is to use a tuple from self.split to generate the hash from
        """
        if not self.CaseMatters:
            return hash(tuple([s.lower() for s in self._splits]))

        return hash(tuple(self._splits))

    def _toksToPath(self, toks, isUNC=False, hasTrailing=False):
        """
        given a bunch of path tokens, deals with prepending and appending path
        separators for unc paths and paths with trailing separators
        """
        toks = list(toks)
        if isUNC:
            toks = ['', ''] + toks

        if hasTrailing:
            toks.append('')

        return self.__class__('/'.join(toks), self.CaseMatters)

    def resolve(self, envDict=None):
        """
        will re-resolve the path given a new envDict
        """
        if envDict is None:
            return self
        else:
            return Path(self._passed, self.CaseMatters, envDict)

    def unresolved(self):
        """
        returns the un-resolved path - this is the exact string that the path was instantiated with
        """
        return self._passed

    def isEqual(self, other):
        """
        compares two paths after all variables have been resolved, and case sensitivity has been
        taken into account - the idea being that two paths are only equal if they refer to the
        same filesystem object.  NOTE: this doesn't take into account any sort of linking on *nix
        systems...
        """
        if not isinstance(other, Path):
            other = Path(other, self.CaseMatters)

        selfStr = str(self.asFile())
        otherStr = str(other.asFile())
        if not self.CaseMatters:
            selfStr = selfStr.lower()
            otherStr = otherStr.lower()

        return selfStr == otherStr

    __eq__ = isEqual

    def __ne__(self, other):
        return not self.isEqual(other)

    def doesCaseMatter(self):
        return self.CaseMatters

    def getStat(self):
        try:
            return os.stat(self)
        except:
            #return a null stat_result object
            return os.stat_result([0 for n in range(os.stat_result.n_sequence_fields)])

    def isAbs(self):
        try:
            return os.path.isabs(str(self))
        except:
            return False

    def abs(self):
        """
        returns the absolute path as is reported by os.path.abspath
        """
        return self.__class__(os.path.abspath(str(self)))

    def split(self, caseMatters=None):
        """
        returns the splits tuple - ie the path tokens
        """
        if caseMatters is not None and not caseMatters:
            return [tok.lower() for tok in self._splits]

        return list(self._splits)

    def asDir(self):
        """
        makes sure there is a trailing / on the end of a path
        """
        if self.hasTrailing:
            return self

        return self.__class__(self._passed + '/', self.CaseMatters)

    asdir = asDir

    def asFile(self):
        """
        makes sure there is no trailing path separators
        """
        if not self.hasTrailing:
            return self

        return self.__class__(str(self)[:-1], self.CaseMatters)

    asfile = asFile

    def isDir(self):
        """
        bool indicating whether the path object points to an existing directory or not.  NOTE: a
        path object can still represent a file that refers to a file not yet in existence and this
        method will return False
        """
        return os.path.isdir(self)

    isdir = isDir

    def isFile(self):
        """
        see isdir notes
        """
        return os.path.isfile(self)

    isfile = isFile

    def getReadable(self):
        """
        returns whether the current instance's file is readable or not.  if the file
        doesn't exist False is returned
        """
        try:
            s = os.stat(self)
            return s.st_mode & stat.S_IREAD
        except:
            #i think this only happens if the file doesn't exist
            return False

    def setWritable(self, state=True):
        """
        sets the writeable flag (ie: !readonly)
        """
        try:
            setTo = stat.S_IREAD
            if state:
                setTo = stat.S_IWRITE

            os.chmod(self, setTo)
        except:
            pass

    def getWritable(self):
        """
        returns whether the current instance's file is writeable or not.  if the file
        doesn't exist True is returned
        """
        try:
            s = os.stat(self)
            return s.st_mode & stat.S_IWRITE
        except:
            #i think this only happens if the file doesn't exist - so return true
            return True

    def getExtension(self, getAllExtensions=False):
        """
        Returns the file extension

        If getAllExtensions is True then a string containing all extensions is returned
        otherwise the right most extension is returned.

        For example:
        Path('filename.info.txt').getExtension(True) == 'info.txt'
        Path('filename.info.txt').getExtension(False) == 'txt'
        """
        try:
            endTok = self[-1]
        except IndexError:
            return ''

        if getAllExtensions:
            idx = endTok.find('.')
        else:
            idx = endTok.rfind('.')

        if idx == -1:
            return ''

        return endTok[idx + 1:]  # add one to skip the period

    def getExtensions(self):
        """
        Returns all extensions

        For example:
        Path('filename.info.txt').getExtensions() == ['info', 'txt']
        """
        return self.getExtension(True).split('.')

    def setExtension(self, xtn=None, setAllExtensions=True):
        """
        Sets the extension the path object.

        The xtn arg doesn't need to contain a leading period but it can.

        If setAllExtensions is True and the filename has multiple extensions then
        all extension tokens are replaced.

        For example:
        Path('filename.info.txt').setExtension('log', True) == 'filename.log'
        Path('filename.info.txt').setExtension('log', False) == 'filename.info.log'
        """
        if xtn is None:
            xtn = ''

        # make sure there is are no start periods
        while xtn.startswith('.'):
            xtn = xtn[1:]

        toks = self.split()
        try:
            endTok = toks.pop()
        except IndexError:
            endTok = ''

        if setAllExtensions:
            idx = endTok.find('.')
        else:
            idx = endTok.rfind('.')

        name = endTok
        if idx >= 0:
            name = endTok[:idx]

        if xtn:
            newEndTok = '%s.%s' % (name, xtn)
        else:
            newEndTok = name

        toks.append(newEndTok)

        return self._toksToPath(toks, self.isUNC, self.hasTrailing)

    def hasExtension(self, extension):
        """
        returns whether the extension is of a certain value or not
        """
        ext = self.getExtension()
        if not self.CaseMatters:
            ext = ext.lower()
            extension = extension.lower()

        return ext == extension

    def name(self, stripExtension=True, stripAllExtensions=False):
        """
        returns the filename by itself - by default it also strips the extension, as the actual filename can
        be easily obtained using self[-1], while extension stripping is either a multi line operation or a
        lengthy expression
        """
        try:
            name = self[-1]
        except IndexError:
            return ''

        if stripExtension:
            if stripAllExtensions:
                pIdx = name.find('.')
            else:
                pIdx = name.rfind('.')

            if pIdx != -1:
                return name[:pIdx]

        return name

    def up(self, levels=1):
        """
        returns a new path object with <levels> path tokens removed from the tail.
        ie: Path("a/b/c/d").up(2) returns Path("a/b")
        """
        if not levels:
            return self

        toks = list(self._splits)
        levels = max(min(levels, len(toks) - 1), 1)
        toksToJoin = toks[:-levels]
        if self.hasTrailing:
            toksToJoin.append('')

        return self._toksToPath(toksToJoin, self.isUNC, self.hasTrailing)

    def walkUp(self):
        """
        walks up the directory tokens.  Ie Path('a/b/c/d') will yield the following:
        a/b/c/d
        a/b/c
        a/b
        a
        """
        for n in range(len(self)):
            yield self.up(n)

    def replace(self, search, replace):
        """
        a simple search replace method - works on path tokens
        """
        idx = self.find(search)
        toks = self.split()
        toks[idx] = replace

        return self._toksToPath(toks, self.isUNC, self.hasTrailing)

    def find(self, search):
        """
        returns the index of the given path token
        """
        toks = self.split(self.CaseMatters)
        if not self.CaseMatters:
            search = search.lower()

        return toks.index(search)

    def rfind(self, search):
        toks = self.split(self.CaseMatters)
        if not self.CaseMatters:
            search = search.lower()

        toks.reverse()
        idx = toks.index(search)

        # "reverse" the index
        idx = len(toks) - idx - 1

        return idx

    index = find

    def exists(self):
        """
        returns whether the file exists on disk or not
        """
        return os.path.exists(self)

    def matchCase(self):
        """
        If running under an env where file case doesn't matter, this method will return a Path instance
        whose case matches the file on disk.  It assumes the file exists
        """
        if self.doesCaseMatter():
            return self

        for f in self.up().files():
            if f == self:
                return f

    def getSize(self):
        """
        returns the size of the file in bytes
        """
        return os.path.getsize(self)

    def create(self):
        """
        if the directory doesn't exist - create it
        """
        if not self.exists():
            os.makedirs(str(self))

    def delete(self):
        """
        WindowsError is raised if the file cannot be deleted
        """
        if self.isfile():
            selfStr = str(self)
            try:
                os.remove(selfStr)
            except WindowsError:
                os.chmod(selfStr, stat.S_IWRITE)
                os.remove(selfStr)
        elif self.isdir():
            selfStr = str(self.asDir())
            for f in self.files(recursive=True):
                f.delete()

            shutil.rmtree(selfStr, True)

    def rename(self, newName, nameIsLeaf=False):
        """
        it is assumed newPath is a fullpath to the new dir OR file.  if nameIsLeaf is True then
        newName is taken to be a filename, not a filepath.  the fullpath to the renamed file is
        returned
        """
        newPath = Path(newName)
        if nameIsLeaf:
            newPath = self.up() / newName

        if self.isfile():
            if newPath != self:
                if newPath.exists():
                    newPath.delete()

            #now perform the rename
            os.rename(self, newPath)
        elif self.isdir():
            raise NotImplementedError('dir renaming not implemented yet...')

        return newPath

    move = rename

    def copy(self, target, nameIsLeaf=False):
        """
        same as rename - except for copying.  returns the new target name
        """
        if self.isfile():
            target = Path(target)
            if nameIsLeaf:
                target = self.up() / target

            if self == target:
                return target

            targetDirpath = target.up()
            if not targetDirpath.exists():
                targetDirpath.create()

            shutil.copy2(str(self), str(target))

            return target
        elif self.isdir():
            shutil.copytree(str(self), str(target))

    def relativeTo(self, other):
        """
        returns self as a path relative to another
        """

        if not self:
            return None

        path = self
        other = Path(other)

        pathToks = path.split()
        otherToks = other.split()

        caseMatters = self.CaseMatters
        if not caseMatters:
            pathToks = [t.lower() for t in pathToks]
            otherToks = [t.lower() for t in otherToks]

        #if the first path token is different, early out - one is not a subset of the other in any fashion
        if otherToks[0] != pathToks[0]:
            return None

        lenPath, lenOther = len(path), len(other)
        if lenPath < lenOther:
            return None

        newPathToks = []
        pathsToDiscard = lenOther
        for pathN, otherN in zip(pathToks[1:], otherToks[1:]):
            if pathN == otherN:
                continue
            else:
                newPathToks.append('..')
                pathsToDiscard -= 1

        additionalToks = path[pathsToDiscard:].split()
        newPathToks.extend(additionalToks)

        return Path('/'.join(newPathToks), self.CaseMatters)

    __sub__ = relativeTo

    def __rsub__(self, other):
        return self.__class__(other, self.CaseMatters).relativeTo(self)

    def transformTo(self, other):
        """
        returns the path token required to transform this path to the other path

        Ie: self / self.transformTo(other) == other

        Example: Path('a/b/c/d').transformTo('a/b/c/x') == '../x'
        """
        other = Path(other)

        selfToks = self.split()
        otherToks = Path(other).split()
        if not self.CaseMatters:
            selfToks = (t.lower() for t in selfToks)
            otherToks = (t.lower() for t in otherToks)

        newPathToks = []
        firstDifferingTokenIdx = len(other)
        for idx, (pathN, otherN) in enumerate(zip(selfToks, otherToks)):
            if pathN != otherN:
                firstDifferingTokenIdx = idx
                break

        for n in xrange(len(self) - firstDifferingTokenIdx):
            newPathToks.append('..')

        newPathToks += other._splits[firstDifferingTokenIdx:]

        return Path('/'.join(newPathToks), self.CaseMatters)

    def inject(self, other, envDict=None):
        """
        injects an env variable into the path - if the env variable doesn't
        resolve to tokens that exist in the path, a path string with the same
        value as self is returned...

        NOTE: a string is returned, not a Path instance - as Path instances are
        always resolved

        NOTE: this method is alias'd by __lshift__ and so can be accessed using the << operator:
        d:/main/content/mod/models/someModel.ma << '%VCONTENT%' results in %VCONTENT%/mod/models/someModel.ma
        """

        toks = toksLower = self._splits
        otherToks = Path(other, self.CaseMatters, envDict=envDict).split()
        newToks = []
        n = 0
        if not self.CaseMatters:
            toksLower = [t.lower() for t in toks]
            otherToks = [t.lower() for t in otherToks]

        while n < len(toks):
            tok, tokLower = toks[n], toksLower[n]
            if tokLower == otherToks[0]:
                allMatch = True
                for tok, otherTok in zip(toksLower[n + 1:], otherToks[1:]):
                    if tok != otherTok:
                        allMatch = False
                        break

                if allMatch:
                    newToks.append(other)
                    n += len(otherToks) - 1
                else:
                    newToks.append(toks[n])
            else:
                newToks.append(tok)
            n += 1

        return '/'.join(newToks)

    __lshift__ = inject

    def findNearest(self):
        """
        returns the longest path that exists on disk
        """
        path = self
        while not path.exists() and len(path) > 1:
            path = path.up()

        if not path.exists():
            raise IOError("Cannot find any path above this one")

        return path

    def asNative(self):
        """
        returns a string with system native path separators
        """
        return os.path.normpath(str(self))

    def startswith(self, other):
        """
        returns whether the current instance begins with a given path fragment.  ie:
        Path('d:/temp/someDir/').startswith('d:/temp') returns True
        """
        if not isinstance(other, type(self)):
            other = Path(other, self.CaseMatters)

        otherToks = other.split()
        selfToks = self.split()
        if not self.CaseMatters:
            otherToks = [t.lower() for t in otherToks]
            selfToks = [t.lower() for t in selfToks]

        if len(otherToks) > len(selfToks):
            return False

        for tokOther, tokSelf in zip(otherToks, selfToks):
            if tokOther != tokSelf: return False

        return True

    isUnder = startswith

    def endswith(self, other):
        """
        determines whether self ends with the given path - it can be a string
        """
        #copies of these objects NEED to be made, as the results from them are often cached - hence modification to them
        #would screw up the cache, causing really hard to track down bugs...  not sure what the best answer to this is,
        #but this is clearly not it...  the caching decorator could always return copies of mutable objects, but that
        #sounds wasteful...  for now, this is a workaround
        otherToks = list(Path(other).split())
        selfToks = list(self._splits)
        otherToks.reverse()
        selfToks.reverse()
        if not self.CaseMatters:
            otherToks = [t.lower() for t in otherToks]
            selfToks = [t.lower() for t in selfToks]

        for tokOther, tokSelf in zip(otherToks, selfToks):
            if tokOther != tokSelf:
                return False

        return True

    def _list_filesystem_items(self, itemtest, recursive=False):
        """
        does all the listing work - itemtest can be a callable that gets passed the filepath
        and should return a boolean
        """
        if not self.exists():
            return

        if recursive:
            walker = os.walk(self)
            for path, subs, files in walker:
                path = Path(path, self.CaseMatters)

                for sub in subs:
                    p = path / sub
                    if itemtest(p):
                        yield p

                for item in files:
                    p = path / item
                    if itemtest(p):
                        yield p
        else:
            for item in os.listdir(self):
                p = self / item
                if itemtest(p):
                    yield p

    def dirs(self, recursive=False):
        return self._list_filesystem_items(os.path.isdir, recursive)

    def files(self, recursive=False):
        return self._list_filesystem_items(os.path.isfile, recursive)

def findFirstInPaths(filename, paths):
    """
    given a filename or path fragment, this will return the first occurance of a file with that name
    in the given list of search paths
    """
    for p in paths:
        loc = Path(p) / filename
        if loc.exists():
            return loc

    raise Exception("The file %s cannot be found in the given paths" % filename)

def findFirstInEnv(filename, envVarName):
    """
    given a filename or path fragment, will return the full path to the first matching file found in
    the given env variable
    """
    return findFirstInPaths(filename, os.environ[envVarName].split(os.pathsep))

def findFirstInPath(filename):
    """
    given a filename or path fragment, will return the full path to the first matching file found in
    the PATH env variable
    """
    return findFirstInEnv(filename, 'PATH')

def findInPyPath(filename):
    """
    given a filename or path fragment, will return the full path to the first matching file found in
    the sys.path variable
    """
    return findFirstInPaths(filename, sys.path)

#end
