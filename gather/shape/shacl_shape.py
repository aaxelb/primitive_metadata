import abc
import dataclasses
import typing

import rdflib

from gather.basket import Basket
from gather.language import LangString


class ShaclShape:
    '''interface for a portion of RDF graph that conforms with a SHACL shape
    '''
    def __init__(self, iri, shacl_graph):
        self.iri = iri
        self._shacl_graph = shacl_graph

    @property
    def name(self):
        return next(self._shacl_graph.objects(self.iri, SHACL.name|RDFS.label))

    @property
    def description(self):
        return next(self._basket[SHACL.description|RDFS.comment])

    @staticmethod
    def shape_from_shacl(shacl_shape_basket: Basket) -> 'ShaclShape':
        # TODO: ShaclShape subclass from a shacl rdfgraph,
        #       alternative to static subclass definition
        #       (not yet aiming for full shacl support;
        #       just adding shacl features as needed)
        raise NotImplementedError

    @classmethod
    def validate_shape(cls):
        # TODO: specific exceptions
        assert isinstance(cls.iri, str)
        assert isinstance(cls.NAME, LangString)
        assert isinstance(cls.DESCRIPTION, LangString)
        # TODO: validate against official shacl-shacl
        return True

    @classmethod
    def shacl_property_set(cls) -> 'typing.Iterable[ShaclProperty]':
        for name, type_hint in typing.get_type_hints(cls).items():
            print(f'{name}: {type_hint}')
            # TODO yield ShaclProperty(

    def shacl_validation_report(self) -> 'ShaclValidationReport':
        pass  # TODO

    # duck-type for gather.render
    def as_rdf_tripleset(self) -> typing.Iterable[tuple]:
        pass  # TODO


class ShaclProperty(ShaclShape):
    pass


# TODO: ShaclValidationReport = ShaclShape.from_shacl(filepath='rdf_in_static_file.ttl')


if __debug__:
    import unittest

    BLRGL = rdflib.Namespace('ftp://blrgl.example/vocab/')

    LILSHAPE_TURTLE = '''
@prefix shacl: http://www.w3.org/ns/shacl#
@prefix rdfs: http://www.w3.org/2000/01/rdf-schema#
@prefix blrgl: ftp://blrgl.example/vocab/

blrgl:LilShape a shacl:NodeShape ;
    shacl:name "LilShape"@en ;
    shacl:description """
LilShape is a little shape (where 'little' is abbreviated
'lil') intended for testing ShaclShape."""@en ;
    shacl:property [
        shacl:path blrgl:txt ;
        shacl:datatype rdf:langString ;
    ] ,
    [
        shacl:path (blrgl:foo blrgl:bar blrgl:baz) ;
        shacl:class blrgl:FooBarBazd
    ]
'''

    class LilShapeTest(unittest.TestCase):
        def setUp(self):
            lilshape_basket = Basket.
            self.lil_shape = ShaclShape(Basket.fro

        def test_valid(self):
            self.assertTrue(self.LilShape.validate_shape())
