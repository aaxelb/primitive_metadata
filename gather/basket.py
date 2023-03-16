'''a Basket is a focal point for gatherer organization


basket (noun)
    - a lightweight container, generally round,
      open at the top, and tapering toward the bottom
    - a set or collection of intangible things.

    (gathered from https://en.wiktionary.org/wiki/basket )
'''
import typing

import rdflib

from .focus import Focus
from .gatherer import gatherer_decorator, get_gatherers, Gatherer


class Basket:
    focus: Focus                     # the thing to gather metadata from.
    gathered_metadata: rdflib.Graph  # heap of metadata already gathered.
    _gathertasks_done: set           # memory of gatherings already done.

    # # # # # # # # # # # #
    # BEGIN public methods

    def __init__(self, focus: Focus):
        assert isinstance(focus, Focus)
        self.focus = focus
        self.reset()  # start with an empty basket

    def reset(self):
        self.gathered_metadata = rdflib.Graph()
        self._gathertasks_done = set()

    def pls_gather(self, predicate_map):  # TODO: async
        '''go gatherers, go!

        @predicate_map: dict with rdflib.URIRef keys

        use the predicate_map to get all relevant gatherers,
        ask them to gather metadata about this basket's focus,
        and keep the gathered metadata in this basket.

        for example:
        ```
        basket.pls_gather({
            DCTERMS.title: None,            # request the focus's titles
            DCTERMS.relation: {             # request the focus's relations
                DCTERMS.title: None,        #   ...and related items' titles
                DCTERMS.creator: {          #   ...and related items' creators
                    FOAF.name: None,    #       ...and those creators' names
                },
            },
        })
        '''
        for triple in self._gather_by_predicate_map(predicate_map, self.focus):
            self.gathered_metadata.add(triple)

    def predicate_set(self, *, focus=None):
        focus_iri = focus or self.focus.iri
        yield from self.gathered_metadata.predicates(focus_iri, unique=True)

    def __getitem__(self, slice_or_arg) -> typing.Iterable[rdflib.term.Node]:
        '''convenience wrapper for rdflib.Graph.objects(unique=True)

        basket[subject:predicate] -> objects that complete the rdf triple
        basket[predicate] -> same, with self.focus as implicit subject

        if you need more, access the rdflib.Graph at
        basket.gathered_metadata directly (or improve this __getitem__?)
        '''
        if isinstance(slice_or_arg, slice):
            focus_iri = slice_or_arg.start
            predicate_iri = slice_or_arg.stop
            # TODO: use slice_or_arg.step, maybe to constrain "expected type"?
        else:
            focus_iri = self.focus.iri
            predicate_iri = slice_or_arg
        yield from self.gathered_metadata.objects(
            subject=focus_iri,
            predicate=predicate_iri,
            unique=True,
        )

    def __len__(self):
        # number of gathered triples
        return len(self.gathered_metadata)

    # END public methods
    # # # # # # # # # # #

    def _gather_by_predicate_map(self, predicate_map, focus):
        yield (focus.iri, rdflib.RDF.type, focus.rdftype)
        if not isinstance(predicate_map, dict):
            # allow iterable of predicates with no deeper paths
            predicate_map = {
                predicate_iri: None
                for predicate_iri in predicate_map
            }
        for gatherer in get_gatherers(focus.rdftype, predicate_map.keys()):
            for (subj, pred, obj) in self._do_a_gathertask(gatherer, focus):
                if isinstance(obj, Focus):
                    yield (subj, pred, obj.iri)
                    if subj == focus.iri:
                        next_steps = predicate_map.get(pred, None)
                        if next_steps:
                            yield from self._gather_by_predicate_map(
                                predicate_map=next_steps,
                                focus=obj,
                            )
                else:
                    yield (subj, pred, obj)

    def _do_a_gathertask(self, gatherer: Gatherer, focus: Focus):
        '''invoke gatherer with the given focus

        (but only if it hasn't already been done)
        '''
        if (gatherer, focus) not in self._gathertasks_done:
            self._gathertasks_done.add((gatherer, focus))  # eager
            yield from gatherer(focus)


