from . import (
    focus,
    gatherer,
    basket,
    render,
)

er = gatherer.gatherer_decorator
#  ^ convenience for use as `@gather.er(...)`
#       (is also joke because "erer" in "gatherer" can blur together
#        visually (thanks for the data compression, cerebral cortex)
#        and verbally (thanks for being you, tongue)
#       )

Focus = focus.Focus
Basket = basket.Basket

__all__ = ('er', 'Focus', 'Basket',)


if __debug__:
    # implement "load_tests protocol" for unittest;
    # tests for each module put in a block wrapped
    # by `if __debug__:` (so they'll be ignored if
    # python is started with `-O`, for "Optimize")
    import unittest

    MODULES_WITH_TESTS = (focus, gatherer, basket, render)

    def load_tests(loader, tests, pattern):
        suite = unittest.TestSuite()
        for module in MODULES_WITH_TESTS:
            suite.addTests(loader.loadTestsFromModule(module))
        return suite
