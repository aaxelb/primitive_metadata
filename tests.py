import doctest

from primitive_metadata import (
    gather,
    primitive_rdf,
)

MODULES_WITH_DOCTESTS = (
    gather,
    primitive_rdf,
)


def load_tests(loader, tests, ignore):
    for _module in MODULES_WITH_DOCTESTS:
        tests.addTests(doctest.DocTestSuite(
            _module,
            optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE,
        ))
    return tests
