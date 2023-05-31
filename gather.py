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
    'Text',
    'Focus',
    'IriNamespace',
)

# only built-in imports (python 3.? (TODO: specificity))
import contextlib
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
    'Text',         # language iris required for Text
    int, float,     # use primitives for numeric data
    datetime.date,  # use date and datetime built-ins
    frozenset,      # blanknodes as frozenset[twople]
]
RdfTwople = tuple[RdfPredicate, RdfObject]  # implicit subject
RdfTriple = tuple[RdfSubject, RdfPredicate, RdfObject]
RdfBlanknode = frozenset[RdfTwople]

# an RDF graph as a dictionary of dictionaries
# note: these are the only mutable "Rdf" types
RdfTwopleDictionary = dict[RdfPredicate, set[RdfObject]]
RdfTripleDictionary = dict[RdfSubject, RdfTwopleDictionary]


###
# utility/helper functions for working with the above types

def ensure_frozenset(something) -> frozenset:
    if isinstance(something, frozenset):
        return something
    if isinstance(something, str):
        return frozenset((something,))
    if something is None:
        return frozenset()
    return frozenset(something)  # error if not iterable


def freeze_blanknode(twopledict: RdfTwopleDictionary) -> RdfBlanknode:
    '''build a "blank node" frozenset of twoples (rdf triples without subjects)
    '''
    return frozenset(
        (_pred, _obj)
        for _pred, _obj_set in twopledict.items()
        for _obj in _obj_set
    )


