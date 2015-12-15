
def removeDupes(iterable):
    """
    Removes duplicate members from an iterable while preserving order.
    """
    uniques = set()
    dupeless = []
    for item in iterable:
        if item in uniques:
            continue

        dupeless.append(item)
        uniques.add(item)

    return dupeless

def uniqueVisitor(itemIterable, itemDataExtractor):
    yielded = set()
    for f in itemIterable:
        result = itemDataExtractor(f)
        if result in yielded:
            continue

        yielded.add(result)

        yield result

def d_yieldUnique(f):
    """
    Wraps functions that return generator objects and filters out duplicate values yielded
    """
    def wrapped(*a, **kw):
        yielded = set()
        for x in f(*a, **kw):
            if x in yielded:
                continue

            yielded.add(x)

            yield x

    wrapped.__module__ = f.__module__
    wrapped.__name__ = f.__name__
    wrapped.__doc__ = f.__doc__

    return wrapped

def uiCB(func, *a, **kw):
    """
    Mainly used for creating callbacks within loops.

    Because of the unusual variable scoping in python, creating a lambda inside a loop means
    its not possible to use the iterator variable inside the lambda because it changes with
    each loop.  By entering this function and returning a lambda the scope gets "baked"
    into the lambda object.
    """
    return lambda *_: func(*a, **kw)

def iterClsHierarchy(cls):
    yield cls
    for subCls in cls.__subclasses__():
        for subSubCls in iterClsHierarchy(subCls):
            yield subSubCls

def getNamedSubclass(cls, name):
    for subCls in iterClsHierarchy(cls):
        if subCls.__name__ == name:
            return subCls

class Callback(object):
    def __init__(self, func, *a, **kw):
        self._func = func
        self._a = a
        self._kw = kw

    def __call__(self, *a, **kw):
        return self._func(*self._a, **self._kw)

def iterBy(iterable, step=2):
    i = iter(iterable)
    while True:
        toYield = []
        try:
            for n in xrange(step):
                toYield.append(i.next())

            yield toYield
        except StopIteration:
            if toYield:
                yield toYield

            break

#end
