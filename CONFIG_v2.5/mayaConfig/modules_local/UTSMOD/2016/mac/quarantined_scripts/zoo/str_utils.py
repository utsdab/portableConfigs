
import misc

parityTestsL = ('l', 'left', 'lft', 'lf', 'lik')
parityTestsR = ('r', 'right', 'rgt', 'rt', 'rik')

class Parity(int):

    PARITIES = NONE, LEFT, RIGHT = None, 0, 1

    #odd indices are left sided, even are right sided
    NAMES = [ '_L', '_R',
              '_a_L', '_a_R',
              '_b_L', '_b_R',
              '_c_L', '_c_R',
              '_d_L', '_d_R' ]

    def __new__(cls, idx):
        return int.__new__(cls, idx)

    def __eq__(self, other):
        if other is None:
            return False

        return self % 2 == int(other) % 2

    def __nonzero__(self):
        return self % 2

    def __ne__(self, other):
        return not self.__eq__(other)

    def asMultiplier(self):
        return (-1) ** self

    def asName(self):
        return self.NAMES[self]

    def isOpposite(self, other):
        return (self % 2) != (other % 2)

Parity.LEFT, Parity.RIGHT = Parity(Parity.LEFT), Parity(Parity.RIGHT)

class Tokenizer(str):

    def camelCase(self):
        toks = []
        if self:
            curTok = []
            def appendToken():
                toks.append(''.join(curTok))

            charIter = iter(self)
            curTok.append(next(charIter))
            for char in charIter:
                if char.isupper():
                    appendToken()
                    curTok = []

                curTok.append(char)

            appendToken()

        return toks

    def split(self, separator='_'):
        toks = []
        for tok in self.camelCase():
            toks += str.split(tok, separator)

        return [tok for tok in toks if tok]

    def splitWithIndices(self, separator='_'):
        find = str.find

        toks = self.split(separator)
        indices = []
        lastIndex = 0
        for tok in toks:
            idx = lastIndex = find(self, tok, lastIndex)
            indices.append(idx)

        return toks, indices

class NodeName(object):
    def __init__(self, node):
        self._node = node

    def __str__(self):
        return self._node

    __unicode__ = __str__
    __repr__ = __str__

    def pathToks(self):
        return str(self._node).split('|')

    def stripNamespace(self):
        return '|'.join(tok.split(':')[-1] for tok in self.pathToks())

    def addNamespace(self, namespace):
        if not namespace.endswith(':'):
            namespace += ':'

        return '|'.join(namespace + tok for tok in self.pathToks())

    def strippedLeafName(self):
        return self.pathToks()[-1].split(':')[-1]

    def getParity(self):
        toks = Tokenizer(str(self._node))
        return getParityAndToken(toks)[0]

def getStrippedLeafName(node):
    return NodeName(node).strippedLeafName()

def getCommonPrefix(strs):
    '''
    returns the longest prefix common to all given strings
    '''
    prefix = ''
    first = strs[0]

    for n, s in enumerate(first):
        for aStr in strs[1:]:
            if s != aStr[n]:
                return prefix

        prefix += s

    return prefix

def getParityAndToken(toks):
    '''
    returns a parity number for a given name.  parity is 0 for none, 1 for left, and 2 for right
    '''
    lowerToks = [tok.lower() for tok in toks]
    lowerToksSet = set(lowerToks)
    existingParityToksL = lowerToksSet.intersection(set(parityTestsL))

    if existingParityToksL:
        parityStr = existingParityToksL.pop()

        return Parity.LEFT, parityStr, lowerToks.index(parityStr)

    existingParityToksR = lowerToksSet.intersection(set(parityTestsR))
    if existingParityToksR:
        parityStr = existingParityToksR.pop()

        return Parity.RIGHT, parityStr, lowerToks.index(parityStr)

    return Parity.NONE, None, -1

def camelCaseToNice(name, niceParityNames=True):
    words = Tokenizer(name).split()

    if niceParityNames:
        parity, parityToken, parityTokenIdx = getParityAndToken(words)
        if parity is not Parity.NONE:
            niceParityStr = (parityTestsL, parityTestsR)[ parity ][ 1 ]

    return ' '.join(w.capitalize() for w in words)

