'''gather.py: a (decreasingly) tiny toolkit for gathering information

mindset metaphor:
1. name a gathering
2. pose a question
3. leaf a record

includes some type declarations to describe how this toolkit represents a
particular subset of RDF concepts (https://www.w3.org/TR/rdf11-concepts/)
using (mostly) immutable python primitives
'''
__all__ = (
    'GatheringNorms',
    'Gathering',
    'Focus',
    'IriNamespace',
    'text',
)

# only built-in imports (python 3.? (TODO: specificity))
import copy
import datetime
import functools
import itertools
import logging
import types
import typing

if __debug__:  # examples/tests thru-out, wrapped in `__debug__`
    # run tests with the command `python3 -m unittest gather.py`
    # (or discard tests with `-O` or `-OO` command-line options)
    import unittest


logger = logging.getLogger(__name__)


###
# here are some type declarations to describe how this toolkit represents a
# particular subset of RDF concepts [https://www.w3.org/TR/rdf11-concepts/]
# using (mostly) immutable python primitives
RdfSubject = str    # iri (not a blank node)
RdfPredicate = str  # iri
RdfObject = typing.Union[
    str,            # iri references as plain strings
    'Text',         # natural language as tagged text
    int, float,     # use primitives for numeric data
    datetime.date,  # use date and datetime built-ins
    frozenset,      # blanknodes as frozenset[twople]
    tuple,          # rdf:Seq (TODO: should be rdf:List and explicit type)
]
RdfTwople = tuple[RdfPredicate, RdfObject]  # implicit subject
RdfTriple = tuple[RdfSubject, RdfPredicate, RdfObject]
RdfBlanknode = frozenset[RdfTwople]

# an RDF graph as a dictionary of dictionaries
# note: these are the only mutable "Rdf" types
RdfTwopleDictionary = dict[RdfPredicate, set[RdfObject]]
RdfTripleDictionary = dict[RdfSubject, RdfTwopleDictionary]


###
# utility/helper functions for working with the "Rdf..." types above

def ensure_frozenset(something) -> frozenset:
    if isinstance(something, frozenset):
        return something
    if isinstance(something, str):
        return frozenset({something})
    if something is None:
        return frozenset()
    try:  # maybe iterable?
        return frozenset(something)
    except TypeError:
        raise ValueError(f'could not make a frozenset (got {something})')


def freeze_blanknode(twopledict: RdfTwopleDictionary) -> RdfBlanknode:
    '''build a "blank node" frozenset of twoples (rdf triples without subjects)
    '''
    return frozenset(
        (_pred, _obj)
        for _pred, _objectset in twopledict.items()
        for _obj in _objectset
    )


def add_triple_to_tripledict(
    triple: RdfTriple,
    tripledict: RdfTripleDictionary,
):
    (_subj, _pred, _obj) = triple
    (
        tripledict
        .setdefault(_subj, dict())
        .setdefault(_pred, set())
        .add(_obj)
    )


def twopleset_as_twopledict(
    twopleset: typing.Iterable[RdfTwople],
) -> RdfTwopleDictionary:
    '''build a "twople dictionary" of RDF objects indexed by predicate

    @param twopleset: iterable of (str, obj) twoples
    @returns: dict[str, set] built from twoples
    '''
    _twopledict = {}
    for _pred, _obj in twopleset:
        if _pred in _twopledict:
            _objectset = _twopledict[_pred]
        else:
            _objectset = _twopledict[_pred] = set()
        _objectset.add(_obj)
    return _twopledict


if __debug__:
    class TestBlanknodeUtils(unittest.TestCase):
        def test_ensure_frozenset(self):
            for arg, expected in (
                (None, frozenset()),
                (set(), frozenset()),
                (list(), frozenset()),
                ('foo', frozenset(('foo',))),
                (['foo', 'bar'], frozenset(('foo', 'bar'))),
                (range(3), frozenset((0, 1, 2))),
            ):
                actual = ensure_frozenset(arg)
                self.assertIsInstance(actual, frozenset)
                self.assertEqual(actual, expected)
            for arg in (
                frozenset(),
                frozenset('hello'),
                frozenset(('hello',)),
                frozenset((1, 2, 3)),
            ):
                self.assertIs(ensure_frozenset(arg), arg)

        def test_freeze_blanknode(self):
            for arg, expected in (
                ({}, frozenset()),
                ({
                    BLARG.foo: {BLARG.fob},
                    BLARG.blib: {27, 33},
                    BLARG.nope: set(),
                }, frozenset((
                    (BLARG.foo, BLARG.fob),
                    (BLARG.blib, 27),
                    (BLARG.blib, 33),
                ))),
            ):
                actual = freeze_blanknode(arg)
                self.assertIsInstance(actual, frozenset)
                self.assertEqual(actual, expected)

        def test_unfreeze_blanknode(self):
            self.assertEqual(
                twopleset_as_twopledict(frozenset()),
                {},
            )
            self.assertEqual(
                twopleset_as_twopledict(frozenset((
                    (BLARG.foo, BLARG.fob),
                    (BLARG.blib, 27),
                    (BLARG.blib, 33),
                ))),
                {
                    BLARG.foo: {BLARG.fob},
                    BLARG.blib: {27, 33},
                },
            )


