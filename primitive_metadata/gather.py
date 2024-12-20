'''gather.py: for gathering metadata as rdf triples

gather (verb)
    - to collect; normally separate things
        - to harvest food
        - to accumulate over time, to amass little by little
        - to congregate, or assemble
        - to grow gradually larger by accretion
    - to bring parts of a whole closer
    - to infer or conclude; to know from a different source.
(gathered from https://en.wiktionary.org/wiki/gather )

mindset metaphor:
1. organize a gathering
2. ask a question
3. leaf a record
'''

from __future__ import annotations
import dataclasses
import functools
import itertools
import types
from typing import Union, Iterable, Iterator, Any, Callable, Optional

from primitive_metadata import primitive_rdf as rdf
from primitive_metadata.namespaces import RDF, OWL, RDFS

__all__ = (
    'GatheringNorms',
    'GatheringOrganizer',
    'Gathering',
)

if __debug__:  # tests under __debug__ thru-out
    import unittest  # TODO: doctest


@dataclasses.dataclass(frozen=True)
class Focus:
    iris: frozenset[str]  # synonymous persistent identifiers in iri form
    type_iris: frozenset[str]
    # may override default gathering_kwargs from the Gathering:
    gatherer_kwargset: frozenset[tuple[str, Any]]

    @classmethod
    def new(cls, iris=None, type_iris=None, gatherer_kwargset=None):
        '''convenience wrapper for Focus
        '''
        if isinstance(gatherer_kwargset, frozenset):
            _gatherer_kwargset = gatherer_kwargset
        elif isinstance(gatherer_kwargset, dict):
            _gatherer_kwargset = frozenset(
                (_kwargname, _kwargvalue)
                for _kwargname, _kwargvalue in gatherer_kwargset.items()
            )
        elif gatherer_kwargset is None:
            _gatherer_kwargset = frozenset()
        else:
            raise GatherException(
                label='focus-gatherer-kwargs',
                comment=(
                    'gatherer_kwargset should be frozenset, dict, or None'
                    f' (got {gatherer_kwargset})'
                ),
            )
        return cls(
            iris=rdf.ensure_frozenset(iris),
            type_iris=rdf.ensure_frozenset(type_iris),
            gatherer_kwargset=_gatherer_kwargset,
        )

    def single_iri(self) -> str:
        return rdf.choose_one_iri(self.iris)

    def as_rdf_tripleset(self) -> Iterator[rdf.RdfTriple]:
        _iri = self.single_iri()
        for _type_iri in self.type_iris:
            yield (_iri, RDF.type, _type_iri)
        for _same_iri in self.iris:
            if _same_iri != _iri:
                yield (_iri, OWL.sameAs, _same_iri)
        # TODO: gatherer_kwargset?


GathererYield = Union[
    rdf.RdfTriple,  # using the rdf triple as basic unit of information
    rdf.RdfTwople,  # may omit subject (assumed iri of the given focus)
    # may yield a Focus in the subject or object position, will get
    # triples from Focus.iris and Focus.type_iris, and may initiate
    # other gatherers' gathering.
    tuple[  # triples with any `None` values are silently discarded
        Union[str, Focus, None],
        Union[str, None],
        Union[rdf.RdfObject, Focus, None],
    ],
    tuple[
        Union[str, None],
        Union[rdf.RdfObject, Focus, None],
    ],
]

Gatherer = Callable[[Focus], Iterator[GathererYield]]

# when decorated, the yield is tidied into triples
TripleGatherer = Callable[
    [Focus],
    Iterator[rdf.RdfTriple],
]


###
# to start gathering information:
# - declare a `GatheringNorms` with pre-defined vocabularies, names, etc.
# - declare a `GatheringOrganizer` for each implementation of given norms
# - write `Gatherer` functions that yield triples or twoples, given Focus


