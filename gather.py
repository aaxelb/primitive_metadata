'''gather.py: a tiny toolkit for gathering information

mindset metaphor:
1. name a gathering
2. pose a question
3. leaf a record
'''
__all__ = ('Text', 'Focus', 'IriNamespace', 'Gathering', 'Basket')

# standard-library imports
import contextlib
import copy
import dataclasses  # python 3.10+ (could NamedTuple for better support?)
import datetime
import functools
import itertools
import types
import typing

if __debug__:  # examples/tests thru-out, wrapped in `__debug__`
    # run tests with the command `python3 -m unittest gather.py`
    # (or discard tests with `-O` or `-OO` command-line options)
    import unittest


###
# here are some type declarations to describe how this toolkit implements a
# particular subset of RDF concepts (https://www.w3.org/TR/rdf11-concepts/)
# using (mostly) immutable python primitives
RdfSubject = str    # IRI (not a blank node)
RdfPredicate = str  # IRI
RdfObject = typing.Union[
    str,             # IRI references as plain strings
    'Text',          # language tags required for Text
    int, float,      # use primitives for numeric data
    datetime.date,   # use date and datetime built-ins
    'RdfBlankNode',  # reduce blank nodes to objects
]
RdfTriple = tuple[RdfSubject, RdfPredicate, RdfObject]
RdfTwople = tuple[RdfPredicate, RdfObject]  # implicit subject
RdfBlankNode = frozenset[RdfTwople]

# an RDF graph as a dictionary of dictionaries
# note: these are the only mutable "Rdf" types
RdfTwopleDictionary = dict[RdfPredicate, set[RdfObject]]
RdfDictionary = dict[RdfSubject, RdfTwopleDictionary]


def freeze_twoples(twople_dict: RdfTwopleDictionary) -> RdfBlankNode:
    return frozenset(
        (pred, obj)
        for pred, obj_set in twople_dict.items()
        for obj in obj_set
    )


def unfreeze_twoples(twoples: RdfBlankNode) -> RdfTwopleDictionary:
    twople_dict = {}
    for pred, obj in twoples:
        twople_dict.setdefault(pred, set()).add(obj)
    return twople_dict


###
# a "gatherer" function yields information about a given focus
GathererYield = typing.Union[
    RdfTriple,  # using the rdf triple as basic unit of information
    RdfTwople,  # may omit subject (assumed iri of the given focus)
    # may yield a tuple containing `None`; will silently discard it
    tuple[
        typing.Optional[RdfSubject],
        typing.Optional[RdfPredicate],
        typing.Optional[RdfObject],
    ],
    tuple[
        typing.Optional[RdfPredicate],
        typing.Optional[RdfObject],
    ],
]
Gatherer = typing.Callable[['Focus'], typing.Iterable[GathererYield]]
# when decorated, the yield is tidied into triples
DecoratedGatherer = typing.Callable[['Focus'], typing.Iterable[RdfTriple]]


@dataclasses.dataclass(frozen=True)
class Text:
    unicode_text: str
    # note: allow any IRI to identify a text language
    # (if you wish to constrain to IETF language tags
    # at https://www.rfc-editor.org/rfc/bcp/bcp47.txt
    # use the defined IANA_LANGUAGE namespace, below)
    language_iri: str = dataclasses.field(kw_only=True)

    def checksum_iri(self) -> str:
        raise NotImplementedError('TODO')


@dataclasses.dataclass(frozen=True)
class Focus:
    iri: str
    type_iris: frozenset[str] = dataclasses.field(kw_only=True)

    def __post_init__(self):
        # ensure frozen/hashable
        assert isinstance(self.iri, str)
        if not isinstance(self.type_iris, frozenset):
            # can initialize `type_iris` with str or any iterable
            frozen_type_iris = (
                frozenset((self.type_iris,))
                if isinstance(self.type_iris, str)
                else frozenset(self.type_iris)
            )
            # using object.__setattr__ because frozen dataclass
            object.__setattr__(self, 'type_iris', frozen_type_iris)

    def as_rdf_tripleset(self) -> typing.Iterable[RdfTriple]:
        for type_iri in self.type_iris:
            yield (self.iri, RDF.type, type_iri)


