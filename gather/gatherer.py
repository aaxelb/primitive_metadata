'''a "gatherer" is a function that gathers metadata about a focus.

gatherers register their interests via `@gatherer_decorator` (or `@gather.er`)


gather (verb)
    - to collect; normally separate things
        - to harvest food
        - to accumulate over time, to amass little by little
        - to congregate, or assemble
        - to grow gradually larger by accretion
    - to bring parts of a whole closer
    - to infer or conclude; to know from a different source.

    (gathered from https://en.wiktionary.org/wiki/gather )
'''
import datetime
import functools
import typing

import rdflib

from .focus import Focus


Gatherer = typing.Callable[[Focus], typing.Iterable[tuple]]
# module-private registry of gatherers by their iris of interest,
# built by the @gather.er decorator (via add_gatherer)
GathererRegistry = typing.Dict[             # outer dict maps
    typing.Optional[rdflib.URIRef],         # from focustype_iri (or None)
    typing.Dict[                            # to inner dict, which maps
        typing.Optional[rdflib.URIRef],     # from predicate_iri (or None)
        typing.Set[Gatherer],               # to a set of gatherers.
    ],
]
_gatherer_registry: GathererRegistry = {}


def gatherer_decorator(*predicate_iris, focustype_iris=None):
    """decorator to register metadata gatherer functions

    for example:
        ```
        from osf.metadata import gather

        @gather.er(DCTERMS.language, focustype_iris=[OSF.MyType])
        def gather_language(focus: gather.Focus):
            yield (DCTERMS.language, getattr(focus.dbmodel, 'language'))
        ```
    """
    def _decorator(gatherer: Gatherer):
        tidy_gatherer = _tidywrap_gatherer(gatherer)
        add_gatherer(tidy_gatherer, predicate_iris, focustype_iris)
        return tidy_gatherer
    return _decorator


def add_gatherer(gatherer, predicate_iris, focustype_iris):
    assert (predicate_iris or focustype_iris), (
        'cannot register gatherer without '
        'either predicate_iris or focustype_iris'
    )
    focustype_keys = focustype_iris or [None]
    predicate_keys = predicate_iris or [None]
    registry_keys = (
        (focustype, predicate)
        for focustype in focustype_keys
        for predicate in predicate_keys
    )
    for focustype, predicate in registry_keys:
        (
            _gatherer_registry
            .setdefault(focustype, {})
            .setdefault(predicate, set())
            .add(gatherer)
        )


def get_gatherers(focustype_iri, predicate_iris):
    gatherer_set = set()
    for focustype in (None, focustype_iri):
        for_focustype = _gatherer_registry.get(focustype, {})
        for predicate in (None, *predicate_iris):
            gatherer_set.update(for_focustype.get(predicate, ()))
    return gatherer_set


class QuietlySkippleTriple(Exception):
    pass


def _tidywrap_gatherer(inner_gatherer: Gatherer) -> Gatherer:
    @functools.wraps(inner_gatherer)
    def tidy_gatherer(focus: Focus):
        for triple in inner_gatherer(focus):
            try:
                yield tidy_gathered_triple(triple, focus)
            except QuietlySkippleTriple:
                pass
    return tidy_gatherer


def tidy_gathered_triple(triple, focus) -> tuple:
    """
    fill in the (perhaps partial) triple, given its focus,
    and convert some common python types to rdflib representation
    """
    if len(triple) == 2:  # allow omitting subject
        triple = (focus.iri, *triple)
    if len(triple) != 3:  # triple means three
        raise ValueError(f'_defocus: not triple enough (got {triple})')
    if any((v is None or v == '') for v in triple):
        raise QuietlySkippleTriple
    subj, pred, obj = triple
    if isinstance(obj, datetime.datetime):
        # no need for finer granularity than date (TODO: allow config)
        obj = obj.date()
    if isinstance(obj, datetime.date):
        # encode dates as iso8601-formatted string literals
        # (TODO: consider rdf datatype options; is xsd:dateTime good?)
        obj = obj.isoformat()
    if not isinstance(obj, (Focus, rdflib.term.Node)):
        # unless a Focus or already rdflib-erated, assume it's literal
        obj = rdflib.Literal(obj)
    return (subj, pred, obj)


