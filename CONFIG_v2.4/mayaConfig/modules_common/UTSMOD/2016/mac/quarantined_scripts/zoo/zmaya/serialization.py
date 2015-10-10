
from maya import cmds

class TypedSerializableDict(dict):
    '''
    serializes the dictionary to the given node/attribute name pair whenever keys are changed.

    You may optionally provide a type dictionary so that key values have a particular type.

    NOTE: this is a simple extension of python's built in dict.
    Ie: issubclass(TypedSerializableDict, dict) is True
    '''

    def __init__(self, node, attrname, typeDict=None):
        serializedValue = cmds.getAttr('%s.%s' % (node, attrname))
        initDict = {}
        if serializedValue:
            # see the notes in the serialize method for the rationalization of the use of eval here
            initDict = eval(serializedValue)

        super(TypedSerializableDict, self).__init__(initDict)

        if typeDict is None:
            typeDict = {}

        self._node = node
        self._attrname = attrname
        self._typeDict = typeDict

    def _coerceValue(self, attr, value):

        if attr not in self._typeDict:
            return value

        valueType = self._typeDict[attr]

        # make sure the value is of the right type
        if type(value) is not valueType:
            value = valueType(value)

        return value

    def __getitem__(self, attr):
        value = super(TypedSerializableDict, self).__getitem__(attr)

        return self._coerceValue(attr, value)

    def __setitem__(self, attr, value):
        initValue = self.get(attr)
        if value is None:
            self.pop(attr)
        else:
            value = self._coerceValue(attr, value)
            super(TypedSerializableDict, self).__setitem__(attr, value)

        # if the value hasn't changed, don't serialize
        if initValue != value:
            self.serialize()

    def __delitem__(self, attr):
        super(TypedSerializableDict, self).__delitem__(attr)
        self.serialize()

    def update(self, *a, **kw):
        super(TypedSerializableDict, self).update(*a, **kw)
        self.serialize()

    def setdefault(self, key, value):
        if key not in self:
            self[key] = value

    def setdefaults(self, otherDict):
        serialize = False

        # there is a touch of code repetition here, but it is simply so serialize only gets called
        # at most once for the call - otherwise it would get called up to len(otherDict.keys) times
        for key, value in otherDict.iteritems():
            if key not in self:
                super(TypedSerializableDict, self).__setitem__(key, value)
                serialize = True

        if serialize:
            self.serialize()

    def serialize(self):
        # we're using super simple serialization here so that complex data types don't get serialized
        # and also so that debugging via the attribute editor is possible (ie human readable
        # serialization values)
        cmds.setAttr('%s.%s' % (self._node, self._attrname), repr(self), type='string')

#end