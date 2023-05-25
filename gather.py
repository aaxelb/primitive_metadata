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
    'Namestory',
    'IriNamespace',
    'Infobasket',
)

# only built-in imports
import contextlib
import copy
import datetime
import functools
import itertools
import types
import typing

if __debug__:  # examples/tests thru-out, wrapped in `__debug__`
    # run tests with the command `python3 -m unittest gather.py`
    # (or discard tests with `-O` or `-OO` command-line options)
    import unittest


class Text(typing.NamedTuple):
    unicode_text: str
    language_iris: frozenset[str]
    # note: allow any IRI to identify a text language
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


###
# here are some type declarations to describe how this toolkit represents a
# particular subset of RDF concepts [https://www.w3.org/TR/rdf11-concepts/]
# using (mostly) immutable python primitives
RdfSubject = str    # IRI (not a blank node)
RdfPredicate = str  # IRI
RdfObject = typing.Union[
    str,            # IRI references as plain strings
    Text,           # language iris required for Text
    int, float,     # use primitives for numeric data
    datetime.date,  # use date and datetime built-ins
    frozenset,      # blanknodes as frozenset[twople]
]
RdfTriple = tuple[RdfSubject, RdfPredicate, RdfObject]
RdfTwople = tuple[RdfPredicate, RdfObject]  # implicit subject
RdfBlanknode = frozenset[RdfTwople]

# an RDF graph as a dictionary of dictionaries
# note: these are the only mutable "Rdf" types
RdfTwopleDictionary = dict[RdfPredicate, set[RdfObject]]
RdfDictionary = dict[RdfSubject, RdfTwopleDictionary]


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


def freeze_blanknode(twople_dict: RdfTwopleDictionary) -> RdfBlanknode:
    '''build a "blank node" frozenset of twoples (rdf triples without subjects)
    '''
    return frozenset(
        (pred, obj)
        for pred, obj_set in twople_dict.items()
        for obj in obj_set
    )


def unfreeze_blanknode(blanknode: RdfBlanknode) -> RdfTwopleDictionary:
    '''build a "twople dictionary" of RDF objects indexed by predicate

    @param blanknode: frozenset of (str, obj) twoples
    @returns: dict[str, set] built from blanknode twoples
    '''
    twople_dict = {}
    for predicate_iri, obj in blanknode:
        twople_dict.setdefault(predicate_iri, set()).add(obj)
    return twople_dict


def looks_like_rdf_dictionary(rdf_dictionary) -> bool:
    if not isinstance(rdf_dictionary, dict):
        return False
    for subj, twople_dict in rdf_dictionary.items():
        if not (isinstance(subj, str) and isinstance(twople_dict, dict)):
            return False
        for pred, obj_set in twople_dict.items():
            if not (isinstance(pred, str) and isinstance(obj_set, set)):
                return False
            if not all(isinstance(obj, RdfObject) for obj in obj_set):
                return False
    return True


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
    iris: frozenset[str]  # synonymous persistent identifiers in IRI form
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
        iri = self.single_iri()
        for type_iri in self.type_iris:
            yield (iri, RDF.type, type_iri)
        for same_iri in self.iris:
            if same_iri != iri:
                yield (iri, OWL.sameAs, same_iri)


###
# a tuple of language-text with increasing length-cap
# choose which name to use based on the space available
# (don't worry, long Texts can/will be only referenced by checksum (...TODO))
Namestory = tuple['Text', ...]


def _namestory_sizes() -> typing.Iterable[int]:
    '''infinite generator of increasing numbers

    (why not fibonacci numbers starting at thirteen?)
    '''
    last_fib = 5
    this_fib = 8
    while True:
        next_fib = this_fib + last_fib
        last_fib = this_fib
        this_fib = next_fib
        yield this_fib


def _is_valid_namestory(namestory: Namestory):
    return (
        isinstance(namestory, tuple)
        and all(
            (
                isinstance(nametext, Text)
                and (len(nametext.text) <= maxlen)
            )
            for nametext, maxlen in zip(
                namestory,
                _namestory_sizes(),
            )
        )
    )


###
# for using IRIs without having to type out full IRIs
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