def looks_like_rdf_dictionary(rdf_dictionary) -> bool:
    if not isinstance(rdf_dictionary, dict):
        return False
    for _subj, _twopledict in rdf_dictionary.items():
        if not (isinstance(_subj, str) and isinstance(_twopledict, dict)):
            return False
        for _pred, _objectset in _twopledict.items():
            if not (isinstance(_pred, str) and isinstance(_objectset, set)):
                return False
            if not all(isinstance(_obj, RdfObject) for _obj in _objectset):
                return False
    return True


def tripledict_as_tripleset(
    tripledict: RdfTripleDictionary
) -> typing.Iterable[RdfTriple]:
    for _subj, _twopledict in tripledict.items():
        for _pred, _objectset in _twopledict.items():
            for _obj in _objectset:
                yield (_subj, _pred, _obj)


def tripledict_as_turtle(
    tripledict: RdfTripleDictionary, *,
    focus=None,
) -> str:
    _rdflib_graph = tripledict_as_rdflib(tripledict)
    # TODO: sort blocks, focus first
    return _rdflib_graph.serialize(format='turtle')


def tripledict_as_rdflib(tripledict: RdfTripleDictionary):
    try:
        import rdflib
    except ImportError:
        raise Exception('tripledict_as_rdflib depends on rdflib')

    _rdflib_graph = rdflib.Graph()  # TODO: namespace prefixes?

    # a local helper
    def _add_to_rdflib_graph(
        rdflib_subj: rdflib.term.Node,
        rdflib_pred: rdflib.term.Node,
        obj: RdfObject,
    ):
        _rdflib_graph.add((rdflib_subj, rdflib_pred, _simple_rdflib_obj(obj)))

    def _simple_rdflib_obj(obj: RdfObject):
        if isinstance(obj, str):
            return rdflib.URIRef(obj)
        if isinstance(obj, Text):
            if not obj.language_iris:
                return rdflib.Literal(obj.unicode_text)
            try:
                _language_iri = next(
                    _iri
                    for _iri in obj.language_iris
                    if _iri in IANA_LANGUAGE
                )
            except StopIteration:  # non-standard language iri?
                # datatype can be any iri; link your own language
                return rdflib.Literal(
                    obj.unicode_text,
                    datatype=next(iter(obj.language_iris)),
                )
            else:  # found standard language tag
                _language_tag = IriNamespace.without_namespace(
                    _language_iri,
                    namespace=IANA_LANGUAGE,
                )
                return rdflib.Literal(
                    obj.unicode_text,
                    lang=_language_tag,
                )
        elif isinstance(obj, (int, float, datetime.date)):
            return rdflib.Literal(obj)
        elif isinstance(obj, frozenset):
            # may result in duplicates -- don't do shared blanknodes
            _blanknode = rdflib.BNode()
            for _pred, _obj in obj:
                _add_to_rdflib_graph(_blanknode, rdflib.URIRef(_pred), _obj)
            return _blanknode
        elif isinstance(obj, tuple):
            _list_bnode = rdflib.BNode()
            # TODO: should be rdf:List?
            rdflib.Seq(_rdflib_graph, _list_bnode, [
                _simple_rdflib_obj(_obj)
                for _obj in obj
            ])
            return _list_bnode
        raise ValueError(f'expected RdfObject, got {obj}')

    for (_subj, _pred, _obj) in tripledict_as_tripleset(tripledict):
        _add_to_rdflib_graph(rdflib.URIRef(_subj), rdflib.URIRef(_pred), _obj)
    return _rdflib_graph


def tripledict_from_turtle(turtle: str):
    # TODO: without rdflib (should be simpler;
    # turtle already structured like RdfTripleDictionary)
    try:
        import rdflib
    except ImportError:
        raise Exception('tripledict_from_turtle depends on rdflib')
    _rdflib_graph = rdflib.Graph()
    _rdflib_graph.parse(data=turtle, format='turtle')
    return tripledict_from_rdflib(_rdflib_graph)


