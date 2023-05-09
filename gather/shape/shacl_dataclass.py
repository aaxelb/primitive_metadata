from dataclasses import dataclass, field

import rdflib

from gather.language import Text


SHACL = rdflib.Namespace('http://www.w3.org/ns/shacl#')


def shacldataclass(class_def):
    def _shacldataclass_decorator(subclass):
        return dataclass(subclass)
    return _shacldataclass_decorator


def shacldataclass_from_shacl(shacl_basket):
    assert shacl_basket.focus.rdftype == SHACL.NodeShape, (
        'shacl_basket should be focused on a shacl:NodeShape'
    )


class ShapeMetaclass(type):

    def __getitem__(cls, shape_iri):
        return cls(shape_iri)


class Shape(metaclass=ShapeMetaclass):
    def __init__(self, shape_iri):
        self.__shape_iri = shape_iri


if __debug__:
    import unittest

    BLARG = rdflib.Namespace('https://blarg.example/vocab/')

    blarg_thing_vocab = {
        'mytitle': rdflib.DCTERMS.title,
        'mydescirptn': rdflib.DCTERMS.description,
        'blergBlop': BLARG.blergBlop,
        'inner-prop': BLARG['inner-prop'],
    }

    class BlargThing(Shape, iri=BLARG.Thing):
        mytitle: Text = shape_property(
        )

    @shacldataclass(
        iri=BLARG.Thing,
        metadata={
            rdflib.RDFS.label: Text('Thing', language='en'),
            rdflib.RDFS.comment: Text(
                'The Thing is the thing that Blarg blargs',
                language='en',
            ),
        },
    )
    class BlargThing:
        mytitle: Text = field(
            metadata={
                rdflib.OWL.sameAs: rdflib.DCTERMS.title,
                rdflib.RDFS.label: Text('mytitle', language='en'),
                rdflib.RDFS.comment: Text('a title, but mine', language='en'),
            }
        )
        mydescirptn: Text = field(
            metadata={
                rdflib.OWL.sameAs: rdflib.DCTERMS.title,
                rdflib.RDFS.label: Text('mydescirptn', language='en'),
                rdflib.RDFS.comment: Text('a description, but mine', language='en'),
            }
        )
        blergBlop: 'BlargMerp' = field(
            metadata={
                rdflib.OWL.sameAs: BLARG.blerg,
                rdflib.RDFS.label: Text('blergBlop', language='en'),
                rdflib.RDFS.comment: Text('blergBlop points to a Merp', language='en'),
            }
        )

    @shacldataclass(BLARG.Merp)
    class BlargMerp:
        morp: Text
        myint: int
        blargThing: BlargThing

    class TestThing(unittest.TestCase):
        def test_thing(self):
            thing = BlargThing(
                mytitle=Text('hello', language='en'),
            )
            assert thing.mytitle
