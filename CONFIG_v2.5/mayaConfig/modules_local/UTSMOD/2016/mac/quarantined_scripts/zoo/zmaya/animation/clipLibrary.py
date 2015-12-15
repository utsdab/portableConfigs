
import cPickle as pickle

from maya import cmds

from ... import imgSequence
from ... import events

from ... import path
from ... import presets

from .. import viewport_utils

import clip

BASE_PRESET_NAME = 'clips'
DEFAULT_LOCALE = presets.LOCAL

class ClipPreset(object):
    """
    Represents the base class for clip preset wrappers

    The preset provides an interface to the file management of the clip data. It
    handles saving/loading actual clip data to/from files as well as
    copy/move/delete type operations as well as meta functionality like creating
    icons
    """
    ICON_SIZE = 64

    @classmethod
    def PresetFromName(cls, name, libraryName, locale=DEFAULT_LOCALE):
        return presets.Preset(name,
            '%s/%s' % (BASE_PRESET_NAME, libraryName),
            locale,
            cls.EXT)

    @classmethod
    def FromName(cls, name, libraryName, locale=DEFAULT_LOCALE):
        return cls(cls.PresetFromName(name, libraryName, locale))

    def __new__(cls, preset):
        toks = preset.path()[-1].split('.')
        typeTok = toks[1]
        if cls is not ClipPreset:
            return object.__new__(cls, preset)

        for aCls in cls.__subclasses__():
            if aCls.EXT == typeTok:
                return object.__new__(aCls, preset)

        raise TypeError("No preset class found for clip extension %s" % typeTok)

    def __init__(self, preset):
        self._preset = preset

        # these are raised when this clip preset instance is moved/deleted
        # NOTE: if two instances of a preset point to the same on disk preset, only
        # the one the move method was called on will raise the event...
        self.moved = events.EventList()
        self.deleted = events.EventList()

        # raised when clip io starts (read or write)
        self.ioStart = events.EventList()

        # raised when clip io finishes (read or write)
        self.ioEnd = events.EventList()

    def getFiles(self):
        return [self._preset.path()]

    def load(self):

        # raise the io start event
        self.ioStart.trigger()
        with self._preset.open() as f:
            clip = pickle.load(f)

        # raise the io end event
        self.ioEnd.trigger()

        return clip

    def generateIcon(self):
        raise clip.AnimLibError("Not implemented in base class")

    def save(self, theClip):
        if not isinstance(theClip, self.CLS):
            raise TypeError("Value must be of type %s" % str(self.CLS))

        # raise the io start event
        self.ioStart.trigger()
        with self._preset.open('w') as f:
            pickle.dump(theClip, f)

        # generate the icon
        self.generateIcon()

        # raise the io end event
        self.ioEnd.trigger()

    def copy(self, name, libraryName, locale):
        newClip = self.FromName(name, libraryName, locale)
        newDirpath = newClip._preset.path().up()
        for f in self.getFiles():
            newNameToks = [name] + f.getExtensions()
            newFilename = '.'.join(newNameToks)
            f.copy(newDirpath / newFilename)

        return newClip

    def __move(self, name, libraryName, locale):
        newClip = self.copy(name, libraryName, locale)
        self.__delete()
        self._preset = newClip._preset

    def __delete(self):
        for f in self.getFiles():
            path.Path(f).delete()

    def move(self, name, libraryName, locale):
        self.__move(name, libraryName, locale)

        # trigger the renamed event
        self.moved.trigger()

    def rename(self, name):
        self.__move(name, self.libraryName, self._preset.locale)

        # trigger the renamed event
        self.moved.trigger()

    def delete(self):
        self.__delete()

        # trigger the deleted event
        self.deleted.trigger()

    @property
    def libraryName(self):
        return path.Path(self._preset.location)[1:]

    @property
    def library(self):
        return Library(self.libraryName)

    @property
    def locale(self):
        return self._preset.locale

    @property
    def displayText(self):
        return self._preset.path()[-1]

    @property
    def name(self):
        return self._preset.path().name()

class PoseClipPreset(ClipPreset):
    EXT = 'pose'
    CLS = clip.PoseClip

    def getFiles(self):
        files = ClipPreset.getFiles(self)
        files.append(self.iconFilepath)

        return files

    @property
    def iconFilepath(self):
        return self._preset.path().setExtension('png')

    def generateIcon(self):
        viewport_utils.Viewport.Get().generatePlayblastIcon(self.iconFilepath, self.ICON_SIZE, self.ICON_SIZE)

class AnimClipPreset(ClipPreset):
    EXT = 'anim'
    CLS = clip.AnimClip
    MAX_PLAYBLAST_FRAMES = 30

    def getFiles(self):
        files = ClipPreset.getFiles(self)
        files.extend(self.playblastImgSequence.getFiles())

        return files

    @property
    def playblastPrefixFilepath(self):
        presetFilepath = self._preset.path()
        iconFilename = presetFilepath.name()

        return presetFilepath.up() / iconFilename

    @property
    def playblastFileGlob(self):
        return self.playblastPrefixFilepath.setExtension('.*.jpg')

    @property
    def playblastFilepath(self):
        return self.playblastPrefixFilepath.setExtension('.####.jpg')

    @property
    def playblastImgSequence(self):
        return imgSequence.ImgSequence(self.playblastPrefixFilepath)

    def generateIcon(self):

        # make sure to delete any existing files before generating the playblast icons
        # in case the range has changed
        for f in self.playblastImgSequence.getFiles():
            f.delete()

        startFrame, endFrame = clip.getPlaybackRange([])

        # figure out how many frames are going to be blasted - if there are too many,
        # then it takes too long and doesn't really add enough value to warrant, so
        # figure out if we need to skip frames
        increment = 1
        if (endFrame - startFrame) > self.MAX_PLAYBLAST_FRAMES:
            increment = (endFrame - startFrame) / float(self.MAX_PLAYBLAST_FRAMES)

        viewport = viewport_utils.Viewport.Get()
        viewport.generatePlayblast(self.playblastPrefixFilepath, startFrame, endFrame, increment, self.ICON_SIZE, self.ICON_SIZE)

class Library(object):

    @classmethod
    def Iter(cls):
        '''
        Yields libraries
        '''
        yielded = set()
        for locale in presets.LOCALES:
            clipPresetDir = locale.path / BASE_PRESET_NAME
            for d in clipPresetDir.dirs():
                libraryName = d.name()
                if libraryName in yielded:
                    continue

                yielded.add(libraryName)
                yield cls(libraryName)

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __repr__(self):
        return 'Library(%r)' % self.name

    def __eq__(self, other):
        return self.name == other.name

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.name)

    def getPath(self, locale=DEFAULT_LOCALE):
        return locale.path / BASE_PRESET_NAME / self.name

    def create(self):
        for locale in presets.LOCALES:
            path = self.getPath()
            if path.exists() is False:
                path.create()

    def iterPresets(self):
        location = path.Path(BASE_PRESET_NAME) / self.name
        for clipCls in [PoseClipPreset, AnimClipPreset]:
            manager = presets.Manager(location, clipCls.EXT)
            for preset in manager.iterPresets():
                yield preset

    def iterClipPresets(self):
        for preset in self.iterPresets():
            yield ClipPreset(preset)

    def createClip(self, name, clipCls, locale=DEFAULT_LOCALE):
        return clipCls.FromName(name, self.name, locale)

#end