def tripledict_from_rdflib(rdflib_graph):
    try:
        import rdflib
    except ImportError:
        raise Exception('tripledict_from_rdflib depends on rdflib')
    _open_subjects = set()

    def _twoples(rdflib_subj) -> typing.Iterable[RdfTwople]:
        if rdflib_subj in _open_subjects:
            raise ValueError(
                'cannot handle loopy blanknodes'
                f' (reached {rdflib_subj} again after {_open_subjects})'
            )
        _open_subjects.add(rdflib_subj)
        for _pred, _obj in rdflib_graph.predicate_objects(rdflib_subj):
            if not isinstance(_pred, rdflib.URIRef):
                raise ValueError(
                    f'cannot handle non-iri predicates (got {_pred})',
                )
            yield (str(_pred), _obj_from_rdflib(_obj))
        _open_subjects.remove(rdflib_subj)

    def _obj_from_rdflib(rdflib_obj) -> RdfObject:
        # TODO: handle rdf:List?
        if isinstance(rdflib_obj, rdflib.URIRef):
            return str(rdflib_obj)
        if isinstance(rdflib_obj, rdflib.BNode):
            return frozenset(_twoples(rdflib_obj))
        if isinstance(rdflib_obj, rdflib.Literal):
            if rdflib_obj.language:
                return text(str(rdflib_obj), language_iris={
                    IANA_LANGUAGE[rdflib_obj.language],
                })
            _as_python = rdflib_obj.toPython()
            if isinstance(_as_python, (int, float, datetime.date)):
                return _as_python
            if rdflib_obj.datatype:
                return text(str(rdflib_obj), language_iris={
                    str(rdflib_obj.datatype),
                })
            return text(str(rdflib_obj.value), language_iris=())
        raise ValueError(f'how obj? ({rdflib_obj})')

    _tripledict = {}
    for _rdflib_subj in rdflib_graph.subjects():
        if isinstance(_rdflib_subj, rdflib.URIRef):
            _subj = str(_rdflib_subj)
            for _pred, _obj in _twoples(_rdflib_subj):
                add_triple_to_tripledict(
                    (_subj, _pred, _obj),
                    _tripledict,
                )
    if rdflib_graph and not _tripledict:
        raise ValueError(
            'there was something, but we got nothing -- note that'
            ' blanknodes not reachable from an IRI subject are omitted'
        )
    return _tripledict


if __debug__:
    class TestRdflib(unittest.TestCase):
        maxDiff = None

        def test_asfrom_rdflib(self):
            try:
                import rdflib
                import rdflib.compare
            except ImportError:
                self.skipTest('cannot import rdflib')
            _tripledict = {
                BLARG.ha: {
                    BLARG.pa: {
                        BLARG.la,
                        BLARG.xa,
                        frozenset((
                            (BLARG.a, BLARG.b),
                            (BLARG.c, BLARG.d),
                            (BLARG.e, frozenset((
                                (BLARG.f, BLARG.g),
                            ))),
                        )),
                    },
                    BLARG.na: {
                        BLARG.ja,
                    },
                },
                BLARG.ya: {
                    BLARG.ba: {
                        text('ha pa la xa', language_iris={BLARG.Dunno}),
                        text('naja yaba', language_iris={BLARG.Dunno}),
                        text('basic', language_iris={IANA_LANGUAGE.en}),
                    },
                }
            }
            _input_turtle = f'''
                @prefix blarg: <{str(BLARG)}> .

                blarg:ha
                    blarg:pa blarg:la ,
                             blarg:xa ,
                             [
                                blarg:a blarg:b ;
                                blarg:c blarg:d ;
                                blarg:e [ blarg:f blarg:g ] ;
                             ] ;
                    blarg:na blarg:ja .

                blarg:ya blarg:ba "ha pa la xa"^^blarg:Dunno ,
                                  "naja yaba"^^blarg:Dunno ,
                                  "basic"@en .
            '''
            _expected = rdflib.Graph()
            _expected.parse(format='turtle', data=_input_turtle)
            _actual = tripledict_as_rdflib(_tripledict)
            self.assertEqual(
                rdflib.compare.to_isomorphic(_actual),
                rdflib.compare.to_isomorphic(_expected),
            )
            _from_rdflib = tripledict_from_rdflib(_expected)
            self.assertEqual(_from_rdflib, _tripledict)
            _from_turtle = tripledict_from_turtle(_input_turtle)
            self.assertEqual(_from_turtle, _tripledict)


class Text(typing.NamedTuple):
    unicode_text: str
    language_iris: frozenset[str]
    # note: allow any iri to identify a text language
    # (if you wish to constrain to IETF language tags
    # as https://www.rfc-editor.org/rfc/bcp/bcp47.txt
    # use the defined IANA_LANGUAGE namespace, below)

    def checksum_iri(self) -> str:
        raise NotImplementedError('TODO')


