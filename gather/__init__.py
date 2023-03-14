'''
1. find (or create) gatherers who share your interests
2. suggest a focus for s
3. gather what yall know in a basket
'''
from .basket import Basket
from .focus import Focus
from .gatherer import gatherer_decorator


er = gatherer_decorator
#  ^ convenience for use as `@gather.er(...)`
#       (is also joke because "erer" in "gatherer" can blur together
#        visually (thanks for the data compression, cerebral cortex)
#        and verbally (thanks for being you, tongue)
#       )


__all__ = ('er', 'Focus', 'Basket',)


if __debug__:
    import unittest

    # modules with tests:
    from . import focus, gatherer, basket

    def load_tests(loader, tests, pattern):
        suite = unittest.TestSuite()
        for module in (focus, gatherer, basket):
            suite.addTests(loader.loadTestsFromModule(module))
        return suite
