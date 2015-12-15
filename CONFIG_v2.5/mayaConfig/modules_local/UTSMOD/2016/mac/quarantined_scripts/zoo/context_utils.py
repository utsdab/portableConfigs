
def nestableContextFactory():
    '''
    This factory returns a new NestableContext class.

    Because the implementation uses class variables to determine nesting we need to manufacture base
    classes for each
    '''
    class NestableContext(object):
        '''
        Context super class to write nestable context managers.

        Implement the enter method and possibly the exit method.  The enter/exit methods only get called
        by the outer most instance of this context.
        '''
        NESTED = False
        ENTER_STATE = None

        def enter(self):
            raise NotImplemented

        def exit(self):
            pass

        def __enter__(self):
            cls = type(self)

            self._initialNested = cls.NESTED
            if not cls.NESTED:
                cls.ENTER_STATE = self.enter()
                cls.NESTED = True

            self._enterState = cls.ENTER_STATE

            return self._enterState

        def __exit__(self, *exc_info):
            cls = type(self)

            # restore the initial nested state
            cls.NESTED = self._initialNested

            # run the exit method if we're at the top nesting level and reset the enter state
            isAtTop = not cls.NESTED
            if isAtTop:
                self.exit()
                cls.ENTER_STATE = None

        def __call__(self, f):
            def wrapped(*a, **kw):
                with self:
                    return f(*a, **kw)

            wrapped.__module__ = f.__module__
            wrapped.__name__ = f.__name__
            wrapped.__doc__ = f.__doc__

            return wrapped

    return NestableContext

#end