def text(unicode_text: str, *, language_iris):
    '''convenience wrapper for Text
    '''
    if not unicode_text:
        return None  # for easy omission
    return Text(
        unicode_text=unicode_text,
        language_iris=ensure_frozenset(language_iris),
    )


if __debug__:
    class TestText(unittest.TestCase):
        def test_blurb(self):
            my_blurb = text(
                'blurbl di blarbl ga',
                language_iris={BLARG['my-language']},
            )
            self.assertIsInstance(my_blurb.unicode_text, str)
            self.assertIsInstance(my_blurb.language_iris, frozenset)
            self.assertEqual(my_blurb.unicode_text, 'blurbl di blarbl ga')
            self.assertEqual(
                my_blurb.language_iris,
                frozenset({'https://blarg.example/my-language'}),
            )


class Focus(typing.NamedTuple):
    iris: frozenset[str]  # synonymous persistent identifiers in iri form
    type_iris: frozenset[str]
    # may override default gathering_kwargs from the Gathering:
    gatherer_kwargset: frozenset[tuple[str, typing.Any]]

    def single_iri(self) -> str:
        return next(iter(sorted(self.iris)))  # TODO: something better

    def as_rdf_tripleset(self) -> typing.Iterable[RdfTriple]:
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


###
# a tuple of language-text of increasing length (TODO: validate)
# choose which name to use based on the space available
# (don't worry, long Texts can/will be only referenced by checksum (...TODO))
Namestory = tuple['Text', ...]


###
# for using iris without having to type out full iris
class IriNamespace:
    '''IriNamespace: for building and using IRIs easily in python code
    (ideally IRLs ("L" for "Locator", an IRI which locates an internet
    document (like via `http`/`https`) and resolves to a document that
    makes enough sense given context), but this toolkit does not check
    for locatorishness and treats any IRI like an IRN ("N" for "Name")
    '''
    def __init__(
        self, iri: str, *,
        nameset: typing.Optional[set[str]] = None,
        namestory: typing.Optional[Namestory] = None,
    ):
        # TODO: namespace metadata/definition
        if ':' not in iri:
            raise ValueError(
                # trying out `Text` for translatable error messaging
                text(
                    f'expected iri to have a ":" (got "{iri}")',
                    language_iris={IANA_LANGUAGE.en},
                )
            )
        # assume python's "private name mangling" will avoid conflicts
        self.__iri = iri
        self.__namestory = namestory
        self.__nameset = (
            frozenset(nameset)
            if nameset is not None
            else None
        )

    @classmethod
    def without_namespace(
        cls, iri: str, *,
        namespace: typing.Union[str, 'IriNamespace'],
    ) -> str:
        namespace_iri = (
            namespace
            if isinstance(namespace, str)
            else namespace.__iri
        )
        if not iri.startswith(namespace_iri):
            raise ValueError(f'"{iri}" does not start with "{namespace_iri}"')
        return iri[len(namespace_iri):]  # the remainder after the namespace

    def __join_name(self, name: str) -> str:
        if (self.__nameset is not None) and (name not in self.__nameset):
            raise ValueError(
                f'name "{name}" not in namespace "{self.__iri}"'
                f' (allowed names: {self.__nameset})'
            )
        return ''.join((self.__iri, name))  # TODO: urlencode name

    def __getitem__(self, name_or_slice) -> str:
        '''IriNamespace.__getitem__: build iri with `SQUARE['bracket']` syntax

        use "slice" syntax to support variable namespaces within namespaces;
        up to three parts separated by colons will be concatenated

        Foo = IriNamespace('http://foo.example/')
        FOO['blah/':'blum#':'blee'] => 'http://foo.example/blah/blum#blee'
        '''
        if isinstance(name_or_slice, slice):
            name = ''.join(filter(None, (
                name_or_slice.start,
                name_or_slice.stop,
                name_or_slice.step,
            )))
        else:
            name = name_or_slice
        return self.__join_name(name)

    def __getattr__(self, attrname: str) -> str:
        '''IriNamespace.__getattr__: build iri with `DOT.dot` syntax

        convenience for names that happen to fit python's attrname constraints
        '''
        return self.__join_name(attrname)

    def __contains__(self, iri_or_namespace):
        iri = (
            iri_or_namespace.__iri
            if isinstance(iri_or_namespace, IriNamespace)
            else iri_or_namespace  # assume str
        )
        return iri.startswith(self.__iri)

    def __str__(self):
        return self.__iri

    def __repr__(self):
        return f'{self.__class__.__qualname__}("{self.__iri}")'

    def __hash__(self):
        return hash(self.__iri)


###
# some namespaces from open standards
RDF = IriNamespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#')
RDFS = IriNamespace('http://www.w3.org/2000/01/rdf-schema#')
OWL = IriNamespace('http://www.w3.org/2002/07/owl#')

