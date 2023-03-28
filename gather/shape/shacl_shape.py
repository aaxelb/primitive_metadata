import abc
import dataclasses
import typing

import rdflib

from gather.basket import Basket
from gather.language import LangString


class ShaclShape(abc.ABC):
    '''interface for a portion of RDF graph that conforms with a SHACL shape
    '''
    # required constants for each shape class:
    IRI = None
    NAME = None
    DESCRIPTION = None

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
        assert isinstance(cls.IRI, str)
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

    @dataclasses.dataclass
    class LilShape(ShaclShape):
        IRI = BLRGL.LilShape
        NAME = LangString(('en', 'LilShape'))
        DESCRIPTION = LangString(
            ('en', (
                'LilShape is a little shape (where "little" is '
                'abbreviated "lil") intended for testing ShaclShape'
            )),
        )

        # LilShape properties
        # python tries to parse iri as typehint: `blarg: BLRGL.blarg`
        txt: rdflib.RDF.langString

    class LilShapeTest(unittest.TestCase):
        def test_valid(self):
            self.assertTrue(LilShape.validate_shape())