def swapParity(name):
    nameToks, tokIndices = Tokenizer(name).splitWithIndices()
    lowerToks = [tok.lower() for tok in nameToks]
    lowerToksSet = set(lowerToks)

    allParityTests = parityTestsL, parityTestsR

    for parityTests, otherTests in zip(allParityTests, reversed(allParityTests)):
        parityTokensPresent = lowerToksSet.intersection(set(parityTests))

        if parityTokensPresent:

            # this is the caseless parity token
            caselessParityToken = parityTokensPresent.pop()

            # this is the token index
            idxInName = lowerToks.index(caselessParityToken)
            idxInTokens = parityTests.index(caselessParityToken)

            # this is the cased parity token
            parityToken = nameToks[idxInName]

            # figure out the replacement parity token
            otherParityToken = matchCase(otherTests[idxInTokens], parityToken)

            # get the string index and lets cut the string up with the replacement parity token
            prefix = name[:tokIndices[idxInName]]
            suffix = name[tokIndices[idxInName] + len(parityToken):]

            return '%s%s%s' % (prefix, otherParityToken, suffix)

    return name

def stripParity(name):
    toks, indices = Tokenizer(name).splitWithIndices()
    parity, parityToken, parityTokenIdx = getParityAndToken(toks)

    if parity:
        strIdx = indices[parityTokenIdx]
        strEndIdx = strIdx + len(parityToken) - 1

        preName = name[:strIdx]
        postName = name[strEndIdx+1:]
        if preName.endswith('_') and postName.startswith('_'):
            postName = postName[1:]

        newName = preName + postName
        if newName.endswith('_'):
            newName = newName[:-1]

        return newName

    return name

def matchCase(theStr, caseToMatch):
    matchedCase = []
    lastCaseWasLower = True
    for charA,charB in zip(theStr,caseToMatch):
        lastCaseWasLower = charB.islower()
        a = (charA.upper(), charA.lower()) [ lastCaseWasLower ]
        matchedCase.append(a)

    lenA, lenB = len(theStr), len(caseToMatch)
    if lenA > lenB:
        remainder = theStr[lenB:]
        if lastCaseWasLower: remainder = remainder.lower()
        matchedCase.extend(remainder)

    return ''.join(matchedCase)

def matchNames(srcList, tgtList, tryFlippedParity=False):
    """
    Returns a list with the same length as the source list of the most appropriate
    matches for each source item in the given list of target names. If no match is
    found, the value for that source item is None

    Ie: all items in the return list of names will be the best match from the
    target list
    """

    # init the matches with nulls
    matches = [None for _ in srcList]

    # create a mutated src list with namespaces/paths stripped
    strippedSrcs = [NodeName(src).strippedLeafName() for src in srcList]

    def anyUnmatched():
        return any(m is None for m in matches)

    def findMatch(src, aTgtList):
        for n, tgt in enumerate(aTgtList):
            if src == tgt:
                match = tgtList.pop(n)
                if aTgtList is not tgtList:
                    aTgtList.pop(n)

                return match

    def performMatches(aTgtList):
        for n, m in enumerate(matches):
            if m is None:

                # look for a match on the exact src name
                matches[n] = findMatch(srcList[n], aTgtList)

                # now look for a match on the stripped src name
                if matches[n] is None:
                    matches[n] = findMatch(strippedSrcs[n], aTgtList)

    # first, look for exact name matches
    for n, src in enumerate(srcList):
        matches[n] = findMatch(src, tgtList)

    # if there are any unmatched nodes, try stripping paths/namespaces
    if anyUnmatched():
        tgtListStripped = [NodeName(tgt).strippedLeafName() for tgt in tgtList]
        performMatches(tgtListStripped)

    # if there are still unmatched nodes, try flipping parity
    if tryFlippedParity and anyUnmatched():
        tgtListFlipped = [swapParity(tgt) for tgt in tgtList]
        performMatches(tgtListFlipped)

        if anyUnmatched():
            tgtListFlippedAndStripped = [NodeName(tgt).strippedLeafName() for tgt in tgtListFlipped]
            performMatches(tgtListFlippedAndStripped)

    return matches

