
from __future__ import with_statement

import os
import stat

import P4

p4 = P4.P4()

def d_withP4Connection(f):
    '''
    ensure the p4 connection is open
    '''
    def wrapped(*a, **kw):

        # if its already connected, just return the value
        if p4.connected():
            return f(*a, **kw)

        # otherwise connect first
        with p4.connect():
            return f(*a, **kw)

    wrapped.__name__ = f.__name__
    wrapped.__doc__ = f.__doc__

    return wrapped

class ChangeContext(object):
    '''
    Any p4 command created within this context will go into the changelist
    the context was instantiated with.
    '''
    CHANGE = None

    def __init__(self, changeOrDesc, deleteIfEmpty=False, revertUnchanged=False, revertOnException=False):
        self._change = changeOrDesc
        self._deleteIfEmpty = deleteIfEmpty
        self._revertUnchanged = revertUnchanged
        self._revertOnException = revertOnException

    def __enter__(self):
        self._initialChange = self.CHANGE
        self._initialConnected = p4.connected()

        if not self._initialConnected:
            p4.connect()

        # if the CHANGE variable has been set already then this is nested within another ChangeContext
        # so bail.  Outer change contexts take precedence
        if self.CHANGE is None:
            if isinstance(self._change, basestring):
                self._change = Change.GetOrCreateByDescription(self._change)

            assert isinstance(self._change, Change)
            ChangeContext.CHANGE = self._change
        else:
            self._change = ChangeContext.CHANGE

        return ChangeContext.CHANGE

    def __exit__(self, *exc_info):
        if self._change:

            # make sure the change actually exists - something within this context may have deleted it
            if self._change.exists():
                if self._revertUnchanged:
                    revertUnchanged(self._change.files)

                # if revert on exception is set, check for an exception
                if self._revertOnException and exc_info[0] is not None:

                    # if the changelist actually has files, revert them
                    files = self._change.files
                    if files:
                        revert(self._change.files)

                if self._deleteIfEmpty:
                    self._change.deleteIfEmpty()

        ChangeContext.CHANGE = self._initialChange
        if not self._initialConnected:
            p4.disconnect()

    @classmethod
    def GetAdditionalArgs(cls):
        if type(cls.CHANGE) is Change:
            return ('-c', cls.CHANGE.number)

        return ()

def d_insertChange(f):
    def wrapped(*a):
        if '-c' not in a:
            a += ChangeContext.GetAdditionalArgs()

        return f(*a)

    wrapped.__name__ = f.__name__
    wrapped.__doc__ = f.__doc__

    return wrapped

class StatNames(object):
    '''
    makes the keys in fstat dictionaries a little more visible - plus auto-completion FTW
    '''
    OTHER_OPEN = 'otherOpen'
    CLIENT_FILE = 'clientFile'
    DEPOT_FILE = 'depotFile'
    ACTION = 'action'
    HEAD_REV = 'headRev'
    HAVE_REV = 'haveRev'
    CHANGE = 'change'

    IN_WORKSPACE = 'inWorkspace'
    IN_DEPOT = 'inDepot'

@d_withP4Connection
def runOnSingleOrMultiple(cmd, fileOrFiles, *args):
    if isinstance(fileOrFiles, basestring):
        fileOrFiles = [fileOrFiles]

    allArgs = list(args) + list(fileOrFiles)

    ret = p4.run(cmd, *allArgs)

    # the P4 wrapper has this awesome feature where if there is an error, the return value is a big fat
    # error string that you'd see printed to stdout (or /sometimes/ stderr).  This sanitises the return
    # value so that all list members are at least dicts
    cleanRet = [val if type(val) is dict else {'error': val, 'action': 'failed'} for val in ret]

    return cleanRet

@d_insertChange
def edit(fileOrFiles, *args):
    try:
        return runOnSingleOrMultiple('edit', fileOrFiles, *args)

    except P4.P4Exception, x:
        xStr = str(x)
        if 'not under client' in xStr:
            return []

        raise

@d_insertChange
def add(fileOrFiles, *args):
    return runOnSingleOrMultiple('add', fileOrFiles, *args)

@d_insertChange
def delete(fileOrFiles, *args):
    return runOnSingleOrMultiple('delete', fileOrFiles, *args)

def sync(fileOrFiles):
    try:
        return runOnSingleOrMultiple('sync', fileOrFiles)
    except P4.P4Exception, x:
        xStr = str(x)
        if 'up-to-date' not in xStr:
            raise

def revert(fileOrFiles, unchangedOnly=False):
    try:
        args = ()
        if unchangedOnly:
            args = ('-a',)

        return runOnSingleOrMultiple('revert', fileOrFiles, *args)

    except P4.P4Exception, x:
        # if there are no files open in the given location p4 will raise an exception which is a touch over the top
        xStr = str(x)
        if 'not opened on this client' in xStr or \
           'not opened for edit' in xStr or \
           'is not under client' in xStr:
            return []

        raise