@dataclasses.dataclass(frozen=True)
class GatheringNorms:
    namestory: rdf.Namestory
    focustype_iris: frozenset[str]
    param_iris: frozenset[str]
    thesaurus: rdf.RdfTripleDictionary

    @classmethod
    def new(
        cls,
        namestory: rdf.Namestory,
        focustype_iris: Iterable[str],
        param_iris: Iterable[str] = (),
        thesaurus: Optional[rdf.RdfTripleDictionary] = None,
    ) -> GatheringNorms:
        '''more flexible alternate constructor for GatheringNorms
        '''
        return cls(
            namestory,
            focustype_iris=rdf.ensure_frozenset(focustype_iris),
            param_iris=rdf.ensure_frozenset(param_iris),
            thesaurus=(thesaurus or {}),
        )

    def validate_param_iris(self, param_iris: Iterable[str]):
        _all_iris_are_known = self.param_iris.issuperset(param_iris)
        if not _all_iris_are_known:
            raise GatherException(
                label='invalid-param-iris',
                comment=(
                    f'expected any of {set(self.param_iris)},'
                    f' got {set(param_iris)}'
                )
            )


@dataclasses.dataclass
class GatheringOrganizer:
    namestory: rdf.Namestory
    norms: GatheringNorms
    gatherer_params: dict[str, str]  # {keyword: param_iri}
    default_gatherer_kwargs: dict[str, Any] = dataclasses.field(
        default_factory=dict,
    )
    signup: _GathererSignup = dataclasses.field(
        default_factory=lambda: _GathererSignup(),
    )

    def __post_init__(self):
        self.norms.validate_param_iris(self.gatherer_params.values())

    def new_gathering(self, gatherer_kwargs: dict | None = None) -> Gathering:
        return Gathering(
            norms=self.norms,
            organizer=self,
            gatherer_kwargs=(gatherer_kwargs or {}),
        )

    def gatherer(self, *predicate_iris, focustype_iris=None, cache_bound=None):
        '''decorate gatherer functions with their iris of interest
        '''
        def _gatherer_decorator(gatherer_fn: Gatherer) -> TripleGatherer:
            _triple_gatherer = self.__make_triple_gatherer(gatherer_fn)
            self.signup.add_gatherer(
                _triple_gatherer,
                predicate_iris=predicate_iris,
                focustype_iris=(focustype_iris or ()),
                cache_bound=cache_bound,
            )
            return _triple_gatherer
        return _gatherer_decorator

    def validate_gatherer_kwargs(self, gatherer_kwargs):
        _recognized_keywords = set(self.gatherer_params.keys())
        _unrecognized_kwargs = {
            _keyword: _value
            for _keyword, _value in gatherer_kwargs.items()
            if _keyword not in _recognized_keywords
        }
        if _unrecognized_kwargs:
            raise GatherException(
                label='unrecognized-gatherer-kwargs',
                comment=(
                    f'expected any keywords from {_recognized_keywords},'
                    f' got unrecognized {_unrecognized_kwargs}'
                ),
            )

    def __make_triple_gatherer(self, gatherer_fn: Gatherer) -> TripleGatherer:
        @functools.wraps(gatherer_fn)
        def _triple_gatherer(focus: Focus, **gatherer_kwargs):
            self.validate_gatherer_kwargs(gatherer_kwargs)
            for _triple_or_twople in gatherer_fn(focus, **gatherer_kwargs):
                if len(_triple_or_twople) == 3:
                    (_subj, _pred, _obj) = _triple_or_twople
                elif len(_triple_or_twople) == 2:
                    _subj = focus.single_iri()
                    (_pred, _obj) = _triple_or_twople
                else:
                    raise ValueError(
                        f'expected triple or twople (got {_triple_or_twople})',
                    )
                triple = (_subj, _pred, _obj)
                if None not in triple:
                    yield triple
        return _triple_gatherer