def matchNamesDict(srcList, tgtList, **kwargs):
    matches = matchNames(srcList, tgtList, **kwargs)
    matchDict = {}
    for src, tgt in zip(srcList, matches):
        matchDict[src] = tgt

    return matchDict

class Mapping(object):
    def __init__(self, srcList=(), tgtList=()):
        self.srcs = list(srcList)
        self.tgts = list(tgtList)

    def __iter__(self):
        for src, tgt in zip(self.srcs, self.tgts):
            if src:
                yield src

    def __len__(self):
        return len(self.keys())

    def __contains__(self, item):
        return item in self.srcs

    def __getitem__(self, item):
        values = []
        for src, tgt in self.iteritems():
            if src == item:
                if tgt:
                    values.append(tgt)

        return values

    def __setitem__(self, item, value):
        if isinstance(value, basestring):
            value = [value]

        asDict = self.asDict()
        asDict[ item ] = value
        self.setFromDict(asDict, self.srcs)

    def __nonzero__(self):
        for src, tgt in self.iteritems():
            if tgt:
                return True

        return False

    def iteritems(self):
        for src, tgt in zip(self.srcs, self.tgts):
            if src:
                yield src, tgt

    def keys(self):
        return misc.removeDupes(src for src, tgt in self.iteritems())

    def values(self):
        return misc.removeDupes(tgt for src, tgt in self.iteritems())

    def swap(self):
        '''
        swaps sources and targets - this is done in place
        '''
        self.srcs, self.tgts = self.tgts, self.srcs
        return self

    def copy(self):
        '''
        returns a copy of the mapping object
        '''
        return self.__class__.FromMapping(self)

    def pop(self, index=-1):
        src = self.srcs.pop(index)
        tgt = self.tgts.pop(index)

        return src, tgt

    def insert(self, index, src, tgt):
        self.srcs.insert(index, src)
        self.tgts.insert(index, tgt)

    def append(self, src, tgt):
        self.srcs.append(src)
        self.tgts.append(tgt)

    def moveItem(self, index, places=1):
        src, tgt = self.pop(index)
        self.insert(index + places, src, tgt)

    def moveItemUp(self, index, places=1):
        return self.moveItem(index, -abs(places))

    def moveItemDown(self, index, places=1):
        return self.moveItem(index, abs(places))

    def setFromDict(self, mappingDict, ordering=()):
        '''
        Sets the mapping from a mapping dictionary.  If an ordering iterable is given then the ordering
        of those sources is preserved.
        '''
        srcs = []
        tgts = []
        def appendTgt(src, tgt):
            if isinstance(tgt, basestring):
                srcs.append(src)
                tgts.append(tgt)
            elif isinstance(tgt, (list, tuple)):
                for t in tgt:
                    srcs.append(src)
                    tgts.append(t)

        for src in ordering:
            tgt = mappingDict.pop(src)
            appendTgt(src, tgt)

        for src, tgt in mappingDict.iteritems():
            appendTgt(src, tgt)

        self.srcs = srcs
        self.tgts = tgts

    def asStr(self):
        return '\n'.join([ '%s  ->  %s' % m for m in self.iteritems() ])

    @classmethod
    def FromDict(cls, mappingDict, ordering=()):
        new = Mapping([], [])
        new.setFromDict(mappingDict, ordering)

        return new

    @classmethod
    def FromMapping(cls, mapping):
        return cls(mapping.srcs, mapping.tgts)

    @classmethod
    def FromPairs(cls, pairs):
        srcs, tgts = [], []
        for src, tgt in pairs:
            srcs.append(src)
            tgts.append(tgt)

        return cls(srcs, tgts)

    def asDict(self):
        matchDict = {}
        for src, tgt in self.iteritems():
            try:
                matchDict[src].append(tgt)
            except KeyError:
                matchDict[src] = [tgt]

        return matchDict

    def asFlatDict(self):
        matchDict = {}
        for src, tgt in zip(self.srcs, self.tgts):
            matchDict[ src ] = tgt

        return matchDict

#end
