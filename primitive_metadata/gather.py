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
1. name a gathering
2. pose a question
3. leaf a record
'''

import copy
import functools
import itertools
import types
from typing import Union, NamedTuple, Iterable, Any, Callable, Optional

from gather.primitive_rdf import (
    IriNamespace,
    MessyPathset,
    Namestory,
    OWL,
    RDF,
    RDFS,
    RdfObject,
    RdfTriple,
    RdfTripleDictionary,
    RdfTwople,
    TidyPathset,
    TripledictWrapper,
    ensure_frozenset,
    is_container,
    container_objects,
    literal,
    tidy_pathset,
)

__all__ = (
    'GatheringNorms',
    'GatheringOrganizer',
    'Gathering',
)

if __debug__:  # tests under __debug__ thru-out
    import unittest  # TODO: doctest


class Focus(NamedTuple):
    iris: frozenset[str]  # synonymous persistent identifiers in iri form
    type_iris: frozenset[str]
    # may override default gathering_kwargs from the Gathering:
    gatherer_kwargset: frozenset[tuple[str, Any]]

    def single_iri(self) -> str:
        return min(self.iris, key=len)  # choose the shortest iri

    def as_rdf_tripleset(self) -> Iterable[RdfTriple]:
        _iri = self.single_iri()
        for _type_iri in self.type_iris:
            yield (_iri, RDF.type, _type_iri)
        for _same_iri in self.iris:
            if _same_iri != _iri:
                yield (_iri, OWL.sameAs, _same_iri)
        # TODO: gatherer_kwargset?


def focus(iris=None, type_iris=None, gatherer_kwargset=None):
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
    return Focus(
        iris=ensure_frozenset(iris),
        type_iris=ensure_frozenset(type_iris),
        gatherer_kwargset=_gatherer_kwargset,
    )


GathererYield = Union[
    RdfTriple,  # using the rdf triple as basic unit of information
    RdfTwople,  # may omit subject (assumed iri of the given focus)
    # may yield a Focus in the subject or object position, will get
    # triples from Focus.iris and Focus.type_iris, and may initiate
    # other gatherers' gathering.
    tuple[  # triples with any `None` values are silently discarded
        Union[str, Focus, None],
        Union[str, None],
        Union[RdfObject, Focus, None],
    ],
    tuple[
        Union[str, None],
        Union[RdfObject, Focus, None],
    ],
]

Gatherer = Callable[[Focus], Iterable[GathererYield]]

# when decorated, the yield is tidied into triples
TripleGatherer = Callable[
    [Focus],
    Iterable[RdfTriple],
]


###
# to start gathering information:
# - declare a `GatheringNorms` with pre-defined vocabularies, names, etc.
# - declare a `GatheringOrganizer` for each implementation of given norms
# - write `Gatherer` functions that yield triples or twoples, given Focus

class GatheringNorms:
    def __init__(
        self, *,
        namestory: Namestory,
        vocabulary: RdfTripleDictionary,
        focustype_iris: frozenset[str],
    ):
        self.namestory = namestory
        self.vocabulary = vocabulary
        self.focustype_iris = ensure_frozenset(focustype_iris)


class GatheringOrganizer:
    def __init__(
        self,
        namestory: Namestory,
        norms: GatheringNorms,
        gatherer_kwargnames: Optional[Iterable[str]] = None,
        # TODO: gatherer_kwarg_iris, let each gatherer declare its accepted
        # kwargs with a dictionary {kwarg_name: kwarg_iri} -- decouple outward
        # "organizer" interface from organizer-gatherer interface, allow
        # omitting gatherer_kwargs for gatherers not actually used
    ):
        self.namestory = namestory
        self.norms = norms
        self.gatherer_kwargnames = gatherer_kwargnames
        self.signup = _GathererSignup()

    def new_gathering(self, gatherer_kwargs=None):
        self.validate_gatherer_kwargnames(gatherer_kwargs)
        return Gathering(
            norms=self.norms,
            organizer=self,
            gatherer_kwargs=(gatherer_kwargs or {}),
        )

    def gatherer(self, *predicate_iris, focustype_iris=None):
        '''decorate gatherer functions with their iris of interest
        '''
        def _gatherer_decorator(gatherer_fn: Gatherer) -> TripleGatherer:
            _triple_gatherer = self.__make_triple_gatherer(gatherer_fn)
            self.signup.add_gatherer(
                _triple_gatherer,
                predicate_iris=predicate_iris,
                focustype_iris=(focustype_iris or ()),
            )
            return _triple_gatherer
        return _gatherer_decorator

    def __make_triple_gatherer(self, gatherer_fn: Gatherer) -> TripleGatherer:
        @functools.wraps(gatherer_fn)
        def _triple_gatherer(focus: Focus, **gatherer_kwargs):
            self.validate_gatherer_kwargnames(gatherer_kwargs)
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

    def validate_gatherer_kwargnames(self, gatherer_kwargs: dict):
        _kwargnames = frozenset(gatherer_kwargs.keys())
        if _kwargnames != self.gatherer_kwargnames:
            raise GatherException(
                label='invalid-gatherer-kwargs',
                comment=(
                    f'expected {self.gatherer_kwargnames},'
                    f' got {_kwargnames}'
                )
            )


class Gathering:
    def __init__(
        self,
        norms: GatheringNorms,
        organizer: GatheringOrganizer,
        gatherer_kwargs: dict,
    ):
        self.norms = norms
        self.organizer = organizer
        self.gatherer_kwargs = gatherer_kwargs
        self.cache = _GatherCache()

    def ask(
        self, pathset: MessyPathset, *,
        focus: Union[str, Focus],
    ) -> Iterable[RdfObject]:
        _focus = (
            self.cache.get_focus_by_iri(focus)
            if isinstance(focus, str)
            else focus
        )
        _tidy_pathset = tidy_pathset(pathset)
        self.__gather_by_pathset(_tidy_pathset, focus=_focus)
        return self.cache.peek(_tidy_pathset, focus=_focus)

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

    def leaf_a_record(self, *, pls_copy=False) -> RdfTripleDictionary:
        return (
            copy.deepcopy(self.cache.tripledict)
            if pls_copy
            else types.MappingProxyType(self.cache.tripledict)
        )

    def __gather_by_pathset(self, pathset: TidyPathset, *, focus: Focus):
        '''gather information into the cache (unless already gathered)
        '''
        self.__gather_predicate_iris(focus, pathset.keys())
        for _pred, _next_pathset in pathset.items():
            if _next_pathset:
                for _obj in self.cache.peek(_pred, focus=focus):
                    # indirect recursion:
                    self.__gather_thru_object(_next_pathset, _obj)

    def __gather_thru_object(
        self,
        pathset: TidyPathset,
        obj: RdfObject,
    ):
        if isinstance(obj, str):  # iri
            try:
                _next_focus = self.cache.get_focus_by_iri(obj)
            except GatherException:
                return  # not a usable focus
            else:
                self.__gather_by_pathset(pathset, focus=_next_focus)
        elif isinstance(obj, frozenset):  # blank node
            if is_container(obj):  # pass thru rdf containers transparently
                for _container_obj in container_objects(obj):
                    self.__gather_thru_object(pathset, _container_obj)
            else:  # not a container
                for _pred, _obj in obj:
                    _next_pathset = pathset.get(_pred)
                    if _next_pathset:
                        self.__gather_thru_object(_next_pathset, _obj)
        # otherwise, ignore

    def __gather_predicate_iris(
        self,
        focus: Focus,
        predicate_iris: Iterable[str],
    ):
        self.cache.add_focus(focus)
        _signup = self.organizer.signup
        for gatherer in _signup.get_gatherers(focus, predicate_iris):
            self.__maybe_gather(gatherer, focus)

    def __maybe_gather(self, gatherer, focus):
        if not self.cache.already_gathered(gatherer, focus):
            _gatherer_kwargs = {
                **self.gatherer_kwargs,
                **dict(focus.gatherer_kwargset),
            }
            for triple in gatherer(focus, **_gatherer_kwargs):
                self.cache.add_triple(triple)


class _GatherCache(TripledictWrapper):
    gathers_done: set[tuple[Gatherer, Focus]]
    focus_set: set[Focus]

    def __init__(self):
        self.gathers_done = set()
        self.focus_set = set()
        super().__init__({})

    def add_focus(self, focus: Focus):
        if focus not in self.focus_set:
            self.focus_set.add(focus)
            for triple in focus.as_rdf_tripleset():
                self.add_triple(triple)

    def get_focus_by_iri(self, iri: str):
        _type_iris = frozenset(self.q(iri, RDF.type))
        if not _type_iris:
            raise GatherException(
                label='cannot-get-focus',
                comment=f'found no type for "{iri}"',
            )
        _same_iris = self.q(iri, OWL.sameAs)
        _iris = {iri, *_same_iris}
        _focus = focus(iris=_iris, type_iris=_type_iris)
        self.add_focus(_focus)
        return _focus

    def add_triple(self, triple: RdfTriple):
        (_subj, _pred, _obj) = triple
        _subj = self.__maybe_unwrap_focus(_subj)
        _obj = self.__maybe_unwrap_focus(_obj)
        super().add_triple((_subj, _pred, _obj))

    def peek(
        self, pathset: MessyPathset, *,
        focus: Union[Focus, str],
    ) -> Iterable[RdfObject]:
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
        return self.q(_focus_iri, pathset)

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
            maybefocus: Union[Focus, RdfObject],
    ):
        if isinstance(maybefocus, Focus):
            self.add_focus(maybefocus)
            return maybefocus.single_iri()
        return maybefocus


if __debug__:
    class TestGatherCache(unittest.TestCase):
        pass  # TODO


class _GathererSignup:
    _by_predicate: dict[str, set[Gatherer]]
    _by_focustype: dict[str, set[Gatherer]]
    _for_any_predicate: set[Gatherer]
    _for_any_focustype: set[Gatherer]

    def __init__(self):
        self._by_predicate = {}
        self._by_focustype = {}
        self._for_any_predicate = set()
        self._for_any_focustype = set()

    def add_gatherer(
        self, gatherer: TripleGatherer, *,
        predicate_iris,
        focustype_iris,
    ):
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
    ):
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
        return gatherer_set


if __debug__:
    BLARG = IriNamespace('https://blarg.example/')
    _a_blargfocus = focus(
        BLARG.asome,
        type_iris=BLARG.SomeType,
    )
    _nother_blargfocus = focus(
        BLARG.another,
        type_iris=BLARG.AnotherType,
    )
    BlargAtheringNorms = GatheringNorms(
        namestory=(
            literal('blarg', language=BLARG.myLanguage),
            literal('blargl blarg', language=BLARG.myLanguage),
            literal(
                'a gathering called "blarg"',
                language='en-US',
            ),
        ),
        vocabulary={
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
    )

    BlorgArganizer = GatheringOrganizer(
        namestory=(
            literal('blarg this way', language=BLARG.myLanguage),
        ),
        norms=BlargAtheringNorms,
        gatherer_kwargnames={'hello'},
    )

    @BlorgArganizer.gatherer(BLARG.greeting)
    def blargather_greeting(focus: Focus, *, hello):
        yield (BLARG.greeting, literal(
            'kia ora',
            language='mi',
        ))
        yield (BLARG.greeting, literal(
            'hola',
            language='es',
        ))
        yield (BLARG.greeting, literal(
            'hello',
            language='en',
        ))
        yield (BLARG.greeting, literal(
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
                    literal('kia ora', language='mi'),
                    literal('hola', language='es'),
                    literal('hello', language='en'),
                    literal('haha', language=BLARG.Dunno),
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
            _tripledict = blargAthering.leaf_a_record(pls_copy=True)
            self.assertEqual(_tripledict, {
                _a_blargfocus.single_iri(): {
                    RDF.type: {BLARG.SomeType},
                    BLARG.greeting: {
                        literal('kia ora', language='mi'),
                        literal('hola', language='es'),
                        literal('hello', language='en'),
                        literal('hoohoo', language=BLARG.Dunno),
                    },
                    BLARG.yoo: {_nother_blargfocus.single_iri()},
                    BLARG.number: {1},
                },
                _nother_blargfocus.single_iri(): {
                    RDF.type: {BLARG.AnotherType},
                    BLARG.greeting: {
                        literal('kia ora', language='mi'),
                        literal('hola', language='es'),
                        literal('hello', language='en'),
                        literal('hoohoo', language=BLARG.Dunno),
                    },
                    BLARG.yoo: {_a_blargfocus.single_iri()},
                },
            })


###
# error handling
# TODO:
#   - use GatherException consistently
#   - use Text for translatable comment
#   - as twoples? rdfs:label, rdfs:comment
class GatherException(Exception):
    def __init__(self, *, label: str, comment: str):
        super().__init__({'label': label, 'comment': comment})