def revertUnchanged(fileOrFiles):
    return revert(fileOrFiles, True)

@d_withP4Connection
@d_insertChange
def rename(filepath, newFilepath, *args):
    iArgs = args + (filepath, newFilepath)
    ret = p4.run('integrate', *iArgs)

    dArgs = args + (filepath,)
    ret = p4.run('delete', *dArgs)

@d_withP4Connection
def editOrAdd(fileOrFiles):
    '''
    given some files (or file) figures out which ones to open for add and which to
    open for edit.  This call is quite efficient in terms of p4 communication.  It
    queries all files for their p4 stats, then partitions them into a list of files
    for add and a list for edit.  Then potentially 2 more calls.

    NOTE: files not in the client view are silently ignored
    '''
    if isinstance(fileOrFiles, basestring):
        fileOrFiles = [fileOrFiles]

    stats = fstat(fileOrFiles)
    forAdd = []
    forEdit = []
    for s in stats:
        if not s[StatNames.IN_WORKSPACE]:
            continue

        if s[StatNames.IN_DEPOT]:
            forEdit.append(s[StatNames.CLIENT_FILE])
        else:
            forAdd.append(s[StatNames.CLIENT_FILE])

    if forAdd: add(forAdd)
    if forEdit: edit(forEdit)

def getFilesOpenFor(files):
    '''
    given a list of files, this function returns which of them are actually
    open in p4 (ie for edit/add/integrate/delete)
    '''
    openedFiles = []
    stats = fstat(files)
    for stat in stats:
        if stat.get(StatNames.ACTION):
            openedFiles.append(stat[StatNames.CLIENT_FILE])

    return openedFiles

@d_withP4Connection
def fstat(fileOrFiles):
    if isinstance(fileOrFiles, basestring):
        fileOrFiles = [fileOrFiles]

    # try a batch fstat query
    try:
        statDicts = p4.run('fstat', *fileOrFiles)
        for s in statDicts:
            s[StatNames.IN_WORKSPACE] = True
            s[StatNames.IN_DEPOT] = True

    # fallback to querying the files one by one...
    except P4.P4Exception, x:
        statDicts = []
        for f in fileOrFiles:
            try:
                stat = p4.run('fstat', f)[0]
                stat[StatNames.IN_WORKSPACE] = True
                stat[StatNames.IN_DEPOT] = True
                statDicts.append(stat)
            except P4.P4Exception, x:
                stat = {StatNames.IN_WORKSPACE: True,
                        StatNames.IN_DEPOT: True,
                        StatNames.CLIENT_FILE: f}

                if 'no such file' in x.value:
                    stat[StatNames.IN_DEPOT] = False

                elif 'not in client view' in x.value or 'not under client' in x.value:
                    stat[StatNames.IN_WORKSPACE] = False
                    stat[StatNames.IN_DEPOT] = False

                statDicts.append(stat)

    return statDicts

@d_withP4Connection
def lastCheckedInBy(filepath):
    stat = fstat(filepath)[0]
    statChange = stat.get('headChange')
    if statChange is not None:

        # NOTE: these aren't change spec dicts as used by the Change class, they're different
        changeDesc = p4.run('describe', '-s', statChange)[0]

        return changeDesc['user']