def unfreeze_blanknode(blanknode: RdfBlanknode) -> RdfTwopleDictionary:
    '''build a "twople dictionary" of RDF objects indexed by predicate

    @param blanknode: frozenset of (str, obj) twoples
    @returns: dict[str, set] built from blanknode twoples
    '''
    _twopledict = {}
    for _pred, _obj in blanknode:
        _twopledict.setdefault(_pred, set()).add(_obj)
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
                unfreeze_blanknode(frozenset()),
                {},
            )
            self.assertEqual(
                unfreeze_blanknode(frozenset((
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
        for _pred, _obj_set in _twopledict.items():
            if not (isinstance(_pred, str) and isinstance(_obj_set, set)):
                return False
            if not all(isinstance(_obj, RdfObject) for _obj in _obj_set):
                return False
    return True


def tripledict_as_tripleset(
    tripledict: RdfTripleDictionary
) -> typing.Iterable[RdfTriple]:
    for _subj, _twopledict in tripledict.items():
        for _pred, _obj_set in _twopledict.items():
            for _obj in _obj_set:
                yield (_subj, _pred, _obj)


def rdfobject_as_jsonld(rdfobject: RdfObject):
    if isinstance(rdfobject, frozenset):
        return {
            _pred: [
                rdfobject_as_jsonld(_obj)
                for _obj in _objectset
            ]
            for _pred, _objectset in unfreeze_blanknode(rdfobject).items()
        }
    elif isinstance(rdfobject, Text):
        # TODO: preserve multiple language iris somehow
        try:
            _language_tag = next(
                IriNamespace.without_namespace(_iri, namespace=IANA_LANGUAGE)
                for _iri in rdfobject.language_iris
                if _iri in IANA_LANGUAGE
            )
        except StopIteration:  # got a non-standard language iri
            return {
                '@value': rdfobject.unicode_text,
                '@type': next(iter(rdfobject.language_iris)),
            }
        else:  # got a language tag
            return {
                '@value': rdfobject.unicode_text,
                '@language': _language_tag,
            }
    elif isinstance(rdfobject, str):
        return {'@id': rdfobject}
    elif isinstance(rdfobject, (float, int, datetime.date)):
        return rdfobject


def twopledict_as_jsonld(twopledict: RdfTwopleDictionary) -> dict:
    return {
        _pred: [
            rdfobject_as_jsonld(_obj)
            for _obj in _objset
        ]
        for _pred, _objset in twopledict.items()
    }


def tripledict_as_html(tripledict: RdfTripleDictionary, *, focus) -> str:
    # TODO: microdata, css, language tags
    from xml.etree.ElementTree import TreeBuilder, tostring
    _html_builder = TreeBuilder()
    # define some local helpers:

    @contextlib.contextmanager
    def _nest_element(tag_name, attrs=None):
        _html_builder.start(tag_name, attrs or {})
        yield
        _html_builder.end(tag_name)

    def _leaf_element(tag_name, *, text=None, attrs=None):
        _html_builder.start(tag_name, attrs or {})
        if text is not None:
            _html_builder.data(text)
        _html_builder.end(tag_name)

    def _twoples_list(twoples: RdfTwopleDictionary, attrs=None):
        with _nest_element('ul', (attrs or {})):
            for _pred, _obj_set in twoples.items():
                with _nest_element('li'):
                    _leaf_element('span', text=_pred)  # TODO: <a href>
                    with _nest_element('ul'):
                        for _obj in _obj_set:
                            with _nest_element('li'):
                                _obj_element(_obj)

    def _obj_element(obj: RdfObject):
        if isinstance(obj, frozenset):
            _twoples_list(unfreeze_blanknode(obj))
        elif isinstance(obj, Text):
            # TODO language tag
            _leaf_element('span', text=str(obj))
        elif isinstance(obj, str):
            # TODO link to anchor on this page?
            _leaf_element('a', text=obj)
        elif isinstance(obj, (float, int, datetime.date)):
            # TODO datatype?
            _leaf_element('span', text=str(obj))

    # now use those helpers to build an <article>
    # with all the info gathered in this gathering
    with _nest_element('article'):
        _leaf_element('h1', text=str(focus))  # TODO: shortened display name
        # TODO: start with focus
        for _subj, _twopledict in tripledict.items():
            with _nest_element('section'):
                _leaf_element('h2', text=_subj)
                _twoples_list(_twopledict)
    # and serialize as str
    return tostring(
        _html_builder.close(),
        encoding='unicode',
        method='html',
    )


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

    # a local helper
    def _yield_rdflib(
        rdflib_subj: rdflib.term.Node,
        rdflib_pred: rdflib.term.Node,
        obj: RdfObject,
    ):
        if isinstance(obj, str):
            yield (rdflib_subj, rdflib_pred, rdflib.URIRef(obj))
        elif isinstance(obj, Text):
            assert len(obj.language_iris), (
                f'expected {obj} to have language_iris'
            )
            for _language_iri in obj.language_iris:
                try:
                    _language_tag = IriNamespace.without_namespace(
                        _language_iri,
                        namespace=IANA_LANGUAGE,
                    )
                except ValueError:  # got a non-standard language iri
                    # datatype can be any iri; link your own language
                    _literal_text = rdflib.Literal(
                        obj.unicode_text,
                        datatype=_language_iri,
                    )
                else:  # got a language tag
                    _literal_text = rdflib.Literal(
                        obj.unicode_text,
                        lang=_language_tag,
                    )
                yield (rdflib_subj, rdflib_pred, _literal_text)
        elif isinstance(obj, (int, float, datetime.date)):
            yield (rdflib_subj, rdflib_pred, rdflib.Literal(obj))
        elif isinstance(obj, frozenset):
            # may result in duplicates -- don't do shared blanknodes
            _blanknode = rdflib.BNode()
            yield (rdflib_subj, rdflib_pred, _blanknode)
            for _pred, _obj in obj:
                yield from _yield_rdflib(
                    _blanknode,
                    rdflib.URIRef(_pred),
                    _obj,
                )
        else:
            raise ValueError(f'should be RdfObject, got {obj}')

    _rdflib_graph = rdflib.Graph()  # TODO: namespace prefixes?
    for (_subj, _pred, _obj) in tripledict_as_tripleset(tripledict):
        for _rdflib_triple in _yield_rdflib(
                rdflib.URIRef(_subj),
                rdflib.URIRef(_pred),
                _obj,
        ):
            _rdflib_graph.add(_rdflib_triple)
    return _rdflib_graph


if __debug__:
    class TestRdflib(unittest.TestCase):
        def test_as_rdflib(self):
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
                        Text.new('ha pa la xa', language_iris={BLARG.Dunno}),
                        Text.new('naja yaba', language_iris={BLARG.Dunno}),
                        Text.new('basic', language_iris={IANA_LANGUAGE.en}),
                    },
                }
            }
            _expected = rdflib.Graph()
            _expected.parse(data=f'''
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
            ''', format='turtle')
            _actual = tripledict_as_rdflib(_tripledict)
            self.assertEqual(
                rdflib.compare.to_isomorphic(_actual),
                rdflib.compare.to_isomorphic(_expected),
            )


class Text(typing.NamedTuple):
    unicode_text: str
    language_iris: frozenset[str]
    # note: allow any iri to identify a text language
    # (if you wish to constrain to IETF language tags
    # as https://www.rfc-editor.org/rfc/bcp/bcp47.txt
    # use the defined IANA_LANGUAGE namespace, below)

    @classmethod
    def new(cls, unicode_text: str, language_iris):
        # ensure frozen/hashable
        return cls(
            unicode_text=unicode_text,
            language_iris=ensure_frozenset(language_iris),
        )

    def checksum_iri(self) -> str:
        raise NotImplementedError('TODO')


if __debug__:
    class TestText(unittest.TestCase):
        def test_blurb(self):
            my_blurb = Text.new(
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

    @classmethod
    def new(cls, iris=None, type_iris=None):
        return cls(
            iris=ensure_frozenset(iris),
            type_iris=ensure_frozenset(type_iris),
        )

    def single_iri(self) -> str:
        return next(iter(sorted(self.iris)))  # TODO: something better

    def as_rdf_tripleset(self) -> typing.Iterable[RdfTriple]:
        _iri = self.single_iri()
        for _type_iri in self.type_iris:
            yield (_iri, RDF.type, _type_iri)
        for _same_iri in self.iris:
            if _same_iri != _iri:
                yield (_iri, OWL.sameAs, _same_iri)


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
                Text.new(
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
        return ''.join((self.__iri, name))

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
OWL = IriNamespace('http://www.w3.org/2002/07/owl#', nameset={
    'sameAs',
})

# `gather.Text` uses an iri to identify language;
# here is a probably-reliable way to express IETF
# language tags in iri form
IANA_LANGUAGE_REGISTRY_IRI = (
    'https://www.iana.org/assignments/language-subtag-registry#'
)
IANA_LANGUAGE = IriNamespace(
    f'{IANA_LANGUAGE_REGISTRY_IRI}#',
    namestory=lambda: (
        Text.new('lang', language_iris={IANA_LANGUAGE['en-US']}),
        Text.new('language', language_iris={IANA_LANGUAGE['en-US']}),
        Text.new('language tag', language_iris={IANA_LANGUAGE['en-US']}),
        Text.new((
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
    _blarg_some_focus = Focus.new(BLARG.asome, type_iris=BLARG.SomeType)
    _blarg_nother_focus = Focus.new(BLARG.another, type_iris=BLARG.AnotherType)

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
                    Text.new(
                        'my-subvocab',
                        language_iris={IANA_LANGUAGE['en-US']},
                    ),
                    Text.new(
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
# to start gathering information, declare a `GatheringNorms` with
# pre-defined vocabularies, then write a `Gatherer` function for
# each iri in the vocab you want to gather about

class GatheringNorms:
    def __init__(
        self, *,
        namestory: Namestory,
        vocabulary: RdfTripleDictionary,
        focustype_iris: frozenset[str],
        gathering_kwargnames: typing.Optional[typing.Iterable[str]] = None,
    ):
        self.namestory = namestory
        self.vocabulary = vocabulary
        self.focustype_iris = ensure_frozenset(focustype_iris)
        self.gathering_kwargnames = ensure_frozenset(gathering_kwargnames)
        self.signup = GathererSignup()

    def assert_gathering_kwargnames(self, kwargnames: typing.Iterable[str]):
        # TODO: better messaging
        assert self.gathering_kwargnames == frozenset(kwargnames)

    def gatherer(self, *predicate_iris, focustype_iris=None):
        '''decorate gatherer functions with their iris of interest
        '''
        def _gatherer_decorator(gatherer_fn: Gatherer) -> TripleGatherer:
            _triple_gatherer = self._make_triple_gatherer(gatherer_fn)
            self.signup.add_gatherer(
                _triple_gatherer,
                predicate_iris=predicate_iris,
                focustype_iris=(focustype_iris or ()),
            )
            return _triple_gatherer
        return _gatherer_decorator

    def _make_triple_gatherer(self, gatherer_fn: Gatherer) -> TripleGatherer:
        @functools.wraps(gatherer_fn)
        def _triple_gatherer(focus: Focus, **kwargs):
            self.assert_gathering_kwargnames(kwargs.keys())
            for _triple_or_twople in gatherer_fn(focus, **kwargs):
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


class Gathering:
    def __init__(self, norms: GatheringNorms, **gathering_kwargs):
        norms.assert_gathering_kwargnames(gathering_kwargs.keys())
        self.norms = norms
        self._cache = GatherCache(norms.signup, gathering_kwargs)

    def ask(
        self,
        focus: typing.Union[str, Focus],
        pathset: MaybePredicatePathSet,
    ) -> typing.Iterable[RdfObject]:
        _focus = (
            self._cache.get_focus_by_iri(focus)
            if isinstance(focus, str)
            else focus
        )
        _tidy_pathset = tidy_predicate_pathset(pathset)
        self._cache.pull(_tidy_pathset, focus=_focus)
        return self._cache.peek(_tidy_pathset, focus=_focus)

    def leaf_a_record(self, *, pls_copy=False) -> RdfTripleDictionary:
        return (
            copy.deepcopy(self._cache.tripledict)
            if pls_copy
            else types.MappingProxyType(self._cache.tripledict)
        )


class GatherCache:
    tripledict: RdfTripleDictionary
    _gathers_done: set[tuple[Gatherer, Focus]]
    _focus_set: set[Focus]

    def __init__(self, gatherer_signup, gathering_kwargs):
        self._signup = gatherer_signup
        self._gathering_kwargs = gathering_kwargs
        self.reset()

    def reset(self):
        self.tripledict = dict()
        self._gathers_done = set()
        self._focus_set = set()

    def peek(
        self, pathset: MaybePredicatePathSet, *,
        focus: typing.Union[Focus, str],
    ) -> typing.Iterable[RdfObject]:
        '''peek: yield information already gathered
        '''
        if isinstance(focus, Focus):
            _focus_iri = focus.single_iri()
        elif isinstance(focus, str):
            _focus_iri = focus
        else:
            raise ValueError(
                f'expected focus to be str or Focus or None (got {focus})'
            )
        _tidy_pathset = tidy_predicate_pathset(pathset)
        for _predicate_iri, _next_pathset in _tidy_pathset.items():
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

    def pull(self, pathset: MaybePredicatePathSet, *, focus: Focus):
        '''pull: gather information (unless already gathered)
        '''
        _tidy_pathset = tidy_predicate_pathset(pathset)
        self.__maybe_gather(focus, _tidy_pathset.keys())
        for _predicate_iri, _next_pathset in _tidy_pathset.items():
            if _next_pathset:
                for _obj in self.peek(_predicate_iri, focus=focus):
                    try:
                        _next_focus = self.get_focus_by_iri(_obj)
                    except ValueError:
                        continue
                    else:  # recursion:
                        self.pull(_next_pathset, focus=_next_focus)

    def get_focus_by_iri(self, iri: str):
        try:
            _type_iris = self.tripledict[iri][RDF.type]
        except KeyError:
            raise ValueError(f'found no type for "{iri}"')
        try:
            _same_iris = self.tripledict[iri][OWL.sameAs]
        except KeyError:
            _iris = {iri}
        else:
            _iris = {iri, *_same_iris}
        return Focus.new(iris=_iris, type_iris=_type_iris)

    def __already_done(
            self, gatherer: Gatherer, focus: Focus, *,
            pls_mark_done=True,
    ) -> bool:
        gatherkey = (gatherer, focus)
        is_done = (gatherkey in self._gathers_done)
        if pls_mark_done and not is_done:
            self._gathers_done.add(gatherkey)
        return is_done

    def __maybe_gather(self, focus, predicate_iris):
        self.__add_focus(focus)
        for gatherer in self._signup.get_gatherers(focus, predicate_iris):
            if not self.__already_done(gatherer, focus, pls_mark_done=True):
                for triple in gatherer(focus, **self._gathering_kwargs):
                    self.__add_triple(triple)

    def __add_focus(self, focus: Focus):
        if focus not in self._focus_set:
            self._focus_set.add(focus)
            for triple in focus.as_rdf_tripleset():
                self.__add_triple(triple)

    def __maybe_unwrap_focus(self, maybefocus: typing.Union[Focus, RdfObject]):
        if isinstance(maybefocus, Focus):
            self.__add_focus(maybefocus)
            return maybefocus.single_iri()
        return maybefocus

    def __add_triple(self, triple: RdfTriple):
        (_subj, _pred, _obj) = triple
        _subj = self.__maybe_unwrap_focus(_subj)
        _obj = self.__maybe_unwrap_focus(_obj)
        (
            self.tripledict
            .setdefault(_subj, dict())
            .setdefault(_pred, set())
            .add(_obj)
        )


class GathererSignup:
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
            Text.new(
                'blarg',
                language_iris={BLARG.myLanguage},
            ),
            Text.new(
                'blargl blarg',
                language_iris={BLARG.myLanguage},
            ),
            Text.new(
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
        gathering_kwargnames={'hello'},
    )

    @BlargAtheringNorms.gatherer(BLARG.greeting)
    def blargather_greeting(focus: Focus, *, hello):
        yield (BLARG.greeting, Text.new(
            'kia ora',
            language_iris={IANA_LANGUAGE.mi},
        ))
        yield (BLARG.greeting, Text.new(
            'hola',
            language_iris={IANA_LANGUAGE.es},
        ))
        yield (BLARG.greeting, Text.new(
            'hello',
            language_iris={IANA_LANGUAGE.en},
        ))
        yield (BLARG.greeting, Text.new(
            hello,
            language_iris={BLARG.Dunno},
        ))

    @BlargAtheringNorms.gatherer(focustype_iris={BLARG.SomeType})
    def blargather_focustype(focus: Focus, *, hello):
        assert BLARG.SomeType in focus.type_iris
        yield (BLARG.number, len(focus.iris))

    @BlargAtheringNorms.gatherer(BLARG.yoo)
    def blargather_yoo(focus: Focus, *, hello):
        if focus == _blarg_some_focus:
            yield (BLARG.yoo, _blarg_nother_focus)
        else:
            yield (BLARG.yoo, _blarg_some_focus)

    class GatheringExample(unittest.TestCase):
        def test_gathering_declaration(self):
            self.assertEqual(
                BlargAtheringNorms.signup.get_gatherers(
                    _blarg_some_focus,
                    {BLARG.greeting},
                ),
                {blargather_greeting, blargather_focustype},
            )
            self.assertEqual(
                BlargAtheringNorms.signup.get_gatherers(_blarg_some_focus, {}),
                {blargather_focustype},
            )
            self.assertEqual(
                BlargAtheringNorms.signup.get_gatherers(
                    _blarg_nother_focus,
                    {BLARG.greeting},
                ),
                {blargather_greeting},
            )
            self.assertEqual(
                BlargAtheringNorms.signup.get_gatherers(
                    _blarg_nother_focus,
                    {BLARG.greeting, BLARG.yoo},
                ),
                {blargather_greeting, blargather_yoo},
            )
            self.assertEqual(
                BlargAtheringNorms.signup.get_gatherers(
                    _blarg_nother_focus,
                    {},
                ),
                set(),
            )

        def test_blargask(self):
            blargAthering = Gathering(norms=BlargAtheringNorms, hello='haha')
            self.assertEqual(
                set(blargAthering.ask(_blarg_some_focus, BLARG.greeting)),
                {
                    Text.new('kia ora', language_iris={IANA_LANGUAGE.mi}),
                    Text.new('hola', language_iris={IANA_LANGUAGE.es}),
                    Text.new('hello', language_iris={IANA_LANGUAGE.en}),
                    Text.new('haha', language_iris={BLARG.Dunno}),
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

try:
    import dataclasses
except ImportError:
    logger.info(
        'gather.py: dataclasses not available; omitting dataclass utilities',
    )
else:
    def dataclass_as_twoples(
        dataclass_instance,
        iri_by_fieldname: dict,
    ) -> typing.Iterable[RdfTwople]:
        for dataclass_field in dataclasses.fields(dataclass_instance):
            field_value = getattr(
                dataclass_instance,
                dataclass_field.name,
                None,
            )
            if field_value is not None:
                try:
                    yield (iri_by_fieldname[dataclass_field.name], field_value)
                except KeyError:
                    pass
                field_iris = dataclass_field.metadata.get(OWL.sameAs, ())
                for field_iri in field_iris:
                    yield (field_iri, field_value)

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