# `gather.Text` uses an IRI to identify language;
# here is a probably-reliable way to express IETF
# language tags in IRI form
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
    # triples with `None` in any position are silently discarded
    tuple[
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


NormalizedPredicateShape = dict[RdfPredicate, 'PredicateShape']
PredicateShape = typing.Union[
    None,
    str,
    NormalizedPredicateShape,
    typing.Iterable[str],
]


def normalize_predicate_shape(
    predicate_shape: PredicateShape,
) -> NormalizedPredicateShape:
    if not predicate_shape:
        return {}
    if isinstance(predicate_shape, dict):
        return predicate_shape  # do not normalize values
    if isinstance(predicate_shape, str):
        return {predicate_shape: None}
    # assume Iterable[str]
    return {
        predicate_iri: None
        for predicate_iri in predicate_shape
    }


###
# to start gathering information, declare a `GatheringNorms` with
# pre-defined vocabularies, then write a `Gatherer` function for
# each iri in the vocab you want to gather about

class GatheringNorms:
    def __init__(
        self, *,
        namestory: Namestory,
        vocabulary: RdfDictionary,
        focustype_iris: frozenset[str],
    ):
        self.namestory = namestory
        self.vocabulary = vocabulary
        self.focustype_iris = ensure_frozenset(focustype_iris)
        self.signup = GathererSignup()

    def gatherer(self, *predicate_iris, focustype_iris=None):
        '''decorate gatherer functions with their iris of interest
        '''
        def gatherer_decorator(gatherer_fn: Gatherer) -> TripleGatherer:
            tidy_gatherer = self._tidy_gatherer(gatherer_fn)
            self.signup.add_gatherer(
                tidy_gatherer,
                predicate_iris=predicate_iris,
                focustype_iris=(focustype_iris or ()),
            )
            return tidy_gatherer
        return gatherer_decorator

    def _tidy_gatherer(self, gatherer_fn: Gatherer) -> TripleGatherer:
        @functools.wraps(gatherer_fn)
        def _gatherer(focus: Focus):
            for triple_or_twople in gatherer_fn(focus):
                if len(triple_or_twople) == 3:
                    (subj, pred, obj) = triple_or_twople
                elif len(triple_or_twople) == 2:
                    subj = focus.single_iri()
                    (pred, obj) = triple_or_twople
                else:
                    raise ValueError(
                        f'expected triple or twople (got {triple_or_twople})',
                    )
                triple = (subj, pred, obj)
                if None not in triple:
                    yield triple
        return _gatherer


class Gathering:
    def __init__(self, norms: GatheringNorms):
        self.norms = norms
        self.cache = GatherCache(norms.signup)

    def infobasket(self, focus: Focus) -> 'Infobasket':
        return Infobasket(gathering=self, focus=focus)

    def leaf__dictionary(self, *, pls_copy=False) -> RdfDictionary:
        return (
            copy.deepcopy(self.cache._triples_gathered)
            if pls_copy
            else types.MappingProxyType(self.cache._triples_gathered)
        )

    def leaf__tripleset(self) -> typing.Iterable[tuple]:
        yield from self.cache.as_rdf_tripleset()

    def leaf__html(self, *, focus) -> str:
        # TODO: microdata, css, language tags
        from xml.etree.ElementTree import TreeBuilder, tostring
        html_builder = TreeBuilder()
        # define some local helpers:

        @contextlib.contextmanager
        def _nest(tag_name, attrs=None):
            html_builder.start(tag_name, attrs or {})
            yield
            html_builder.end(tag_name)

        def _leaf(tag_name, *, text=None, attrs=None):
            html_builder.start(tag_name, attrs or {})
            if text is not None:
                html_builder.data(text)
            html_builder.end(tag_name)

        def _twoples(twoples: RdfTwopleDictionary, attrs=None):
            with _nest('ul', (attrs or {})):
                for pred, obj_set in twoples.items():
                    with _nest('li'):
                        _leaf('span', text=pred)  # TODO: <a href>
                        with _nest('ul'):
                            for obj in obj_set:
                                with _nest('li'):
                                    _obj(obj)

        def _obj(obj: RdfObject):
            if isinstance(obj, frozenset):
                _twoples(unfreeze_blanknode(obj))
            elif isinstance(obj, Text):
                # TODO language tag
                _leaf('span', text=str(obj))
            elif isinstance(obj, str):
                # TODO link to anchor on this page?
                _leaf('a', text=obj)
            elif isinstance(obj, (float, int, datetime.date)):
                # TODO datatype?
                _leaf('span', text=str(obj))

        # now use those helpers to build an <article>
        # with all the info gathered thru this Infobasket
        with _nest('article'):
            _leaf('h1', text=str(self.focus))  # TODO: shortened display name
            for subj, predicate_dict in self.cache._triples_gathered.items():
                with _nest('section'):
                    _leaf('h2', text=subj)
                    _twoples(predicate_dict)
        # and serialize as str
        return tostring(
            html_builder.close(),
            encoding='unicode',
            method='html',
        )

    def leaf__turtle(self) -> str:
        rdflib_graph = self.leaf__rdflib()
        # TODO: sort blocks, focus first
        return rdflib_graph.serialize(format='turtle')

    def leaf__rdflib(self):
        try:
            import rdflib
        except ImportError:
            raise Exception('Infobasket.leaf__rdflib depends on rdflib')

        def _yield_rdflib(
            subj: RdfSubject,
            pred: RdfPredicate,
            obj: RdfObject,
        ):
            rdflib_subj = rdflib.URIRef(subj)
            rdflib_pred = rdflib.URIRef(pred)
            if isinstance(obj, str):
                yield (rdflib_subj, rdflib_pred, rdflib.URIRef(obj))
            elif isinstance(obj, Text):
                assert len(obj.language_iris), (
                    f'expected {obj} to have language_iris'
                )
                for language_iri in obj.language_iris:
                    try:
                        language_tag = IriNamespace.without_namespace(
                            language_iri,
                            namespace=IANA_LANGUAGE,
                        )
                    except ValueError:  # got a language iri
                        # datatype can be any IRI; link your own language
                        literal_text = rdflib.Literal(
                            obj.unicode_text,
                            datatype=obj.language_iri,
                        )
                    else:  # got a language tag
                        literal_text = rdflib.Literal(
                            obj.unicode_text,
                            language=language_tag,
                        )
                    yield (rdflib_subj, rdflib_pred, literal_text)
            elif isinstance(obj, (int, float, datetime.date)):
                yield (rdflib_subj, rdflib_pred, rdflib.Literal(obj))
            elif isinstance(obj, frozenset):
                # may result in duplicates -- don't do shared blanknodes
                blanknode = rdflib.BNode()
                for blankpred, blankobj in obj:
                    yield from _yield_rdflib(blanknode, blankpred, blankobj)
            else:
                raise ValueError(f'should be RdfObject, got {obj}')

        leafed_graph = rdflib.Graph()  # TODO: namespace prefixes?
        for (subj, pred, obj) in self.leaf__tripleset():
            for rdflib_triple in _yield_rdflib(subj, pred, obj):
                leafed_graph.add(rdflib_triple)
        return leafed_graph


class GatherCache:
    _triples_gathered: RdfDictionary
    _gathers_done: set[tuple[Gatherer, Focus]]
    _focus_set: set[Focus]

    def __init__(self, gatherer_signup):
        self._signup = gatherer_signup
        self.reset()

    def reset(self):
        self._triples_gathered = dict()
        self._gathers_done = set()
        self._focus_set = set()

    def as_rdf_tripleset(self) -> typing.Iterable[RdfTriple]:
        for subj, predicate_dict in self._triples_gathered.items():
            for pred, obj_set in predicate_dict.items():
                for obj in obj_set:
                    yield (subj, pred, obj)

    def peek(
        self, predicate_shape, *,
        focus: typing.Union[Focus, str],
    ) -> typing.Iterable[RdfObject]:
        '''peek: yield information already gathered
        '''
        if isinstance(focus, Focus):
            focus_iri = focus.single_iri()
        elif isinstance(focus, str):
            focus_iri = focus
        else:
            raise ValueError(
                f'expected focus to be str or Focus or None (got {focus})'
            )
        predicate_dict = normalize_predicate_shape(predicate_shape)
        for predicate_iri, next_shape in predicate_dict.items():
            object_set = (
                self._triples_gathered
                .get(focus_iri, {})
                .get(predicate_iri, set())
            )
            if next_shape:
                for obj in object_set:
                    if isinstance(obj, str):
                        yield from self.peek(next_shape, focus=obj)
            else:
                yield from object_set

    def pull(self, predicate_shape, *, focus: Focus):
        '''pull: gather information (unless already gathered)
        '''
        predicate_dict = normalize_predicate_shape(predicate_shape)
        self.__maybe_gather(focus, predicate_dict.keys())
        for predicate_iri, next_shape in predicate_dict.items():
            if next_shape:
                for obj in self.peek(predicate_iri, focus=focus):
                    try:
                        next_focus = self.get_focus_by_iri(obj)
                    except ValueError:
                        continue
                    else:  # recursion:
                        self.pull(next_shape, focus=next_focus)

    def get_focus_by_iri(self, iri):
        try:
            type_iris = self._triples_gathered[iri][RDF.type]
        except KeyError:
            raise ValueError(f'found no type for "{iri}"')
        try:
            same_iris = self._triples_gathered[iri][OWL.sameAs]
        except KeyError:
            iris = {iri}
        else:
            iris = {iri, *same_iris}
        return Focus.new(iris=iris, type_iris=type_iris)

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
                for triple in gatherer(focus):
                    self.__add_triple(triple)

    def __add_focus(self, focus: Focus):
        if focus not in self._focus_set:
            self._focus_set.add(focus)
            for triple in focus.as_rdf_tripleset():
                self.__add_triple(triple)

    def __add_triple(self, triple: RdfTriple):
        (subj, pred, obj) = triple
        (
            self._triples_gathered
            .setdefault(subj, dict())
            .setdefault(pred, set())
            .add(obj)
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
        },
        focustype_iris={
            BLARG.SomeType,
            BLARG.AnotherType,
        },
    )

    @BlargAtheringNorms.gatherer(BLARG.greeting)
    def blargather_greeting(focus: Focus):
        yield (BLARG.greeting, Text.new(
            'kia ora',
            language_iris={IANA_LANGUAGE.mi},
        ))
        yield (BLARG.greeting, Text.new('hola', language_iris={IANA_LANGUAGE.es}))
        yield (BLARG.greeting, Text.new('hello', language_iris={IANA_LANGUAGE.en}))

    @BlargAtheringNorms.gatherer(focustype_iris={BLARG.SomeType})
    def blargather_focustype(focus: Focus):
        assert BLARG.SomeType in focus.type_iris
        yield (BLARG.number, len(focus.iris))

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
                    {},
                ),
                set(),
            )


