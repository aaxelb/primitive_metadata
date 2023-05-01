import dataclasses
import typing

import rdflib


@dataclasses.dataclass(frozen=True)
class Focus:
    '''the "focus" is what to gather metadata about, and how.
    '''
    iri: rdflib.URIRef      # "what": id should be unambiguous and persistent
    rdftype: rdflib.URIRef  # "how": basket uses rdftype to decide gatherers

    def __post_init__(self):
        try:
            assert (self.iri and self.rdftype)
            assert isinstance(self.iri, rdflib.URIRef)
            assert isinstance(self.rdftype, rdflib.URIRef)
        except AssertionError as err:
            raise ValueError from err

    def as_triples(self) -> typing.Iterable[tuple]:
        yield (self.iri, rdflib.RDF.type, self.rdftype)


if __debug__:
    import unittest

    BLERG = rdflib.Namespace('http://blerg.example/namespace/')

    class FocusDunderTest(unittest.TestCase):
        def test_comparisons(self):
            fo0 = Focus(BLERG.fo, BLERG.Fo)
            fo1 = Focus(rdftype=BLERG.Fo, iri=BLERG.fo)
            cus = Focus(BLERG.cus, BLERG.Cus)
            self.assertEqual(fo0.iri, BLERG.fo)
            self.assertEqual(fo0.rdftype, BLERG.Fo)
            self.assertEqual(fo1.iri, BLERG.fo)
            self.assertEqual(fo1.rdftype, BLERG.Fo)
            self.assertEqual(fo1, fo0)
            self.assertNotEqual(fo0, cus)
            self.assertEqual(len({fo0, fo1}), 1)
            self.assertEqual(len({cus, fo0, fo1}), 2)

        def test_errors(self):
            bad_argss = [
                (None, None),
                (2, 'foo'),
                (BLERG.pie, 'https://nope.example/'),
                ('https://not.example/', BLERG.enough),
            ]
            for bad_args in bad_argss:
                with self.assertRaises(ValueError):
                    Focus(*bad_args)
                with self.assertRaises(ValueError):
                    Focus(rdftype=bad_args[1], iri=bad_args[0])

        def test_triples(self):
            phee = Focus(BLERG.phee, BLERG.Blerg)
            phi = Focus(rdftype=BLERG.Blirg, iri=BLERG.phi)
            pho = Focus(rdftype=BLERG.Blorg, iri=BLERG.pho)
            phum = Focus(BLERG.phum, BLERG.Blurg)
            for f in {phee, phi, pho, phum}:
                assert (
                    set(f.as_triples())
                    == {(f.iri, rdflib.RDF.type, f.rdftype)}
                )
