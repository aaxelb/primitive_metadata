from dataclasses import dataclass, field

import rdflib


SHACL = rdflib.Namespace('http://www.w3.org/ns/shacl#')


def shacldataclass(class_def):
    def _shacldataclass_decorator(subclass):
        return dataclass(subclass)
    return _shacldataclass_decorator


if __debug__:
    import unittest

    BLARG = rdflib.Namespace('https://blarg.example/vocab/')

    @shacldataclass(
        BLARG.Thing,
        metadata={
            SHACL.name: Literal('Thing', language='en'),
            SHACL.description: 'The Thing is the thing that Blarg blargs',
        },
    )
    class BlargThing:
        mytitle: field(
            metadata={
                SHACL.name
                rdflib.DCTERMS.title
            }
        )
        mydescription: DCTERMS.description
        synonym: BLARG.synonym

    class TestThing(unittest.TestCase):
        def test_thing(self):
            thing = BlargThing(
                mytitle=Literal('hello', language='en'),
            )