@dataclasses.dataclass
class Gathering:
    norms: GatheringNorms
    organizer: GatheringOrganizer
    gatherer_kwargs: dict
    cache: _GatherCache = dataclasses.field(
        default_factory=lambda: _GatherCache(),
    )

    def ask(
        self, pathset: rdf.MessyPathset, *,
        focus: Union[str, Focus],
    ):
        _focus = (
            self.cache.get_focus_by_iri(focus)
            if isinstance(focus, str)
            else focus
        )
        _tidy_pathset = rdf.tidy_pathset(pathset)
        self.__gathercache_by_pathset(_tidy_pathset, focus=_focus)
        return self.cache.peek(_tidy_pathset, focus=_focus)

    def ask_exhaustively(
        self, predicate_iri: str, *,
        focus: Focus,
    ) -> Iterator[tuple[rdf.RdfObject, rdf.RdfGraph]]:
        _gatherers = self.organizer.signup.get_gatherers(
            focus,
            [predicate_iri],
        )
        for gatherer in _gatherers:
            _gatherer_kwargs = self.__gatherer_kwargs(gatherer, focus)
            _triples = gatherer(focus, **_gatherer_kwargs)
            _incidentals = rdf.RdfGraph()
            _triple = next(_triples, None)
            while _triple is not None:
                _incidentals.add(_triple)
                (_subj, _pred, _obj) = _triple
                if (_subj in focus.iris) and (_pred == predicate_iri):
                    yield _obj, _incidentals
                    _incidentals = rdf.RdfGraph()  # reset
                _triple = next(_triples, None)

    def ask_all_about(self, focus: Union[str, Focus]):
        _asked_focus = (
            self.cache.get_focus_by_iri(focus)
            if isinstance(focus, str)
            else focus
        )
        _predicate_iris = self.organizer.signup.all_predicate_iris()
        _focus_visited = set()
        _focus_to_visit = {_asked_focus}
        while _focus_to_visit:
            _focus = _focus_to_visit.pop()
            if _focus not in _focus_visited:
                _focus_visited.add(_focus)
                self.ask(_predicate_iris, focus=_focus)
                _focus_to_visit.update(self.cache.focus_set - _focus_visited)

    def leaf_a_record(self):
        return types.MappingProxyType(self.cache.gathered.tripledict)

    def __gathercache_by_pathset(
        self, pathset: rdf.TidyPathset, *, focus: Focus
    ) -> None:
        '''gather information into the cache (unless already gathered)
        '''
        self.__gathercache_predicate_iris(focus, set(pathset.keys()))
        for _pred, _next_pathset in pathset.items():
            if _next_pathset:
                for _obj in self.cache.peek(_pred, focus=focus):
                    # indirect recursion:
                    self.__gathercache_thru_object(_next_pathset, _obj)

    def __gathercache_thru_object(
        self,
        pathset: rdf.TidyPathset,
        obj: rdf.RdfObject,
    ) -> None:
        if isinstance(obj, str):  # iri
            try:
                _next_focus = self.cache.get_focus_by_iri(obj)
            except GatherException:
                return  # not a usable focus
            else:
                self.__gathercache_by_pathset(pathset, focus=_next_focus)
        elif isinstance(obj, frozenset):  # blank node
            if rdf.is_container(obj):  # pass thru rdf containers transparently
                for _container_obj in rdf.container_objects(obj):
                    self.__gathercache_thru_object(
                        pathset, _container_obj
                    )
            else:  # not a container
                for _pred, _obj in obj:
                    _next_pathset = pathset.get(_pred)
                    if _next_pathset:
                        self.__gathercache_thru_object(
                            _next_pathset, _obj
                        )
        # otherwise, ignore

    def __gathercache_predicate_iris(
        self,
        focus: Focus,
        predicate_iris: set[str],
    ) -> None:
        self.cache.add_focus(focus)
        _signup = self.organizer.signup
        for gatherer in _signup.get_gatherers(focus, predicate_iris):
            if self.cache.already_gathered(gatherer, focus):
                continue
            _bound = _signup._cache_bounds.get(gatherer)
            _triples = (
                self.__do_unbounded_gather(gatherer, focus)
                if _bound is None
                else self.__do_bounded_gather(
                    gatherer,
                    focus,
                    predicate_iris,
                    _bound,
                )
            )
            for _triple in _triples:
                self.cache.add_triple(_triple)

    def __do_unbounded_gather(
        self, gatherer, focus
    ) -> Iterator[rdf.RdfTriple]:
        _gatherer_kwargs = self.__gatherer_kwargs(gatherer, focus)
        for triple in gatherer(focus, **_gatherer_kwargs):
            yield triple

    def __do_bounded_gather(
        self,
        gatherer: TripleGatherer,
        focus: Focus,
        predicate_iris: set[str],
        bound: int,
    ) -> Iterator[rdf.RdfTriple]:
        _gatherer_kwargs = self.__gatherer_kwargs(gatherer, focus)
        _triples = gatherer(focus, **_gatherer_kwargs)
        for _ in range(bound):
            for (_subj, _pred, _obj) in _triples:
                yield _subj, _pred, _obj
                if (_subj in focus.iris) and (_pred in predicate_iris):
                    break

    def __gatherer_kwargs(self, gatherer, focus) -> dict:
        return {
            **self.organizer.default_gatherer_kwargs,
            **self.gatherer_kwargs,
            **dict(focus.gatherer_kwargset),
        }


