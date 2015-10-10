
import path

class Locale(object):
    def __init__(self, name, pathStr):
        self.path = path.Path(pathStr)
        self.name = name

LOCALES = LOCAL, NETWORK = \
    (
    Locale('local', '~/presets/'),
    Locale('network', '~/global/presets/'),
    )

DEFAULT_EXT = 'preset'

class Preset(object):

    @classmethod
    def FromFilepath(cls, filepath):
        filepath = path.Path(filepath)

        for locale in LOCALES:
            if filepath.isUnder(locale.path):
                presetSub = filepath.up() - locale.path

                return cls(filepath.name(), presetSub, locale, filepath.getExtension())

    def __init__(self, name, location, locale=LOCAL, extension=DEFAULT_EXT):
        self.name = name
        self.location = location
        self.locale = locale
        self.extension = extension

    @property
    def localeName(self):
        return self.locale.name

    def path(self):
        return self.locale.path / self.location / ('%s.%s' % (self.name, self.extension))

    def open(self, mode='r'):
        filepath = self.path()
        dirpath = filepath.up()
        if dirpath.exists() is False:
            dirpath.create()

        return open(filepath, mode)

class Manager(object):
    def __init__(self, location, extension=DEFAULT_EXT):
        self.location = location
        self.extension = extension

    def iterPresets(self, localeOrdering=LOCALES):
        presetsYielded = set()
        for locale in localeOrdering:
            baseLocation = locale.path / self.location
            if not baseLocation.exists():
                continue

            for f in baseLocation.files():
                if f.hasExtension(self.extension):
                    if f.name() in presetsYielded:
                        continue

                    presetsYielded.add(f.name())
                    yield Preset.FromFilepath(f)

    def getPreset(self, name, localeOrdering=LOCALES):
        for locale in localeOrdering:
            preset = Preset(name, self.location, locale, self.extension)
            if preset.path().exists():
                return preset

        # if no existing preset is found, return an instance in the default location (the first locale in the list)
        return Preset(name, self.location, localeOrdering[0], self.extension)

#end
