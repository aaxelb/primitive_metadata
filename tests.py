import doctest

from primitive_rdf import (
    iri_namespace,
)

MODULES_WITH_DOCTESTS = (
    iri_namespace,
)


def load_tests(loader, tests, ignore):
    for _module in MODULES_WITH_DOCTESTS:
        tests.addTests(doctest.DocTestSuite(_module))
    return tests