class _GatherCache:
    gathers_done: set[tuple[Gatherer, Focus]]
    focus_set: set[Focus]
    gathered: rdf.RdfGraph

    def __init__(self):
        self.gathers_done = set()
        self.focus_set = set()
        self.gathered = rdf.RdfGraph()

    def add_focus(self, focus: Focus):
        if focus not in self.focus_set:
            self.focus_set.add(focus)
            for triple in focus.as_rdf_tripleset():
                self.gathered.add(triple)

    def get_focus_by_iri(self, iri: str):
        _type_iris = frozenset(self.gathered.q(iri, RDF.type))
        if not _type_iris:
            raise GatherException(
                label='cannot-get-focus',
                comment=f'found no type for "{iri}"',
            )
        _same_iris = self.gathered.q(iri, OWL.sameAs)
        _iris = {iri, *_same_iris}
        _focus = Focus.new(iris=_iris, type_iris=_type_iris)
        self.add_focus(_focus)
        return _focus

    def add_triple(self, triple: rdf.RdfTriple):
        (_subj, _pred, _obj) = triple
        _subj = self.__maybe_unwrap_focus(_subj)
        _obj = self.__maybe_unwrap_focus(_obj)
        self.gathered.add((_subj, _pred, _obj))

    def peek(
        self, pathset: rdf.MessyPathset, *,
        focus: Union[Focus, str],
    ) -> Iterator[rdf.RdfObject]:
        '''peek: yield objects the given pathset leads to, from the given focus
        '''
        if isinstance(focus, Focus):
            _focus_iri = focus.single_iri()
        elif isinstance(focus, str):
            _focus_iri = focus
        else:
            raise ValueError(
                f'expected focus to be str or Focus or None (got {focus})'
            )
        yield from self.gathered.q(_focus_iri, pathset)

    def already_gathered(
        self, gatherer: Gatherer, focus: Focus, *,
        pls_mark_done=True,
    ) -> bool:
        gatherkey = (gatherer, focus)
        is_done = (gatherkey in self.gathers_done)
        if pls_mark_done and not is_done:
            self.gathers_done.add(gatherkey)
        return is_done

    def __maybe_unwrap_focus(
        self,
        maybefocus: Union[Focus, rdf.RdfObject],
    ):
        if isinstance(maybefocus, Focus):
            self.add_focus(maybefocus)
            return maybefocus.single_iri()
        return maybefocus


if __debug__:
    class TestGatherCache(unittest.TestCase):
        pass  # TODO


