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
    focus: Focus                     # the thing to gather metadata about;
    gathered_metadata: rdflib.Graph  # a heap of metadata gathered so far;
    _gathertasks_done: set           # memory of gather-work already done,
    _focus_set_by_iri: dict          # of items we could learn more about.

    # # # # # # # # # # # #
    # BEGIN public methods

    def __init__(self, focus: Focus):
        assert isinstance(focus, Focus)
        self.focus = focus
        self.reset()  # start with an empty basket (except the focus itself)

    def reset(self):
        self.gathered_metadata = rdflib.Graph()
        self._gathertasks_done = set()
        self._focus_set_by_iri = {}
        self._add_known_focus(self.focus)

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
        self._gather_by_predicate_map(self.focus, predicate_map)

    def predicate_set(self, *, focus=None):
        focus_iri = focus or self.focus.iri
        yield from self.gathered_metadata.predicates(focus_iri, unique=True)

    def __getitem__(self, slice_or_arg) -> typing.Iterable[rdflib.term.Node]:
        '''convenience for getting and gathering values

        always returns an iterable (if no values found, an empty iterable)

        basket[focus:path] -> objects that complete rdf triples
        basket[path] -> same, with self.focus as implicit focus

        automatically invokes gatherers, if any are registered for the
        given focus type and path predicates
        '''
        if isinstance(slice_or_arg, slice):
            focus_iri = slice_or_arg.start
            path = slice_or_arg.stop
            # TODO: use slice_or_arg.step, maybe to constrain "expected type"?
        else:
            focus_iri = self.focus.iri
            path = slice_or_arg
        self._maybe_gather_for_path(focus_iri, path)
        yield from self.gathered_metadata.objects(
            subject=focus_iri,
            predicate=path,
            unique=True,
        )
        # return a descriptive message for StopIteration
        return f'{self}: no more objects for focus_iri=<{focus_iri}> path={path}'

    def __str__(self):
        return f'{self.__class__.__qualname__}({self.focus})'

    def __len__(self):
        # number of gathered triples
        return len(self.gathered_metadata)

    def __contains__(self, triple):
        # is the triple in the rdf graph? (also prevent infinite loop
        # from `x in basket` trying __getitem__ with every integer)
        return (triple in self.gathered_metadata)

    # END public methods
    # # # # # # # # # # #

    def _maybe_gather_for_path(self, focus, path):
        if isinstance(path, str):
            self._maybe_gather_for_predicate_map(focus, [path])
        elif isinstance(path, rdflib.paths.AlternativePath):
            self._maybe_gather_for_predicate_map(focus, set(path.args))
        elif isinstance(path, rdflib.paths.SequencePath):
            predicate_map = current_map = {}
            for subpath in path.args:
                current_map[subpath] = current_map = {}
            self._maybe_gather_for_predicate_map(focus, predicate_map)
        else:
            raise ValueError(
                f'unsupported path type {type(path)} (path={path})',
            )

    def _maybe_gather_for_predicate_map(self, iri_or_focus, predicate_map):
        if isinstance(iri_or_focus, Focus):
            # with an actual Focus, always try to gather more
            self._gather_by_predicate_map(iri_or_focus, predicate_map)
        elif isinstance(iri_or_focus, rdflib.URIRef):
            # with an IRI, gather more only if it matches a known Focus
            for focus in self._focus_set_by_iri.get(iri_or_focus, ()):
                self._gather_by_predicate_map(focus, predicate_map)
        elif isinstance(iri_or_focus, rdflib.BNode):
            pass  # never gather more about blank nodes
        else:
            raise ValueError(
                'expected `iri_or_focus` to be Focus, URIRef, or BNode'
                f' (got {iri_or_focus})'
            )

    def _gather_by_predicate_map(self, focus, predicate_map):
        assert isinstance(focus, Focus)
        if not isinstance(predicate_map, dict):
            # allow iterable of predicates with no deeper paths
            predicate_map = {
                predicate_iri: None
                for predicate_iri in predicate_map
            }
        for gatherer in get_gatherers(focus.rdftype, predicate_map.keys()):
            self._maybe_do_a_gathertask(gatherer, focus)
        for predicate_iri, next_steps in predicate_map.items():
            if next_steps:
                next_subjects = (
                    self.gathered_metadata
                    .objects(focus.iri, predicate_iri)
                )
                for next_subject_iri in next_subjects:
                    self._maybe_gather_for_predicate_map(
                        next_subject_iri,
                        next_steps,
                    )

    def _maybe_do_a_gathertask(self, gatherer: Gatherer, focus: Focus):
        '''invoke gatherer with the given focus

        (but only if it hasn't already been done)
        '''
        if (gatherer, focus) not in self._gathertasks_done:
            self._gathertasks_done.add((gatherer, focus))
            self._do_a_gathertask(gatherer, focus)

    def _do_a_gathertask(self, gatherer, focus):
        for (subj, pred, obj) in gatherer(focus):
            if isinstance(obj, Focus):
                self.gathered_metadata.add((subj, pred, obj.iri))
                self._add_known_focus(obj)
            else:
                self.gathered_metadata.add((subj, pred, obj))

    def _add_known_focus(self, focus: Focus):
        (
            self._focus_set_by_iri
            .setdefault(focus.iri, set())
            .add(focus)
        )
        for triple in focus.as_rdf_tripleset():
            self.gathered_metadata.add(triple)


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
            related_focus = Focus(BLARG.borked, BLARG.TypeBork)
            # define some mock gatherer functions
            mock_zork = unittest.mock.Mock(return_value=(
                (BLARG.item, BLARG.zork, BLARG.zorked),
            ))
            mock_bork = unittest.mock.Mock(return_value=(
                (BLARG.item, BLARG.bork, related_focus),
            ))
            mock_hork = unittest.mock.Mock(return_value=(
                (BLARG.item, BLARG.hork, BLARG.horked),
            ))
            mock_lork = unittest.mock.Mock(return_value=(
                (BLARG.borked, BLARG.lork, BLARG.borklorked),
            ))
            # register the mock gatherer functions
            gatherer_decorator(BLARG.zork)(mock_zork)
            gatherer_decorator(BLARG.bork)(mock_bork)
            gatherer_decorator(
                BLARG.lork,
                focustype_iris=[BLARG.TypeBork],
            )(mock_lork)
            gatherer_decorator(BLARG.hork)(mock_hork)
            # check basket organizes gatherers as expected
            basket = Basket(focus)
            self.assertEqual(basket.focus, focus)
            self.assertTrue(isinstance(basket.gathered_metadata, rdflib.Graph))
            # at start, no gatherers run
            self.assertFalse(mock_zork.called)
            self.assertFalse(mock_bork.called)
            self.assertFalse(mock_lork.called)
            self.assertFalse(mock_hork.called)
            self.assertEqual(len(basket), 1)
            self.assertEqual(len(basket._gathertasks_done), 0)
            # zork (should gather)
            self.assertEqual(
                set(basket[BLARG.zork]),
                {BLARG.zorked},
            )
            self.assertEqual(mock_zork.call_count, 1)
            self.assertFalse(mock_bork.called)
            self.assertFalse(mock_lork.called)
            self.assertFalse(mock_hork.called)
            self.assertEqual(len(basket), 2)
            self.assertEqual(len(basket._gathertasks_done), 1)
            # bork (should gather)
            self.assertEqual(
                set(basket[BLARG.bork]),
                {BLARG.borked},
            )
            self.assertEqual(mock_zork.call_count, 1)
            self.assertEqual(mock_bork.call_count, 1)
            self.assertFalse(mock_lork.called)
            self.assertFalse(mock_hork.called)
            self.assertEqual(len(basket), 4)
            self.assertEqual(len(basket._gathertasks_done), 2)
            # borklork (should gather lork, but not bork)
            self.assertEqual(
                set(basket[BLARG.bork / BLARG.lork]),
                {BLARG.borklorked},
            )
            self.assertEqual(mock_zork.call_count, 1)
            self.assertEqual(mock_bork.call_count, 1)
            self.assertEqual(mock_lork.call_count, 1)
            self.assertFalse(mock_hork.called)
            self.assertEqual(len(basket), 5)
            self.assertEqual(len(basket._gathertasks_done), 3)
            # bork again (should not regather)
            assert set(basket[BLARG.bork]) == {BLARG.borked}
            self.assertEqual(mock_zork.call_count, 1)
            self.assertEqual(mock_bork.call_count, 1)
            self.assertEqual(mock_lork.call_count, 1)
            self.assertFalse(mock_hork.called)
            self.assertEqual(len(basket), 5)
            self.assertEqual(len(basket._gathertasks_done), 3)
            # hork (should gather)
            assert set(basket[BLARG.hork]) == {BLARG.horked}
            self.assertEqual(mock_zork.call_count, 1)
            self.assertEqual(mock_bork.call_count, 1)
            self.assertEqual(mock_lork.call_count, 1)
            self.assertEqual(mock_hork.call_count, 1)
            self.assertEqual(len(basket), 6)
            self.assertEqual(len(basket._gathertasks_done), 4)
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
            self.assertEqual(len(basket), 1)
            self.assertEqual(len(basket._gathertasks_done), 0)