if __debug__:
    class TextExamples(unittest.TestCase):
        def test_blurb(self):
            my_blurb = Text(
                'blurbl di blarbl ga',
                language_iri=BLARG['my-language'],
            )
            self.assertIsInstance(my_blurb.unicode_text, str)
            self.assertEqual(my_blurb.unicode_text, 'blurbl di blarbl ga')
            self.assertEqual(str(my_blurb), 'blurbl di blarbl ga')
            self.assertEqual(
                my_blurb.language_iri,
                'https://blarg.example/my-language',
            )


class IriNamespace:
    '''IriNamespace: for building and using IRIs easily in python code
    (ideally IRLs ("L" for "Locator", an IRI which locates an internet
    document (like via `http`/`https`) and resolves to a document that
    makes enough sense given context), but this toolkit does not check
    for locatorishness and treats any IRI like an IRN ("N" for "Name")
    '''
    def __init__(self, iri: str):  # TODO: name/namestory
        if ':' not in iri:
            raise ValueError(
                # trying out `Text` for translatable error messaging
                Text(f'expected iri to have a ":" (got "{iri}")',
                     language_iri=IANA_LANGUAGE.en),
            )
        # assume python's "private name mangling" will avoid conflicts
        self.__iri = iri

    @classmethod
    def namespace_name(cls, namespace: 'IriNamespace'):
        return namespace.__name

    @classmethod
    def namespace_description(cls, namespace: 'IriNamespace'):
        return namespace.__description

    @classmethod
    def without_namespace(cls, iri: str, *, namespace: 'IriNamespace'):
        if not iri.startswith(namespace.__iri):
            raise ValueError(f'"{iri}" should start with "{namespace.__iri}"')
        return iri[len(namespace.__iri):]

    def __getitem__(self, attrname: str) -> str:
        '''IriNamespace.__getitem__: build iri with `SQUARE['bracket']` syntax
        '''
        return ''.join((self.__iri, attrname))

    def __getattr__(self, attrname: str) -> str:
        '''IriNamespace.__getattr__: build iri with `DOT.dot` syntax
        '''
        return self.__getitem__(attrname)

    def __contains__(self, iri: str):
        return iri.startswith(self.__iri)

    def __str__(self):
        return self.__iri

    def __repr__(self):
        return f'{self.__class__.__qualname__}("{self.__iri}")'

    def __hash__(self):
        return hash(self.__iri)


RDF = IriNamespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#')

# `gather.Text` uses an IRI to identify language;
# use IANA_LANGUAGE to express IETF language tags
IANA_LANGUAGE_REGISTRY_IRI = (
    'https://www.iana.org/assignments/language-subtag-registry#'
)
IANA_LANGUAGE = IriNamespace(
    f'{IANA_LANGUAGE_REGISTRY_IRI}#',
    name=Text('language', language_iri=f'{IANA_LANGUAGE_REGISTRY_IRI}#en-US'),
    description=Text((
        'allow expressing a "language tag" (as required by RDF and'
        ' defined by IETF ( https://www.ietf.org/rfc/bcp/bcp47.txt'
        ' ) as an IRI, using a URL for a IANA Registry followed by'
        ' "#" and the language tag "tag-SUBTAG"'
    ), language_iri=f'{IANA_LANGUAGE_REGISTRY_IRI}#en-US'),
)