# `gather.Text` uses an iri to identify language;
# here is a probably-reliable way to express IETF
# language tags in iri form
IANA_LANGUAGE_REGISTRY_IRI = (
    'https://www.iana.org/assignments/language-subtag-registry#'
)
IANA_LANGUAGE = IriNamespace(
    f'{IANA_LANGUAGE_REGISTRY_IRI}#',
    namestory=lambda: (
        text('lang', language_iris={IANA_LANGUAGE['en-US']}),
        text('language', language_iris={IANA_LANGUAGE['en-US']}),
        text('language tag', language_iris={IANA_LANGUAGE['en-US']}),
        text((
            'a "language tag" (as used by RDF and defined by IETF'
            ' ( https://www.ietf.org/rfc/bcp/bcp47.txt )) has the'
            ' structure "tag-SUBTAG", and has no defined IRI form'
            ' -- this toolkit uses a set of IRIs to identify text'
            ' languages, and this URL of the IANA Language Subtag'
            ' Registry as an IRI namespace (even tho the fragment'
            ' does not identify an item in the registry, as "tag"'
            ' and "SUBTAG" are defined separately)'
        ), language_iris={IANA_LANGUAGE['en-US']}),
    ),
)

if __debug__:
    BLARG = IriNamespace('https://blarg.example/')
    _blarg_some_focus = focus(BLARG.asome, type_iris=BLARG.SomeType)
    _blarg_nother_focus = focus(BLARG.another, type_iris=BLARG.AnotherType)

    class ExampleIriNamespaceUsage(unittest.TestCase):
        def test___contains__(self):
            self.assertEqual(BLARG.foo, 'https://blarg.example/foo')
            self.assertEqual(BLARG.blip, BLARG['blip'])
            self.assertEqual(BLARG['gloo.my'], 'https://blarg.example/gloo.my')
            self.assertIn('https://blarg.example/booboo', BLARG)
            self.assertNotIn('https://gralb.example/booboo', BLARG)
            self.assertNotIn('blip', BLARG)
            my_subvocab = IriNamespace(
                BLARG['my-subvocab/'],
                namestory=(
                    text(
                        'my-subvocab',
                        language_iris={IANA_LANGUAGE['en-US']},
                    ),
                    text(
                        'a namespace nested within the BLARG namespace',
                        language_iris={IANA_LANGUAGE['en-US']},
                    ),
                ),
            )
            self.assertIn(my_subvocab, BLARG)
            self.assertNotIn(BLARG, my_subvocab)
            self.assertEqual(
                str(my_subvocab),
                'https://blarg.example/my-subvocab/',
            )
            self.assertEqual(
                my_subvocab.oooooo,
                'https://blarg.example/my-subvocab/oooooo',
            )
            self.assertEqual(
                my_subvocab['🦎'],
                'https://blarg.example/my-subvocab/🦎',
            )
            self.assertEqual(
                my_subvocab['🦎':'🦎':'🦎'],
                'https://blarg.example/my-subvocab/🦎🦎🦎',
            )
            self.assertEqual(
                BLARG['my-subvocab/':'🦎🦎'],
                my_subvocab['🦎🦎'],
            )
            self.assertEqual(
                BLARG['my-subvocab/':'🦎🦎':'#blarp'],
                my_subvocab['🦎🦎':'#blarp'],
            )


GathererYield = typing.Union[
    RdfTriple,  # using the rdf triple as basic unit of information
    RdfTwople,  # may omit subject (assumed iri of the given focus)
    # may yield a Focus in the subject or object position, will get
    # triples from Focus.iris and Focus.type_iris, and may initiate
    # other gatherers' gathering.
    tuple[  # triples with any `None` values are silently discarded
        typing.Union[RdfSubject, Focus, None],
        typing.Union[RdfPredicate, None],
        typing.Union[RdfObject, Focus, None],
    ],
    tuple[
        typing.Union[RdfPredicate, None],
        typing.Union[RdfObject, Focus, None],
    ],
]

Gatherer = typing.Callable[[Focus], typing.Iterable[GathererYield]]

# when decorated, the yield is tidied into triples
TripleGatherer = typing.Callable[[Focus], typing.Iterable[RdfTriple]]


PredicatePathSet = dict[RdfPredicate, 'PredicatePathSet']
MaybePredicatePathSet = typing.Union[
    PredicatePathSet,
    dict[RdfPredicate, 'MaybePredicatePathSet'],
    typing.Iterable[str],
    typing.Iterable[typing.Iterable[str]],
    str,
    None,
]