@dataclasses.dataclass
class _GathererSignup:
    _by_predicate: dict[str, set[TripleGatherer]] = dataclasses.field(
        default_factory=dict,
    )
    _by_focustype: dict[str, set[TripleGatherer]] = dataclasses.field(
        default_factory=dict,
    )
    _for_any_predicate: set[TripleGatherer] = dataclasses.field(
        default_factory=set,
    )
    _for_any_focustype: set[TripleGatherer] = dataclasses.field(
        default_factory=set,
    )
    _cache_bounds: dict[TripleGatherer, int] = dataclasses.field(
        default_factory=dict,
    )

    def add_gatherer(
        self, gatherer: TripleGatherer, *,
        predicate_iris,
        focustype_iris,
        cache_bound: int | None = None,
    ):
        if cache_bound is not None:
            self._cache_bounds[gatherer] = cache_bound
        if predicate_iris:
            for iri in predicate_iris:
                (
                    self._by_predicate
                    .setdefault(iri, set())
                    .add(gatherer)
                )
        else:
            self._for_any_predicate.add(gatherer)
        if focustype_iris:
            for iri in focustype_iris:
                (
                    self._by_focustype
                    .setdefault(iri, set())
                    .add(gatherer)
                )
        else:
            self._for_any_focustype.add(gatherer)
        return gatherer

    def all_predicate_iris(self):
        return frozenset(self._by_predicate.keys())

    def get_gatherers(
        self,
        focus: Focus,
        predicate_iris: Iterable[str],
    ) -> set[TripleGatherer]:
        gatherer_set = None
        for iris, gatherers_by_iri, gatherers_for_any_iri in (
            (predicate_iris, self._by_predicate, self._for_any_predicate),
            (focus.type_iris, self._by_focustype, self._for_any_focustype),
        ):
            gatherer_iter = itertools.chain(
                *(
                    gatherers_by_iri.get(iri, frozenset())
                    for iri in iris
                ),
                gatherers_for_any_iri,
            )
            if gatherer_set is None:
                gatherer_set = set(gatherer_iter)
            else:
                gatherer_set.intersection_update(gatherer_iter)
        return gatherer_set or set()


