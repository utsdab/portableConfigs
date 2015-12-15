
from maya import cmds

from .. import str_utils

def findItem(itemName):
    if cmds.objExists(itemName):
        return itemName

    return str_utils.matchNames([itemName], cmds.ls(type='transform', r=True))[0]

def getNamespacesFromStrings( theStrs ):
    '''
    returns list of all the namespaces found in the given list of strings
    '''
    namespaces = set()
    for aStr in theStrs:
        namespaces.add( ':'.join( aStr.split( '|' )[-1].split( ':' )[ :-1 ] ) )

    return list( namespaces )

def getOpposites(objs):
    return [str_utils.swapParity(obj) for obj in objs]

def matchNames(srcObjs, tgtObjs, matchOpposites=False):
    namespaces = getNamespacesFromStrings(tgtObjs)
    tgtObjsSet = set(tgtObjs)
    mappedTgts = []

    namespacesToTest = []
    for namespace in namespaces:
        namespaceToks = [tok for tok in namespace.split('|')[-1].split(':') if tok]
        for n, tok in enumerate(namespaceToks):
            namespacesToTest.append(':'.join(namespaceToks[:n+1]))

    for srcObj in srcObjs:

        # if we're matching opposites, swap the parity
        if matchOpposites:
            srcObj = str_utils.swapParity(srcObj)

        # see if the exact source is in the target list
        if srcObj in tgtObjsSet:
            mappedTgts.append(srcObj)

        # if not see if we're able to prepend the given namespace
        else:
            sourceNodeToks = srcObj.split('|')[-1].split(':')
            nodeName = sourceNodeToks[-1]
            foundCandidate = False
            for candidateNamespace in namespacesToTest:
                candidate = '%s:%s' % (candidateNamespace, nodeName)
                if candidate in tgtObjsSet:
                    mappedTgts.append(candidate)
                    foundCandidate = True
                    break

            if not foundCandidate:
                if nodeName in tgtObjsSet:
                    mappedTgts.append(nodeName)
                else:
                    mappedTgts.append('')

    return str_utils.Mapping(srcObjs, mappedTgts)

#end