if __debug__:
    import unittest
    from unittest import mock

    FOO = rdflib.Namespace('https://foo.example/')
    BAZ = rdflib.Namespace('https://baz.example/')

    @mock.patch.dict(_gatherer_registry, clear=True)
    class GathererRegistryTest(unittest.TestCase):
        def test_gatherer_registry(self):
            # register gatherer functions
            @gatherer_decorator(FOO.identifier)
            def gather_identifiers(focus):
                yield (FOO.identifier, 'fooid')

            @gatherer_decorator(focustype_iris=[FOO.Project])
            def gather_project_defaults(focus):
                yield (FOO.title, 'fooproject')

            @gatherer_decorator(focustype_iris=[BAZ.Preprint])
            def gather_preprint_defaults(focus):
                yield (FOO.title, 'foopreprint')
                yield (BAZ.title, 'foopreprint')

            @gatherer_decorator(
                BAZ.creator,
                focustype_iris=[FOO.Project, BAZ.Preprint],
            )
            def gather_preprint_or_project_creator(focus):
                yield (BAZ.creator, Focus(FOO['userguid'], BAZ.Agent))

            @gatherer_decorator(BAZ.creator, focustype_iris=[BAZ.Preprint])
            def gather_special_preprint_creator(focus):
                yield (BAZ.creator, Focus(BAZ['special'], BAZ.Agent))

            @gatherer_decorator(FOO.name, focustype_iris=[BAZ.Agent])
            def gather_agent_name(focus):
                yield (FOO.name, 'hey is me')

            # check the registry is correct
            assert _gatherer_registry == {
                None: {
                    FOO.identifier: {gather_identifiers},
                },
                FOO.Project: {
                    None: {gather_project_defaults},
                    BAZ.creator: {
                        gather_preprint_or_project_creator,
                    },
                },
                BAZ.Preprint: {
                    None: {gather_preprint_defaults},
                    BAZ.creator: {
                        gather_preprint_or_project_creator,
                        gather_special_preprint_creator,
                    },
                },
                BAZ.Agent: {
                    FOO.name: {gather_agent_name},
                },
            }

            # check get_gatherers gets good gatherers
            assert get_gatherers(FOO.Anything, [FOO.unknown]) == set()
            assert get_gatherers(FOO.Anything, [FOO.identifier]) == {
                gather_identifiers,
            }
            assert get_gatherers(FOO.Project, [BAZ.creator]) == {
                gather_project_defaults,
                gather_preprint_or_project_creator,
            }
            assert get_gatherers(BAZ.Preprint, [BAZ.creator]) == {
                gather_preprint_defaults,
                gather_preprint_or_project_creator,
                gather_special_preprint_creator,
            }
            assert get_gatherers(
                BAZ.Agent,
                [FOO.name, FOO.identifier, FOO.unknown],
            ) == {
                gather_agent_name,
                gather_identifiers,
            }

    class TidyTripleTest(unittest.TestCase):
        def setUp(self):
            self.focus = Focus(FOO.ttt, FOO.Test)

        def test_good_triples(self):
            good_cases = (
                {
                    'in': (FOO.a, 'wha'),
                    'out': (FOO.ttt, FOO.a, rdflib.Literal('wha')),
                },
                # TODO: more
            )
            for test_case in good_cases:
                actual_out = tidy_gathered_triple(
                    test_case['in'],
                    self.focus,
                )
                self.assertEqual(actual_out, test_case['out'])

        def test_skippled_triples(self):
            skip_cases = (
                (None, None),
                (FOO.ba, ''),
                (FOO.ba, None),
                (FOO.a, FOO.b, None),
                (FOO.a, FOO.b, ''),
            )
            for test_case_triple in skip_cases:
                with self.assertRaises(QuietlySkippleTriple):
                    tidy_gathered_triple(
                        test_case_triple,
                        self.focus,
                    )

        def test_bad_triples(self):
            bad_cases = (
                (),
                (FOO.a,),
                (FOO.a, FOO.b, FOO.c, FOO.d),
            )
            for test_case_triple in bad_cases:
                with self.assertRaises(ValueError):
                    tidy_gathered_triple(
                        test_case_triple,
                        self.focus,
                    )

    if __name__ == '__main__':
        unittest.main()