if __debug__:
    BLARG = rdf.IriNamespace('https://blarg.example/')
    _a_blargfocus = Focus.new(
        BLARG.asome,
        type_iris=BLARG.SomeType,
    )
    _nother_blargfocus = Focus.new(
        BLARG.another,
        type_iris=BLARG.AnotherType,
    )
    BlargAtheringNorms = GatheringNorms.new(
        namestory=(
            rdf.literal('blarg', language=BLARG.myLanguage),
            rdf.literal('blargl blarg', language=BLARG.myLanguage),
            rdf.literal(
                'a gathering called "blarg"',
                language='en-US',
            ),
        ),
        thesaurus={
            BLARG.greeting: {
                RDF.type: {RDFS.Property},
            },
            BLARG.yoo: {
            },
        },
        focustype_iris={
            BLARG.SomeType,
            BLARG.AnotherType,
        },
        param_iris={BLARG.hello},
    )

    BlorgArganizer = GatheringOrganizer(
        namestory=(
            rdf.literal('blarg this way', language=BLARG.myLanguage),
        ),
        norms=BlargAtheringNorms,
        gatherer_params={
            'hello': BLARG.hello,
        },
    )

    @BlorgArganizer.gatherer(BLARG.greeting)
    def blargather_greeting(focus: Focus, *, hello):
        yield (BLARG.greeting, rdf.literal(
            'kia ora',
            language='mi',
        ))
        yield (BLARG.greeting, rdf.literal(
            'hola',
            language='es',
        ))
        yield (BLARG.greeting, rdf.literal(
            'hello',
            language='en',
        ))
        yield (BLARG.greeting, rdf.literal(
            hello,
            language=BLARG.Dunno,
        ))

    @BlorgArganizer.gatherer(focustype_iris={BLARG.SomeType})
    def blargather_focustype(focus: Focus, *, hello):
        assert BLARG.SomeType in focus.type_iris
        yield (BLARG.number, len(focus.iris))

    @BlorgArganizer.gatherer(BLARG.yoo)
    def blargather_yoo(focus: Focus, *, hello):
        if focus == _a_blargfocus:
            yield (BLARG.yoo, _nother_blargfocus)
        else:
            yield (BLARG.yoo, _a_blargfocus)

    @BlorgArganizer.gatherer(BLARG.boundedProp, cache_bound=3)
    def blargather_bounded(focus: Focus, *, hello):
        for _i in range(77):
            yield (BLARG.incidentalProp, _i * _i)
            yield (BLARG.boundedProp, _i)

    class GatheringExample(unittest.TestCase):
        maxDiff = None

        def test_gathering_declaration(self):
            self.assertEqual(
                BlorgArganizer.signup.get_gatherers(
                    _a_blargfocus,
                    {BLARG.greeting},
                ),
                {blargather_greeting, blargather_focustype},
            )
            self.assertEqual(
                BlorgArganizer.signup.get_gatherers(_a_blargfocus, {}),
                {blargather_focustype},
            )
            self.assertEqual(
                BlorgArganizer.signup.get_gatherers(
                    _nother_blargfocus,
                    {BLARG.greeting},
                ),
                {blargather_greeting},
            )
            self.assertEqual(
                BlorgArganizer.signup.get_gatherers(
                    _nother_blargfocus,
                    {BLARG.greeting, BLARG.yoo},
                ),
                {blargather_greeting, blargather_yoo},
            )
            self.assertEqual(
                BlorgArganizer.signup.get_gatherers(
                    _nother_blargfocus,
                    {},
                ),
                set(),
            )

        def test_blargask(self):
            blargAthering = BlorgArganizer.new_gathering({
                'hello': 'haha',
            })
            self.assertEqual(
                set(blargAthering.ask(BLARG.greeting, focus=_a_blargfocus)),
                {
                    rdf.literal('kia ora', language='mi'),
                    rdf.literal('hola', language='es'),
                    rdf.literal('hello', language='en'),
                    rdf.literal('haha', language=BLARG.Dunno),
                },
            )
            self.assertEqual(
                set(blargAthering.ask(
                    BLARG.unknownpredicate,
                    focus=_a_blargfocus,
                )),
                set(),
            )
            self.assertEqual(
                set(blargAthering.ask(BLARG.yoo, focus=_a_blargfocus)),
                {_nother_blargfocus.single_iri()},
            )
            self.assertEqual(
                set(blargAthering.ask(BLARG.yoo, focus=_nother_blargfocus)),
                {_a_blargfocus.single_iri()},
            )

        def test_ask_all_about(self):
            blargAthering = BlorgArganizer.new_gathering({
                'hello': 'hoohoo',
            })
            blargAthering.ask_all_about(_a_blargfocus)
            _tripledict = blargAthering.leaf_a_record().copy()
            self.assertEqual(_tripledict, {
                _a_blargfocus.single_iri(): {
                    RDF.type: {BLARG.SomeType},
                    BLARG.greeting: {
                        rdf.literal('kia ora', language='mi'),
                        rdf.literal('hola', language='es'),
                        rdf.literal('hello', language='en'),
                        rdf.literal('hoohoo', language=BLARG.Dunno),
                    },
                    BLARG.yoo: {_nother_blargfocus.single_iri()},
                    BLARG.number: {1},
                    BLARG.boundedProp: {0, 1, 2},  # only 3 objects
                    BLARG.incidentalProp: {0, 1, 4},  # only 3 objects
                },
                _nother_blargfocus.single_iri(): {
                    RDF.type: {BLARG.AnotherType},
                    BLARG.greeting: {
                        rdf.literal('kia ora', language='mi'),
                        rdf.literal('hola', language='es'),
                        rdf.literal('hello', language='en'),
                        rdf.literal('hoohoo', language=BLARG.Dunno),
                    },
                    BLARG.yoo: {_a_blargfocus.single_iri()},
                    BLARG.boundedProp: {0, 1, 2},  # only 3 objects
                    BLARG.incidentalProp: {0, 1, 4},  # only 3 objects
                },
            })

        def test_ask_streaming(self):
            blargAthering = BlorgArganizer.new_gathering({
                'hello': 'blah',
            })
            _expected_num = 0
            for _obj, _incidentals in blargAthering.ask_exhaustively(
                BLARG.boundedProp,
                focus=_a_blargfocus,
            ):
                self.assertEqual(_obj, _expected_num)
                self.assertEqual(_incidentals.tripledict, {
                    _a_blargfocus.single_iri(): {
                        BLARG.boundedProp: {_expected_num},
                        BLARG.incidentalProp: {_expected_num * _expected_num},
                    },
                })
                _expected_num += 1
            self.assertEqual(_expected_num, 77)


###
# error handling
# TODO:
#   - use GatherException consistently
#   - use Text for translatable comment
#   - as twoples? rdfs:label, rdfs:comment
class GatherException(Exception):
    def __init__(self, *, label: str, comment: str):
        super().__init__({'label': label, 'comment': comment})
