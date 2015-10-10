
import weakref
import logging

import cls_types

logger = logging.getLogger(__name__)

class WeakMethod(object):
    def __init__(self, instance, function):
        self.__instance = weakref.ref(instance)
        self.__function = weakref.ref(function)

    def __call__(self, *args, **kwargs):
        instance = self.__instance()
        if instance is None:
            return

        function = self.__function()
        if function is None:
            return

        return function(instance, *args, **kwargs)

class EventList(object):
    """
    stores a list of callbacks

    callbacks should all have the same call signature. When the trigger method is called,
    all args/kwargs are passed through to each callback in the list

    NOTE: if a bound method is appended as a callback, a weakref to the instance is
    created so that the object isn't prevented from being GC'd, but function references
    aren't weakrefs so that lambdas can be used as callback functions
    """
    def __init__(self):
        self.__callbacks = []

    def append(self, eventCallback):
        if eventCallback in self.__callbacks:
            return

        # is the callback a bound method? If so we need to do some funkery...
        # NOTE: python 2.x regards both bound and unbound methods as instances of
        # instancemethod so instead we test for the presence of im_self and that
        # the im_self attr isn't None... Not sure if this covers all bases, but
        # it seems to work
        if hasattr(eventCallback, 'im_self') and eventCallback.im_self is not None:
            eventCallback = WeakMethod(eventCallback.im_self, eventCallback.im_func)

        self.__callbacks.append(eventCallback)

    def remove(self, eventCallback):
        try:
            self.__callbacks.remove(eventCallback)
        except ValueError: pass

    def removeAll(self):
        self.__callbacks = []

    def trigger(self, *a, **kw):
        for eventCallback in self.__callbacks:
            try:
                eventCallback(*a, **kw)
            except:
                logger.error("Callback %s failed" % eventCallback, exc_info=1)

class EventId(int): pass

class EventManager(dict):
    __metaclass__ = cls_types.SingletonType

    def createEventId(self):
        '''
        returns a new, unique EventId object that can be used to register events using
        '''
        eventIds = self.keys()
        eventIds.sort()

        if eventIds:
            newEventId = EventId(eventIds[-1] + 1)
        else:
            newEventId = EventId(0)

        self[newEventId] = EventList()

        return newEventId

    def addEventCallback(self, eventId, eventCallback):
        '''
        adds the given callable object to the list of callbacks for the given EventId.  The arguments expected by the
        callback is the responsibility of the code that triggers the event.
        '''
        if type(eventId) is not EventId:
            raise TypeError("You must provide an EventId instance when adding an event callback!")

        try:
            self[eventId].append(eventCallback)
        except KeyError:
            raise KeyError("The event given has not been registered yet!")

    def removeEventCallback(self, eventId, eventCallback):
        try:
            self[eventId].remove(eventCallback)
        except KeyError: pass

    def removeAllEventCallbacks(self, eventId):
        if eventId in self:
            try:
                self[eventId].removeAll()
                del self[eventId]
            except KeyError: pass

    def trigger(self, eventId, *a, **kw):
        '''
        call this when you actually want to execute the events that have been registered for the given event.  Any args
        and kwargs passed to this method are handed to the callbacks being executed.
        '''
        if type(eventId) is not EventId:
            raise TypeError("You must provide an EventId instance when triggering an event!")

        try:
            self[eventId].trigger(*a, **kw)
        except KeyError: pass

class EventHandlerContext(object):
    '''
    Context for registering and unregistering event handlers

    Usage:
    manager = EventManager()
    EVT_SOMETHING = manager.createEventId()
    with EventHandlerContext(EVT_SOMETHING, handler):
        manager.trigger(EVT_SOMETHING, arg1, arg2, ...)

    The handler function will be unregistered upon exiting the with block
    '''
    def __init__(self, eventId, handler):
        self._eventId = eventId
        self._handler = handler
        self._manager = EventManager()

    def __enter__(self):
        self._manager.addEventCallback(self._eventId, self._handler)

        return self._manager

    def __exit__(self, *exc_info):
        self._manager.removeEventCallback(self._eventId, self._handler)

#end