if __debug__:
    import unittest

    BLARG = rdflib.Namespace('https://blarg.example/blarg/')

    class BasicBasketTest(unittest.TestCase):

        def test_badbasket(self):
            # test non-focus AssertionError
            with self.assertRaises(AssertionError):
                Basket(None)
            with self.assertRaises(AssertionError):
                Basket('http://hello.example/')

        def test_goodbasket(self):
            focus = Focus(BLARG.item, BLARG.Type)
            # define some mock gatherer functions
            mock_zork = unittest.mock.Mock(return_value=(
                (BLARG.item, BLARG.zork, BLARG.zorked),
            ))
            mock_bork = unittest.mock.Mock(return_value=(
                (BLARG.item, BLARG.bork, BLARG.borked),
                (BLARG.borked, BLARG.lork, BLARG.borklorked),
            ))
            mock_hork = unittest.mock.Mock(return_value=(
                (BLARG.item, BLARG.hork, BLARG.horked),
            ))
            # register the mock gatherer functions
            gatherer_decorator(BLARG.zork)(mock_zork)
            gatherer_decorator(BLARG.bork)(mock_bork)
            gatherer_decorator(BLARG.hork)(mock_hork)
            # check basket organizes gatherers as expected
            basket = Basket(focus)
            self.assertEqual(basket.focus, focus)
            self.assertTrue(isinstance(basket.gathered_metadata, rdflib.Graph))
            self.assertEqual(len(basket), 0)
            self.assertEqual(len(basket._gathertasks_done), 0)
            # no repeat gathertasks:
            mock_zork.assert_not_called()
            mock_bork.assert_not_called()
            mock_hork.assert_not_called()
            basket.pls_gather({BLARG.zork})
            mock_zork.assert_called_once()
            mock_bork.assert_not_called()
            mock_hork.assert_not_called()
            self.assertEqual(len(basket), 2)
            self.assertEqual(len(basket._gathertasks_done), 1)
            basket.pls_gather({BLARG.zork, BLARG.bork})
            mock_zork.assert_called_once()
            mock_bork.assert_called_once()
            mock_hork.assert_not_called()
            self.assertEqual(len(basket), 4)
            self.assertEqual(len(basket._gathertasks_done), 2)
            basket.pls_gather({BLARG.bork})
            mock_zork.assert_called_once()
            mock_bork.assert_called_once()
            mock_hork.assert_not_called()
            self.assertEqual(len(basket), 4)
            self.assertEqual(len(basket._gathertasks_done), 2)
            basket.pls_gather({BLARG.bork, BLARG.zork, BLARG.hork})
            mock_zork.assert_called_once()
            mock_bork.assert_called_once()
            mock_hork.assert_called_once()
            self.assertEqual(len(basket), 5)
            self.assertEqual(len(basket._gathertasks_done), 3)
            # __getitem__:
            self.assertEqual(set(basket[BLARG.zork]), {BLARG.zorked})
            self.assertEqual(set(basket[BLARG.bork]), {BLARG.borked})
            self.assertEqual(set(basket[BLARG.hork]), {BLARG.horked})
            self.assertEqual(set(basket[BLARG.somethin_else]), set())
            # __getitem__ path:
            self.assertEqual(
                set(basket[BLARG.bork / BLARG.lork]),
                {BLARG.borklorked},
            )
            # __getitem__ slice:
            self.assertEqual(
                set(basket[BLARG.item:BLARG.zork]),
                {BLARG.zorked},
            )
            self.assertEqual(set(basket[BLARG.item:BLARG.lork]), set())
            self.assertEqual(set(basket[BLARG.borked:BLARG.bork]), set())
            self.assertEqual(
                set(basket[BLARG.borked:BLARG.lork]),
                {BLARG.borklorked},
            )
            # reset:
            basket.reset()
            self.assertEqual(len(basket), 0)
            self.assertEqual(len(basket), 0)
            self.assertEqual(len(basket._gathertasks_done), 0)

    if __name__ == '__main__':
        unittest.main()
