
from __future__ import with_statement

import logging

import simple_p4

import path
import misc

logger = logging.getLogger(__name__)

class MayaSceneParser(object):
    def __init__(self, stream):
        self.stream = stream

    def iterReferencedFilepaths(self, recursive=False):
        '''
        yields the maya scenes referenced by this one
        '''
        yielded = set()
        for line in self.stream:

            # we've past the referencing part in the header so bail
            if line.startswith('fileInfo'):
                return

            if line.startswith('file '):
                endIdx = line.rfind('"')
                startIdx = line[:endIdx].rfind('"')
                aFilepath = path.Path(line[startIdx + 1:endIdx])
                if aFilepath in yielded:
                    continue

                yielded.add(aFilepath)
                yield aFilepath

                if recursive and aFilepath.exists():
                    with open(aFilepath) as f:
                        aFilepathParser = MayaSceneParser(f)
                        for aChildFilepath in aFilepathParser.iterReferencedFilepaths(True):
                            if aChildFilepath in yielded:
                                continue

                            yielded.add(aChildFilepath)
                            yield aChildFilepath

    @misc.d_yieldUnique
    def iterShaderFilepaths(self):
        for creationCmd, setupCmds in self.iterNodeCreationChunks('FShader'):
            for cmdStr in setupCmds:
                if ' ".file" ' in cmdStr:
                    toks = cmdStr.split('"')

                    yield path.Path(toks[-2])

    @misc.d_yieldUnique
    def iterTBReferencedFilepaths(self, recursive=False):
        for createCmd, setupCmds in self.iterNodeCreationChunks('transform'):
            for cmdStr in setupCmds:
                if '.TBReferencePath' in cmdStr:
                    toks = cmdStr.split('"')
                    maFilepath = path.Path(toks[-2])

                    yield maFilepath

                    if recursive:
                        with open(maFilepath) as tbRefFile:
                            for subRef in MayaSceneParser(tbRefFile).iterTBReferencedFilepaths(True):
                                yield subRef

    def iterNodeCreationChunks(self, nodeTypeFilter=None):
        fIter = iter(self.stream)
        def countLinesTillNext(startLine):
            nodeLines = []
            for line in fIter:
                isCompleteLine = line.rstrip().endswith(';')
                if line.startswith('\t') or not isCompleteLine:
                    nodeLines.append(line)
                    continue

                return startLine, nodeLines, line

        nodeCreationStr = 'createNode '
        if nodeTypeFilter is not None:
            nodeCreationStr = 'createNode %s ' % nodeTypeFilter

        for line in fIter:
            while line.startswith(nodeCreationStr):
                createCmd, setupCmds, line = countLinesTillNext(line)

                yield createCmd, setupCmds

class MayaScene(object):
    def __init__(self, filepath):
        self.filepath = path.Path(filepath)

    def iterReferencedMayaScenes(self, recursive=False):
        with open(self.filepath) as f:
            for mayaFilepath in MayaSceneParser(f).iterReferencedFilepaths(recursive):
                yield MayaScene(mayaFilepath)

    def iterReferencedFilepaths(self, recursive=False):
        with open(self.filepath) as f:
            for mayaFilepath in MayaSceneParser(f).iterReferencedFilepaths(recursive):
                yield mayaFilepath

    def iterTBReferencedFilepaths(self, recursive=False):
        with open(self.filepath) as f:
            for filepath in MayaSceneParser(f).iterTBReferencedFilepaths(recursive):
                yield filepath

    def iterShaderFilepaths(self):
        with open(self.filepath) as f:
            for filepath in MayaSceneParser(f).iterShaderFilepaths():
                yield filepath

    def iterShaderAndTextureFilepaths(self):
        with open(self.filepath) as f:
            for filepath in MayaSceneParser(f).iterShaderAndTextureFilepaths():
                yield filepath

    def iterNodeCreationChunks(self, nodeTypeFilter=None):
        with open(self.filepath) as f:
            for data in MayaSceneParser(f).iterNodeCreationChunks(nodeTypeFilter):
                yield data

def reportNegativeTBLocalIdValues():
    dirToSearchWithin = path.TB_DATA / 'models/world'
    for f in dirToSearchWithin.files(True):
        if not f.hasExtension('ma'):
            continue

        offendingNodes = []
        for createCmd, setupCmds in MayaScene(f).iterNodeCreationChunks('transform'):
            for line in setupCmds:
                if '.TBLocalId' in line:
                    toks = line.split()
                    valueTok = toks[-1]
                    valueStr = valueTok[1:-2]
                    assert valueTok.startswith('"') and valueTok.endswith('";')
                    if '-' in valueStr:

                        # ok so we've found an offending node, so extract the node name
                        nodeToks = createCmd.split()
                        nameIdx = nodeToks.index('-n') + 1
                        nodeName = nodeToks[nameIdx][1:-1]
                        offendingNodes.append(nodeName)
                    else:
                        assert valueStr.isdigit()

        if offendingNodes:
            print "Offending nodes found in %s" % f
            for node in offendingNodes:
                print "\t%s" % node

            print "--------------------"

#end