class Change(object):

    @classmethod
    @d_withP4Connection
    def Create(cls, description=None, files=()):
        spec = p4.fetch_change()
        spec._files = list(files)  # the P4 API requires that this is a list...
        spec._description = str(description or 'Auto-created changelist')  # apparently p4 doesn't like unicode
        ret = p4.save_change(spec)[0]

        # now that we've saved it, change the status to pending
        spec._status = 'pending'

        # ugh!  seems we need to parse the result of the save_change command...
        # not sure how reliable this will be!
        changeId = int(ret.split()[1])

        # P4.Spec requires this value to be a string...
        spec._change = str(changeId)

        return cls(spec)

    @classmethod
    def Iter(cls):

        # NOTE: connectivity needs to be handled explicitly here because python returns a generator
        # object and then exits, causing the d_withP4Connection decorator to disconnect...  Not sure
        # if there is a more elegant solution
        isConnected = p4.connected()
        if not isConnected:
            p4.connect()

        for spec in p4.run('changes', '-u', p4.user, '-s', 'pending', '-c', p4.client):
            yield cls(spec)

        if not isConnected:
            p4.disconnect()

    @classmethod
    @d_withP4Connection
    def GetOrCreateByDescription(cls, description):
        strippedDesc = description.strip()
        for change in cls.Iter():
            if change.description == strippedDesc:
                return change

        return cls.Create(description)

    def __init__(self, spec):
        # NOTE: python evaluates or expressions in a lazy fashion, so the latter expression is only evaluated
        # if the former fails.  If neither are found a KeyError will still be raised
        self._number = spec.get(StatNames.CHANGE) or spec['Change']

    def __str__(self):
        return 'Change %s' % self.number

    def __eq__(self, other):
        return self.number == other.number

    @property
    @d_withP4Connection
    def spec(self):
        return p4.fetch_change(self._number)

    def getDescription(self):
        return self.spec._description.strip()

    def setDescription(self, descStr):
        '''
        sets the description for the change
        '''
        self.spec._description = descStr
        return p4.save_change(self.spec)[0]

    description = property(getDescription, setDescription)

    def getFiles(self):
        try:
            return self.spec._files
        except KeyError:
            return []

    @d_withP4Connection
    def setFiles(self, files):

        # this is a little awkward (and smelly) but grab the change spec, then modify it, then save it.
        # if we do self.spec._files = list(files) this won't work because "spec" is a property
        spec = self.spec
        spec._files = list(files)
        ret = p4.save_change(spec)[0]

        return ret

    files = property(getFiles, setFiles)

    def reopen(self, fileOrFiles):
        runOnSingleOrMultiple('reopen', fileOrFiles, '-c', self.number)

    def exists(self):
        try:
            spec = self.spec
            return True
        except: return False

    def append(self, filepath):
        '''
        appends the given filepath to this changelist

        NOTE: the filepath must be a depot filepath, not a client filepath!
        '''
        self.files = self.files + [filepath]

    def extend(self, filepaths):
        '''
        extends the files in this changelist
        '''
        self.files = self.files + filepaths

    @property
    def number(self):
        return self._number

    def addFileIfInDefaultChange(self, filepath):
        '''
        adds the given file to this changelist ONLY if it is in the default changelist
        '''
        stat = fstat(filepath)[0]
        curChange = stat.get(StatNames.CHANGE)
        if curChange is None or curChange == 'default':
            self.append(stat.get(StatNames.DEPOT_FILE) or stat[StatNames.CLIENT_FILE])

    @d_withP4Connection
    def revertUnchanged(self):
        p4.run('revert', '-a', '-c', self._number)

    @d_withP4Connection
    def deleteIfEmpty(self):
        if not self.files:
            p4.run('change', '-d', self._number)

class File(file):
    '''
    simple wrapper around python's builtin file class to handle opening for edit before writing
    and opening for add on closing is appropriate
    '''
    P4_MODES = 'w', 'a'
    def __init__(self, name, mode=None, buffering=None):
        if mode is None:
            mode = 'r'

        if buffering is None:
            buffering = 0

        self._p4DealtWith = False

        # if we're opening the file for writing, see if it exists on disk and check its writable state
        # if its writable, assume its already open for edit if its managed by p4
        if mode in self.P4_MODES:
            if os.path.exists(name):
                writable = os.stat(name).st_mode & stat.S_IWRITE
                if not writable:
                    p4stat = fstat(name)[0]
                    if p4stat[StatNames.IN_WORKSPACE] and p4stat[StatNames.IN_DEPOT]:
                        edit(name)

                self._p4DealtWith = True

        super(File, self).__init__(name, mode, buffering)

    def close(self):
        if self.mode in self.P4_MODES:

            # if p4 hasn't been dealt with, then open for add if the file exists
            if not self._p4DealtWith:
                if os.path.exists(self.name):
                    stat = fstat(self.name)[0]

                    # if the file is also in the client workspace then open for add
                    if stat[StatNames.IN_WORKSPACE]:
                        add(self.name)

        super(File, self).close()

__builtins__['file'] = File

def open(name, mode=None, buffering=None):
    '''
    override for the builtin "open" function.  Returns an instance of the File class
    defined above
    '''
    return File(name, mode, buffering)

__builtins__['open'] = open

class EditAddContext(object):
    def __init__(self, filepath, change=None):
        self.filepath = filepath
        self.change = change
        self.stat = None
        self._handled = False

    def __enter__(self):
        self.stat = stat = fstat(self.filepath)[0]

        # if the file already has an action set, nothing to do, mark the file as handled
        action = stat.get(StatNames.ACTION)
        if action is not None:
            if action == 'branch':

                # ok this is annoying - if a file is already in a changelist and we ask
                # p4 to edit AND pass in the changelist it doesn't raise, it just silently
                # continues without doing anything.  so check to see if the file is in a
                # change and explicitly pass that in so that d_insertChange doesn't do its
                # thing
                args = []
                if 'change' in stat:
                    args.append('-c')
                    args.append(stat.get('change'))

                edit(self.filepath, *args)

            self._handled = True

        # if the file isn't in the workspace, nothing we can do, make the file as handled
        elif not stat[StatNames.IN_WORKSPACE]:
            self._handled = True

        # if the file is in the depot, open it for edit
        elif stat[StatNames.IN_DEPOT]:
            args = []
            if self.change:
                args += ['-c', self.change.number]

            edit(self.filepath, *args)
            self._handled = True

        return self

    def __exit__(self, *exc_info):

        # if the file hasn't been handled yet, make sure it exists and add it
        if not self._handled:
            if os.path.exists(self.filepath) and self.change:
                add(self.filepath, '-c', self.change.number)

        # make sure to set this back to None
        self.stat = None

#end