if __debug__:
    BLARG = IriNamespace(
        'https://blarg.example/',
        name=Text(
            'blarg',
            language_iris={IANA_LANGUAGE['en-US']},
        ),
        description={
            Text(
                'blargl blarg',
                language_iris={'https://blarg.example/blargl'},
            ),
        },
    )
    _blarg_some_focus = Focus(BLARG.asome, type_iris=BLARG.SomeType)
    _blarg_nother_focus = Focus(BLARG.another, type_iris=BLARG.AnotherType)

    class ExampleIriNamespaceUsage(unittest.TestCase):
        def test___contains__(self):
            self.assertEqual(BLARG.foo, 'https://blarg.example/foo')
            self.assertEqual(BLARG.blip, BLARG['blip'])
            self.assertEqual(BLARG['gloo.my'], 'https://blarg.example/gloo.my')
            self.assertIn('https://blarg.example/booboo', BLARG)
            self.assertNotIn('https://gralb.example/booboo', BLARG)
            self.assertNotIn('blip', BLARG)
            my_subvocab = IriNamespace(
                BLARG['my-subvocab'],
                name=Text(
                    'my-subvocab',
                    language_iri=IANA_LANGUAGE['en-US'],
                ),
                description=Text(
                    'a namespace nested within the BLARG namespace',
                    language_iris=IANA_LANGUAGE['en-US'],
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


class Gathering:
    '''Gathering: for gatherers to decorate themself by interest
    '''
    def __init__(self, gathering_iri: str):
        self.iri = gathering_iri
        # see `_add_gatherer` for how these gatherer dictionaries are used
        self._by_predicate = {}
        self._by_focustype = {}
        self._for_any_predicate = set()
        self._for_any_focustype = set()

    def gatherer(self, *,
                 predicate_iris=(),
                 focustype_iris=(),
                 ):
        '''decorate gatherer functions with their iris of interest
        '''
        def gatherer_decorator(gatherer_fn: Gatherer) -> DecoratedGatherer:
            decorated_gatherer = self._decorated_gatherer(gatherer_fn)
            self._add_gatherer(
                decorated_gatherer,
                predicate_iris=predicate_iris,
                focustype_iris=focustype_iris,
            )
            return decorated_gatherer
        return gatherer_decorator

    def get_gatherers(self, *,
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

    def _add_gatherer(self, gatherer, *,
                      predicate_iris,
                      focustype_iris,
                      ):
        for iris, gatherers_by_iri, gatherers_for_any_iri in (
            (predicate_iris, self._by_predicate, self._for_any_predicate),
            (focustype_iris, self._by_focustype, self._for_any_focustype),
        ):
            if not iris:
                gatherers_for_any_iri.add(gatherer)
            else:
                for iri in iris:
                    try:
                        gatherers_by_iri[iri].add(gatherer)
                    except KeyError:
                        gatherers_by_iri[iri] = {gatherer}

    def _decorated_gatherer(self, gatherer_fn: Gatherer) -> DecoratedGatherer:
        @functools.wraps(gatherer_fn)
        def decorated_gatherer(focus: Focus):
            for triple_or_twople in gatherer_fn(focus):
                if len(triple_or_twople) == 3:
                    (subj, pred, obj) = triple_or_twople
                elif len(triple_or_twople) == 2:
                    subj = focus.iri
                    (pred, obj) = triple_or_twople
                else:
                    raise ValueError(
                        f'expected triple or twople (got {triple_or_twople})',
                    )
                triple = (subj, pred, obj)
                if None not in triple:
                    yield triple
        return decorated_gatherer


if __debug__:
    BlargAthering = Gathering(BLARG.mygathering)

    @BlargAthering.gatherer(predicate_iris={BLARG.greeting})
    def blargather_predicate(focus: Focus):
        yield (BLARG.greeting, Text('kia ora', language_iri=IANA_LANGUAGE.mi))
        yield (BLARG.greeting, Text('hola', language_iri=IANA_LANGUAGE.es))
        yield (BLARG.greeting, Text('hello', language_iri=IANA_LANGUAGE.en))

    def _blargather_iri_to_object(focus):
        return {'nuuumber': len(focus.iri)}

    @BlargAthering.gatherer(focustype_iris={BLARG.SomeType})
    def blargather_focustype(focus: Focus):
        assert BLARG.SomeType in focus.type_iris
        my_blarg = _blargather_iri_to_object(focus)
        yield (BLARG.number, my_blarg['nuuumber'])

    class GatheringExample(unittest.TestCase):
        def test_gathering_declaration(self):
            self.assertEqual(BlargAthering.iri, BLARG.mygathering)
            self.assertEqual(
                BlargAthering.get_gatherers(_blarg_some_focus,
                                            {BLARG.greeting}),
                {blargather_predicate, blargather_focustype},
            )
            self.assertEqual(
                BlargAthering.get_gatherers(_blarg_some_focus, {}),
                {blargather_focustype},
            )
            self.assertEqual(
                BlargAthering.get_gatherers(_blarg_nother_focus,
                                            {BLARG.greeting}),
                {blargather_predicate},
            )
            self.assertEqual(
                BlargAthering.get_gatherers(_blarg_nother_focus, {}),
                set(),
            )


class Basket:
    __gathered: RdfDictionary

    def __init__(self, gathering: Gathering, focus: Focus):
        self.gathering = gathering
        self.focus = focus
        self.reset()

    def reset(self):
        self.__gathered = dict()
        self.__gathers_done = set()

    def pull(self, predicate_shape, *,
             focus=None,
             ) -> typing.Iterable[RdfObject]:
        pull_focus = (focus or self.focus)
        if isinstance(predicate_shape, str):
            self.__maybe_gather(pull_focus, {predicate_shape})
            return self.peek(predicate_shape, focus=pull_focus)
        if isinstance(predicate_shape, dict):
            self.__maybe_gather(pull_focus, predicate_shape.keys())
            for predicate_iri, next_shape in predicate_shape.items():
                if not next_shape:
                    continue
                for obj in self.peek(predicate_iri, focus=pull_focus):
                    try:
                        next_focus = self.get_focus_by_iri(obj)
                    except ValueError:
                        continue
                    else:  # recursion:
                        self.pull(next_shape, focus=next_focus)
        else:  # assume iterable
            self.__maybe_gather(set(predicate_shape), focus=pull_focus)
            return self.peek(predicate_shape, focus=pull_focus)

    def peek(self, predicate_iri, *, focus=None) -> typing.Iterable[RdfObject]:
        if focus is None:
            focus_iri = self.focus.iri
        elif isinstance(focus, Focus):
            focus_iri = focus.iri
        elif isinstance(focus, str):
            focus_iri = focus
        else:
            raise ValueError(
                f'expected focus to be str or Focus or None (got {focus})'
            )
        yield from (
            self.__gathered
            .get(focus_iri, {})
            .get(predicate_iri, set())
        )

    def add(self, subj, predicate, obj):
        (
            self.__gathered
            .setdefault(subj, dict())
            .setdefault(predicate, set())
            .add(obj)
        )

    def get_focus_by_iri(self, iri):
        try:
            type_iris = self.__gathered[iri][RDF.type]
        except KeyError:
            raise ValueError(f'found no type for "{iri}"')
        else:
            return Focus(iri, type_iris=type_iris)

    def __maybe_gather(self, focus, predicate_iris):
        for gatherer in self.gathering.get_gatherers(focus, predicate_iris):
            gatherkey = (gatherer, focus)
            if gatherkey not in self.__gathers_done:
                self.__gathers_done.add(gatherkey)
                for (subj, pred, obj) in gatherer(focus):
                    self.add(subj, pred, obj)

    def leaf__dictionary(self, *, pls_copy=False) -> RdfDictionary:
        return (
            copy.deepcopy(self.__gathered)
            if pls_copy
            else types.MappingProxyType(self.__gathered)
        )

    def leaf__tripleset(self) -> typing.Iterable[tuple]:
        for subj, predicate_dict in self.__gathered.items():
            for pred, obj_set in predicate_dict.items():
                for obj in obj_set:
                    yield (subj, pred, obj)

    def leaf__html(self) -> str:
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
                _twoples(unfreeze_twoples(obj))
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
        # with all the info gathered thru this Basket
        with _nest('article'):
            _leaf('h1', text=str(self.focus))  # TODO: shortened display name
            for subj, predicate_dict in self.__gathered.items():
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
        return rdflib_graph.serialize(format='turtle')

    def leaf__rdflib(self):
        try:
            import rdflib
        except ImportError:
            raise GatherException(
                Text(
                    'Basket.leaf__rdflib depends on rdflib',
                    language_iri=IANA_LANGUAGE.en,
                ),
            )

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
                try:
                    language_tag = IriNamespace.without_namespace(
                        obj.language_iri,
                        namespace=IANA_LANGUAGE,
                    )
                except ValueError:
                    # datatype can be any IRI; link your own language
                    literal_text = rdflib.Literal(
                        obj.unicode_text,
                        datatype=obj.language_iri,
                    )
                else:
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


if __debug__:
    class BasketExample(unittest.TestCase):
        def test_blargbasket(self):
            blargsket = Basket(BlargAthering, _blarg_some_focus)
            self.assertEqual(
                set(blargsket.pull(BLARG.greeting)),
                {
                    Text('kia ora', language_iri=IANA_LANGUAGE.mi),
                    Text('hola', language_iri=IANA_LANGUAGE.es),
                    Text('hello', language_iri=IANA_LANGUAGE.en),
                },
            )
            self.assertEqual(
                set(blargsket.pull(BLARG.unknownpredicate)),
                set(),
            )



