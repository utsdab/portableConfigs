
from .. import presets

import base_ui
import filterable_list

class PresetsListWidget(filterable_list.FilterableListWidget):
    pass

class PresetManager(base_ui.MayaQWidget):
    def __init__(self,  location, extension=presets.DEFAULT_EXT):
        base_ui.MayaQWidget.__init__(self)

        self._manager = presets.Manager(location, extension)
        self._presets = PresetsListWidget()

        layout = self.makeVLayout()
        layout.addWidget(self._presets, 1)

        self.setLayout(layout)

        self.populate()

    def populate(self):
        for preset in self._manager.iterPresets():
            self._presets.append(preset)

#end