class Infobasket:
    def __init__(self, gathering: Gathering, focus: Focus):
        self.gathering = gathering
        self.focus = focus
        self.gathering.cache

    def ask(
        self,
        predicate_shape: PredicateShape,
    ) -> typing.Iterable[RdfObject]:
        shape = normalize_predicate_shape(predicate_shape)
        self.gathering.cache.pull(shape, focus=self.focus)
        yield from self.gathering.cache.peek(shape, focus=self.focus)

    def _ensure_focus(self, maybe_focus):
        if maybe_focus is None:
            return self.focus
        if isinstance(maybe_focus, Focus):
            return maybe_focus
        if isinstance(maybe_focus, str):
            return self.gathering.cache.get_focus_by_iri(maybe_focus)
        raise ValueError(
            f'_ensure_focus expected Focus, str, or None (got {maybe_focus})',
        )

    def __contains__(self, *args, **kwargs):
        raise NotImplementedError  # prevent infinite loop from `foo in basket`


if __debug__:
    class BasketExample(unittest.TestCase):
        def test_blargbasket(self):
            blargAthering = Gathering(norms=BlargAtheringNorms)
            blargsket = blargAthering.infobasket(_blarg_some_focus)
            self.assertEqual(
                set(blargsket.ask(BLARG.greeting)),
                {
                    Text.new('kia ora', language_iris={IANA_LANGUAGE.mi}),
                    Text.new('hola', language_iris={IANA_LANGUAGE.es}),
                    Text.new('hello', language_iris={IANA_LANGUAGE.en}),
                },
            )
            self.assertEqual(
                set(blargsket.ask(BLARG.unknownpredicate)),
                set(),
            )