def tidy_predicate_pathset(
    maybe_pathset: MaybePredicatePathSet,
) -> PredicatePathSet:
    if not maybe_pathset:
        return {}
    if isinstance(maybe_pathset, str):
        return {maybe_pathset: {}}
    if isinstance(maybe_pathset, dict):
        return {
            _pred: tidy_predicate_pathset(_nested_pathset)
            for _pred, _nested_pathset in maybe_pathset.items()
        }
    # assume Iterable
    _pathset = {}
    for _maybe_path in maybe_pathset:
        if isinstance(_maybe_path, str):
            _pathset[_maybe_path] = {}
        else:  # assume Iterable[str]
            _nested_pathset = _pathset
            for _iri in _maybe_path:
                _nested_pathset = _nested_pathset.setdefault(_iri, {})
    return _pathset


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
        gatherer_kwargnames: typing.Optional[typing.Iterable[str]] = None,
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
        self,
        focus: typing.Union[str, Focus],
        pathset: MaybePredicatePathSet,  # could be messy
    ) -> typing.Iterable[RdfObject]:
        _focus = (
            self.cache.get_focus_by_iri(focus)
            if isinstance(focus, str)
            else focus
        )
        _tidy_pathset = tidy_predicate_pathset(pathset)
        self.__gather_by_pathset(_tidy_pathset, focus=_focus)
        return self.cache.peek(_tidy_pathset, focus=_focus)

    def ask_all_about(self, focus: typing.Union[str, Focus]):
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
                self.ask(_focus, _predicate_iris)
                _focus_to_visit.update(self.cache.focus_set - _focus_visited)

    def leaf_a_record(self, *, pls_copy=False) -> RdfTripleDictionary:
        return (
            copy.deepcopy(self.cache.tripledict)
            if pls_copy
            else types.MappingProxyType(self.cache.tripledict)
        )

    def __gather_by_pathset(self, pathset: PredicatePathSet, *, focus: Focus):
        '''gather information into the cache (unless already gathered)
        '''
        self.__gather_predicate_iris(focus, pathset.keys())
        for _predicate_iri, _next_pathset in pathset.items():
            if _next_pathset:
                for _obj in self.cache.peek({_predicate_iri: {}}, focus=focus):
                    # indirect recursion:
                    self.__gather_thru_object(_next_pathset, _obj)

    def __gather_thru_object(self, pathset: PredicatePathSet, obj: RdfObject):
        if isinstance(obj, str):  # iri
            try:
                _next_focus = self.cache.get_focus_by_iri(obj)
            except GatherException:
                return  # not a usable focus
            else:
                self.__gather_by_pathset(pathset, focus=_next_focus)
        elif isinstance(obj, frozenset):  # blank node
            for _pred, _obj in obj:
                _next_pathset = pathset.get(_pred)
                if _next_pathset:
                    self.__gather_thru_object(_next_pathset, _obj)
        # otherwise, ignore

    def __gather_predicate_iris(
        self,
        focus: Focus,
        predicate_iris: typing.Iterable[str],
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


class _GatherCache:
    tripledict: RdfTripleDictionary
    gathers_done: set[tuple[Gatherer, Focus]]
    focus_set: set[Focus]

    def __init__(self):
        self.tripledict = dict()
        self.gathers_done = set()
        self.focus_set = set()

    def get_focus_by_iri(self, iri: str):
        try:
            _type_iris = self.tripledict[iri][RDF.type]
        except KeyError:
            raise GatherException(
                label='cannot-get-focus',
                comment=f'found no type for "{iri}"',
            )
        try:
            _same_iris = self.tripledict[iri][OWL.sameAs]
        except KeyError:
            _iris = {iri}
        else:
            _iris = {iri, *_same_iris}
        _focus = focus(iris=_iris, type_iris=_type_iris)
        self.add_focus(_focus)
        return _focus

    def add_focus(self, focus: Focus):
        if focus not in self.focus_set:
            self.focus_set.add(focus)
            for triple in focus.as_rdf_tripleset():
                self.add_triple(triple)

    def add_triple(self, triple: RdfTriple):
        (_subj, _pred, _obj) = triple
        _subj = self.__maybe_unwrap_focus(_subj)
        _obj = self.__maybe_unwrap_focus(_obj)
        add_triple_to_tripledict(
            (_subj, _pred, _obj),
            self.tripledict,
        )

    def peek(
        self, pathset: PredicatePathSet, *,
        focus: typing.Union[Focus, str],
    ) -> typing.Iterable[RdfObject]:
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
        for _predicate_iri, _next_pathset in pathset.items():
            _object_set = (
                self.tripledict
                .get(_focus_iri, {})
                .get(_predicate_iri, set())
            )
            if _next_pathset:
                for _obj in _object_set:
                    if isinstance(_obj, str):
                        yield from self.peek(_next_pathset, focus=_obj)
            else:
                yield from _object_set

    def already_gathered(
        self, gatherer: Gatherer, focus: Focus, *,
        pls_mark_done=True,
    ) -> bool:
        gatherkey = (gatherer, focus)
        is_done = (gatherkey in self.gathers_done)
        if pls_mark_done and not is_done:
            self.gathers_done.add(gatherkey)
        return is_done

    def __maybe_unwrap_focus(self, maybefocus: typing.Union[Focus, RdfObject]):
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
        predicate_iris: typing.Iterable[str],
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
    BlargAtheringNorms = GatheringNorms(
        namestory=(
            text('blarg', language_iris={BLARG.myLanguage}),
            text('blargl blarg', language_iris={BLARG.myLanguage}),
            text(
                'a gathering called "blarg"',
                language_iris={IANA_LANGUAGE['en-US']},
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
            text('blarg this way', language_iris={BLARG.myLanguage}),
        ),
        norms=BlargAtheringNorms,
        gatherer_kwargnames={'hello'},
    )

    @BlorgArganizer.gatherer(BLARG.greeting)
    def blargather_greeting(focus: Focus, *, hello):
        yield (BLARG.greeting, text(
            'kia ora',
            language_iris={IANA_LANGUAGE.mi},
        ))
        yield (BLARG.greeting, text(
            'hola',
            language_iris={IANA_LANGUAGE.es},
        ))
        yield (BLARG.greeting, text(
            'hello',
            language_iris={IANA_LANGUAGE.en},
        ))
        yield (BLARG.greeting, text(
            hello,
            language_iris={BLARG.Dunno},
        ))

    @BlorgArganizer.gatherer(focustype_iris={BLARG.SomeType})
    def blargather_focustype(focus: Focus, *, hello):
        assert BLARG.SomeType in focus.type_iris
        yield (BLARG.number, len(focus.iris))

    @BlorgArganizer.gatherer(BLARG.yoo)
    def blargather_yoo(focus: Focus, *, hello):
        if focus == _blarg_some_focus:
            yield (BLARG.yoo, _blarg_nother_focus)
        else:
            yield (BLARG.yoo, _blarg_some_focus)

    class GatheringExample(unittest.TestCase):
        maxDiff = None

        def test_gathering_declaration(self):
            self.assertEqual(
                BlorgArganizer.signup.get_gatherers(
                    _blarg_some_focus,
                    {BLARG.greeting},
                ),
                {blargather_greeting, blargather_focustype},
            )
            self.assertEqual(
                BlorgArganizer.signup.get_gatherers(_blarg_some_focus, {}),
                {blargather_focustype},
            )
            self.assertEqual(
                BlorgArganizer.signup.get_gatherers(
                    _blarg_nother_focus,
                    {BLARG.greeting},
                ),
                {blargather_greeting},
            )
            self.assertEqual(
                BlorgArganizer.signup.get_gatherers(
                    _blarg_nother_focus,
                    {BLARG.greeting, BLARG.yoo},
                ),
                {blargather_greeting, blargather_yoo},
            )
            self.assertEqual(
                BlorgArganizer.signup.get_gatherers(
                    _blarg_nother_focus,
                    {},
                ),
                set(),
            )

        def test_blargask(self):
            blargAthering = BlorgArganizer.new_gathering({
                'hello': 'haha',
            })
            self.assertEqual(
                set(blargAthering.ask(_blarg_some_focus, BLARG.greeting)),
                {
                    text('kia ora', language_iris={IANA_LANGUAGE.mi}),
                    text('hola', language_iris={IANA_LANGUAGE.es}),
                    text('hello', language_iris={IANA_LANGUAGE.en}),
                    text('haha', language_iris={BLARG.Dunno}),
                },
            )
            self.assertEqual(
                set(blargAthering.ask(
                    _blarg_some_focus,
                    BLARG.unknownpredicate,
                )),
                set(),
            )
            self.assertEqual(
                set(blargAthering.ask(_blarg_some_focus, BLARG.yoo)),
                {_blarg_nother_focus.single_iri()},
            )
            self.assertEqual(
                set(blargAthering.ask(_blarg_nother_focus, BLARG.yoo)),
                {_blarg_some_focus.single_iri()},
            )

        def test_ask_all_about(self):
            blargAthering = BlorgArganizer.new_gathering({
                'hello': 'hoohoo',
            })
            blargAthering.ask_all_about(_blarg_some_focus)
            _tripledict = blargAthering.leaf_a_record(pls_copy=True)
            self.assertEqual(_tripledict, {
                _blarg_some_focus.single_iri(): {
                    RDF.type: {BLARG.SomeType},
                    BLARG.greeting: {
                        text('kia ora', language_iris={IANA_LANGUAGE.mi}),
                        text('hola', language_iris={IANA_LANGUAGE.es}),
                        text('hello', language_iris={IANA_LANGUAGE.en}),
                        text('hoohoo', language_iris={BLARG.Dunno}),
                    },
                    BLARG.yoo: {_blarg_nother_focus.single_iri()},
                    BLARG.number: {1},
                },
                _blarg_nother_focus.single_iri(): {
                    RDF.type: {BLARG.AnotherType},
                    BLARG.greeting: {
                        text('kia ora', language_iris={IANA_LANGUAGE.mi}),
                        text('hola', language_iris={IANA_LANGUAGE.es}),
                        text('hello', language_iris={IANA_LANGUAGE.en}),
                        text('hoohoo', language_iris={BLARG.Dunno}),
                    },
                    BLARG.yoo: {_blarg_some_focus.single_iri()},
                },
            })


###
# utilities for working with dataclasses
#
# treat `dataclasses.Field.metadata` as twople-dictionary describing a property
# (iri keys are safe enough against collision), with implicit `rdfs:label` from
# `Field.name` (possible TODO: gather a `shacl:PropertyShape` for `Field.type`)
#
# may treat a dataclass instance as blanknode, twople-dictionary, or twople-set
# (TODO: maybe build a Focus based on fields mapped to owl:sameAs and rdf:type)

try:
    import dataclasses
except ImportError:
    logger.info(
        'gather.py: dataclasses not available; omitting dataclass utilities',
    )
else:
    def dataclass_as_twoples(
        dataclass_instance,
        iri_by_fieldname=None,
    ) -> typing.Iterable[RdfTwople]:
        '''express the given dataclass instance as RDF predicate-subject pairs

        to be included, a field must have a name in `iri_by_fieldname` or have
        a value for owl:sameAs (in full iri form) in `metadata`:
        ```
        @dataclasses.dataclass
        class MyDataclass:
            word: str = dataclasses.field(metadata={
                OWL.sameAs: MY_IRI_NAMESPACE.myWord,
            })
            ignored: str
        ```
        '''
        for dataclass_field in dataclasses.fields(dataclass_instance):
            field_value = getattr(
                dataclass_instance,
                dataclass_field.name,
                None,
            )
            if field_value is not None:
                if iri_by_fieldname is not None:
                    try:
                        yield (
                            iri_by_fieldname[dataclass_field.name],
                            field_value,
                        )
                    except KeyError:
                        pass
                field_iris = dataclass_field.metadata.get(OWL.sameAs, ())
                for field_iri in field_iris:
                    yield (field_iri, field_value)

    def dataclass_as_twopledict(
        dataclass_instance,
        iri_by_fieldname,
    ) -> RdfTwopleDictionary:
        return frozenset(
            dataclass_as_twoples(dataclass_instance, iri_by_fieldname),
        )

    def dataclass_as_blanknode(
        dataclass_instance,
        iri_by_fieldname,
    ) -> RdfBlanknode:
        return frozenset(
            dataclass_as_twoples(dataclass_instance, iri_by_fieldname),
        )

    if __debug__:
        @dataclasses.dataclass
        class BlargDataclass:
            foo: str = dataclasses.field(metadata={
                OWL.sameAs: {BLARG.foo},
            })
            bar: str  # unadorned

        class TestBlarg(unittest.TestCase):
            def test_as_twoples(self):
                blarg = BlargDataclass(foo='foo', bar='bar')
                self.assertEqual(
                    set(dataclass_as_twoples(blarg, {})),
                    {(BLARG.foo, 'foo')},
                )
                self.assertEqual(
                    set(dataclass_as_twoples(blarg, {'bar': BLARG.barrr})),
                    {
                        (BLARG.foo, 'foo'),
                        (BLARG.barrr, 'bar'),
                    },
                )
                self.assertEqual(
                    set(dataclass_as_twoples(blarg, {
                        'foo': BLARG.fool,
                        'bar': BLARG.barr,
                        'baz': BLARG.baz,
                    })),
                    {
                        (BLARG.foo, 'foo'),
                        (BLARG.fool, 'foo'),
                        (BLARG.barr, 'bar'),
                    },
                )

            def test_as_blanknode(self):
                blarg = BlargDataclass(foo='bloo', bar='blip')
                actual = dataclass_as_blanknode(blarg, {})
                self.assertIsInstance(actual, frozenset)
                self.assertEqual(actual, frozenset((
                    (BLARG.foo, 'bloo'),
                )))


###
# error handling
# TODO:
#   - use GatherException consistently
#   - use Text for translatable comment
#   - as twoples? rdfs:label, rdfs:comment
class GatherException(Exception):
    def __init__(self, *, label: str, comment: str):
        super().__init__({'label': label, 'comment': comment})
