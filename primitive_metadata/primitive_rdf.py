'''primitive_rdf.py: some rdf primitives implemented with python primitives

uses rdf concepts: https://www.w3.org/TR/rdf11-concepts/
'''
# only standard imports (python 3.? (TODO: specificity informed by testing))
import collections.abc
import contextlib
import dataclasses  # python3.7+
import datetime
import functools  # using functools.cache: python3.9+
import json
import logging
import operator
import types
from typing import Iterable, Iterator, Union, Optional, NamedTuple, Callable
import weakref

logger = logging.getLogger(__name__)


###
# RDF data represented using built-in or standard python types supporting
# most (but not all) RDF concepts [https://www.w3.org/TR/rdf11-concepts/]
RdfSubject = str    # iri string for a something
RdfPredicate = str  # iri string for a way to relate
RdfObject = Union[  # the object of relation may be any of:
    str,             # iri string for another something
    int, float,      # immutable python primitives
    datetime.date,   # date and datetime, too
    'RdfBlanknode',  # frozenset for blank nodes (acyclic)
    'Literal',       # namedtuple for explicit rdf literals
    'QuotedTriple',  # namedtuple for quoted rdf triples
    'QuotedGraph',   # namedtuple for quoted rdf graph
]
RdfTwople = tuple[RdfPredicate, RdfObject]
RdfTriple = tuple[RdfSubject, RdfPredicate, RdfObject]
RdfBlanknode = frozenset[RdfTwople]
RdfTripleSet = frozenset[RdfTriple]

# an RDF graph as a dictionary of dictionaries
# note: these are the only mutable "Rdf" types
RdfTwopleDictionary = dict[RdfPredicate, set[RdfObject]]
RdfTripleDictionary = dict[RdfSubject, RdfTwopleDictionary]

ReadonlyTwopleDictionary = collections.abc.Mapping[
    RdfPredicate,
    collections.abc.Collection[RdfObject],
]

# for defining branching paths of predicates from a focus
TidyPathset = dict[RdfPredicate, 'TidyPathset']
# (tho be flexible in public api: allow messier pathsets)
MessyPathset = Union[
    dict[RdfPredicate, 'MessyPathset'],
    Iterable['MessyPathset'],
    RdfPredicate,
    None,
]


###
# utility/helper functions for working with the "Rdf..." types above

def add_triple(tripledict: RdfTripleDictionary, triple: RdfTriple):
    (_subj, _pred, _obj) = triple
    (
        tripledict
        .setdefault(_subj, dict())
        .setdefault(_pred, set())
        .add(_obj)
    )


def tripledict_from_tripleset(tripleset: Iterable[RdfTriple]):
    _tripledict: RdfTripleDictionary = {}
    for _triple in tripleset:
        add_triple(_tripledict, _triple)
    return _tripledict


def ensure_frozenset(something) -> frozenset:
    '''convenience for building frozensets

    wrap a string in a frozenset
    >>> ensure_frozenset('foo')
    frozenset({'foo'})

    non-str iterables converted to frozensets
    >>> ensure_frozenset([])
    frozenset()
    >>> ensure_frozenset(['foo'])
    frozenset({'foo'})
    >>> _ab = ensure_frozenset(['a', 'b'])
    >>> type(_ab) is frozenset and _ab == {'b', 'a'}
    True
    >>> ensure_frozenset(['a','b']) == {'a', 'b'}
    True
    >>> _r = ensure_frozenset(range(5))
    >>> type(_r) is frozenset and _r == {4, 3, 2, 1, 0}
    True

    if given a frozenset, just return it (don't make a new frozenset)
    >>> ensure_frozenset(_r) is _r
    True
    '''
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


def blanknode(
    twopledict: Optional[RdfTwopleDictionary] = None,
) -> RdfBlanknode:
    '''build a "blank node" frozenset of twoples (rdf triples without subjects)

    >>> blanknode()
    frozenset()
    >>> blanknode({})
    frozenset()
    >>> _blank = blanknode({RDF.value: {RDF.Bag, RDF.Seq, RDF.Alt}})
    >>> type(_blank) is frozenset and _blank == {
    ...     (RDF.value, RDF.Bag),
    ...     (RDF.value, RDF.Seq),
    ...     (RDF.value, RDF.Alt),
    ... }
    True
    '''
    if twopledict:
        return frozenset(iter_twoples(twopledict))
    return frozenset()


def iter_twoples(twopledict: ReadonlyTwopleDictionary) -> Iterator[RdfTwople]:
    '''iterate thru twoples in the given twopledict

    >>> iter_twoples({})
    <generator object iter_twoples at 0x...>
    >>> set(iter_twoples({}))
    set()
    >>> set(iter_twoples({RDF.value: {RDF.Bag, RDF.Seq, RDF.Alt}})) == {
    ...     (RDF.value, RDF.Bag),
    ...     (RDF.value, RDF.Seq),
    ...     (RDF.value, RDF.Alt),
    ... }
    True
    '''
    for _pred, _objectset in twopledict.items():
        for _obj in _objectset:
            yield (_pred, _obj)


def twopledict_from_twopleset(
    twopleset: Iterable[RdfTwople],
) -> RdfTwopleDictionary:
    '''build a "twople dictionary" of RDF objects indexed by predicate

    >>> _tdict = twopledict_from_twopleset([
    ...     (RDF.type, RDF.Property),
    ...     (RDFS.range, RDF.Resource),
    ...     (RDFS.range, RDFS.Literal),
    ... ])
    >>> type(_tdict) is dict
    True
    >>> set(_tdict.keys()) == {RDFS.range, RDF.type}
    True
    >>> all(type(_object_set) is set for _object_set in _tdict.values())
    True
    >>> _tdict[RDF.type] == {RDF.Property}
    True
    >>> _tdict[RDFS.range] == {RDF.Resource, RDFS.Literal}
    True
    '''
    _twopledict: RdfTwopleDictionary = {}
    for _pred, _obj in twopleset:
        if _pred in _twopledict:
            _objectset = _twopledict[_pred]
        else:
            _objectset = _twopledict[_pred] = set()
        _objectset.add(_obj)
    return _twopledict


def smells_like_iri(something) -> bool:
    return isinstance(something, str)  # TODO: iri parsing?!


def smells_like_rdf_object(something) -> bool:
    return (
        isinstance(something, (
            int,
            float,
            datetime.date,
            Literal,
            QuotedTriple,
            QuotedGraph,
        ))
        or smells_like_iri(something)
        or smells_like_blanknode(something)
    )


def smells_like_blanknode(something) -> bool:
    return isinstance(something, frozenset) and all(
        smells_like_twople(_item) for _item in something
    )


def smells_like_twople(something) -> bool:
    try:
        _pred, _obj = something
    except ValueError:
        return False
    return isinstance(_pred, str) and smells_like_rdf_object(_obj)


def smells_like_rdf_tripledict(rdf_dictionary) -> bool:
    '''simple type-check for dict[str, dict[str, set[RdfObject]]]

    correct smells:
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type: {RDF.Property}}})
    True
    >>> smells_like_rdf_tripledict({})
    True

    not dictionaries:
    >>> smells_like_rdf_tripledict(None)
    False
    >>> smells_like_rdf_tripledict(7)
    False
    >>> smells_like_rdf_tripledict([2, 3])
    False

    dictionaries with wrong-smelling keys or values:
    >>> smells_like_rdf_tripledict({7: 9})
    False
    >>> smells_like_rdf_tripledict({RDF.type: 7})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {}})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type}})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type: [RDF.Property]}})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type: RDF.Property}})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type: RDF.Property}})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type: {RDF.Property: 7}}})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {7: {RDF.Property}}})
    False
    '''
    if not isinstance(rdf_dictionary, dict):
        return False
    for _subj, _twopledict in rdf_dictionary.items():
        if not _subj or not isinstance(_subj, str):
            return False
        if not _twopledict or not isinstance(_twopledict, dict):
            return False
        for _pred, _objectset in _twopledict.items():
            if not _pred or not isinstance(_pred, str):
                return False
            if not _objectset or not isinstance(_objectset, set):
                return False
            if not all(smells_like_rdf_object(_obj) for _obj in _objectset):
                return False
    return True


def iter_tripleset(
    tripledict: RdfTripleDictionary
) -> Iterator[RdfTriple]:
    '''yields all triples from the tripledict

    >>> iter_tripleset({})
    <generator object iter_tripleset at 0x...>
    >>> list(_)
    []
    >>> set(iter_tripleset({
    ...     RDF.type: {RDF.type: {RDF.Property}},
    ... })) == {(RDF.type, RDF.type, RDF.Property)}
    True
    >>> set(iter_tripleset({
    ...     RDF.type: {RDF.type: {RDF.Property, RDF.Resource}},
    ...     RDF.Property: {RDF.type: {RDFS.Class, RDF.Resource}},
    ...     RDF.Resource: {
    ...         RDF.type: {RDFS.Class},
    ...         RDF.value: {RDF.nil},
    ...     },
    ... })) == {
    ...     (RDF.type, RDF.type, RDF.Property),
    ...     (RDF.type, RDF.type, RDF.Resource),
    ...     (RDF.Property, RDF.type, RDF.Resource),
    ...     (RDF.Property, RDF.type, RDFS.Class),
    ...     (RDF.Resource, RDF.type, RDFS.Class),
    ...     (RDF.Resource, RDF.value, RDF.nil),
    ... }
    True
    '''
    for _subj, _twopledict in tripledict.items():
        for _pred, _objectset in _twopledict.items():
            for _obj in _objectset:
                yield (_subj, _pred, _obj)


def choose_one_iri(iris: Iterable[str]):
    # prefer iris without ":", shorter iris, and break ties by alphabet
    return min(iris, key=lambda iri: (':' in iri, len(iri), iri))


class Literal(NamedTuple):
    unicode_value: str  # an rdf value serialized to unicode string
    datatype_iris: frozenset[str]  # iris for any languages, codebooks,
    #                                thesauruseseses, datatypes, or web
    #                                links that help read the value str
    # (if you wish to constrain to IETF language tags
    # in https://www.rfc-editor.org/rfc/bcp/bcp47.txt
    # use the helper `literal(.., language='..')`
    # or an iri within the `IANA_LANGUAGE` namespace)

    @property
    def language(self) -> Optional[str]:
        try:
            return next(self.iter_language_tags())
        except StopIteration:
            return None

    def iter_language_tags(self) -> Iterator[str]:
        yield from (
            iri_minus_namespace(_iri, namespace=IANA_LANGUAGE)
            for _iri in self.datatype_iris
            if _iri in IANA_LANGUAGE
        )

    def single_datatype(self) -> str:
        if any(self.iter_language_tags()):
            return RDF.langString
        if self.datatype_iris:
            return choose_one_iri(self.datatype_iris)
        return RDF.string

    def as_literal_iri(self):
        '''encode text as a self-addressed iri with scheme "literal"
        '''
        return LITERAL[self.unicode_value]  # TODO: datatype_iris


def literal(
    primitive_value: Union[str, int, float, datetime.date], *,
    datatype_iris: Union[str, Iterable[str]] = (),
    language=None,  # adds an IANA_LANGUAGE iri to datatype_iris
    mediatype=None,  # adds a IANA_MEDIATYPE iri to datatype_iris
) -> Literal:
    '''convenience wrapper for Literal

    >>> literal('blurbl di blarbl da', datatype_iris={BLARG.my_language})
    Literal(unicode_value='blurbl di blarbl da',
          datatype_iris=frozenset({'http://blarg.example/vocab/my_language'}))
    >>> literal(7)
    Literal(unicode_value='7',
        datatype_iris=frozenset({'http://www.w3.org/2001/XMLSchema#integer'}))
    >>> literal(datetime.date(1111, 11, 11))
    Literal(unicode_value='1111-11-11',
        datatype_iris=frozenset({'http://www.w3.org/2001/XMLSchema#date'}))
    >>> literal('hello', mediatype='text/plain;charset=utf-8')
    Literal(unicode_value='hello',
        datatype_iris=frozenset({'https://www.iana.org/assignments/media-types/text/plain#charset=utf-8'}))
    >>> literal('hello', language='es').datatype_iris == {
    ...     RDF.langString,
    ...     IANA_LANGUAGE['es'],
    ... }
    True
    >>> literal(
    ...    '¿porque no los dos?',
    ...    language='es',
    ...    mediatype='text/plain;charset=utf-8',
    ... ).datatype_iris == {
    ...     RDF.langString,
    ...     IANA_LANGUAGE['es'],
    ...     IANA_MEDIATYPE['text/plain#charset=utf-8'],
    ... }
    True
    >>> literal('')
    Literal(unicode_value='',
            datatype_iris=frozenset({'http://www.w3.org/1999/02/22-rdf-syntax-ns#string'}))
    >>> literal(None)
    Traceback (most recent call last):
      ...
    ValueError: expected RdfObject, got None
    '''
    _str_value = None
    _implied_datatype = None
    if isinstance(primitive_value, str):
        _str_value = primitive_value
        if language:
            _implied_datatype = RDF.langString
        elif not datatype_iris and not mediatype:
            _implied_datatype = RDF.string
    elif isinstance(primitive_value, int):
        _str_value = str(primitive_value)
        _implied_datatype = XSD.integer
    elif isinstance(primitive_value, float):
        _str_value = str(primitive_value)  # fits with xsd:float definition
        _implied_datatype = XSD.float
    elif isinstance(primitive_value, datetime.datetime):
        _str_value = primitive_value.isoformat()
        _implied_datatype = XSD.dateTime
    elif isinstance(primitive_value, datetime.date):
        _str_value = primitive_value.isoformat()
        _implied_datatype = XSD.date

    if _str_value is None:
        raise ValueError(f'expected RdfObject, got {primitive_value}')

    def _iter_one_or_many(items) -> Iterator:
        if isinstance(items, str):
            yield items
        else:
            try:
                for _item in items:
                    yield from _iter_one_or_many(_item)
            except TypeError:
                pass  # not str or iterable; ignore

    def _iter_datatype_iris() -> Iterator[str]:
        yield from _iter_one_or_many(datatype_iris)
        for _language in _iter_one_or_many(language):
            if ':' in _language:  # assume full IRI
                yield _language
            else:  # assume language tag
                yield IANA_LANGUAGE[_language]
        for _mediatype in _iter_one_or_many(mediatype):
            yield iri_from_mediatype(_mediatype)
        if _implied_datatype is not None:
            yield _implied_datatype

    return Literal(
        unicode_value=_str_value,
        datatype_iris=frozenset(_iter_datatype_iris()),
    )


def literal_or_none(
    primitive_value: Union[str, int, float, datetime.date, None], **kwargs
) -> Union[Literal, None]:
    '''
    same as `literal`, but gives None for empty values instead ValueError

    >>> literal_or_none(None)
    '''
    if primitive_value is None:
        return None
    return literal(primitive_value, **kwargs)


def literal_json(jsonable_obj):
    return literal(
        json.dumps(jsonable_obj, sort_keys=True),
        datatype_iris={RDF.JSON},
    )


class QuotedTriple(NamedTuple):
    subj: RdfSubject
    pred: RdfPredicate
    obj: RdfObject


def container(
    container_type: str,
    items: Iterable[RdfObject],
    *,
    with_twoples: Iterable[RdfTwople] = (),
) -> RdfBlanknode:
    '''
    >>> _bag = container(RDF.Bag, [11,12,13])
    >>> type(_bag) is frozenset and _bag == {
    ...     (RDF.type, RDF.Bag),
    ...     (RDF._1, 11),
    ...     (RDF._2, 12),
    ...     (RDF._3, 13),
    ... }
    True
    >>> _empty = container(RDF.Bag, [])
    >>> type(_empty) is frozenset and _empty == {(RDF.type, RDF.Bag)}
    True
    '''
    _indexed_twoples = (
        (RDF[f'_{_index+1}'], _item)
        for _index, _item in enumerate(items)
    )
    return frozenset((
        (RDF.type, container_type),
        *_indexed_twoples,
        *with_twoples,
    ))


def is_container(bnode: RdfBlanknode) -> bool:
    '''
    >>> is_container(blanknode({RDF.type: {RDF.Alt}}))
    True
    >>> is_container(blanknode({RDF.type: {RDF.Seq}}))
    True
    >>> is_container(blanknode({RDF.type: {RDF.Bag}}))
    True
    >>> is_container(blanknode({RDF.type: {RDF.Container}}))
    True

    not linked lists tho
    >>> is_container(blanknode({RDF.type: {RDF.List}}))
    False
    >>> is_container(blanknode())
    False
    '''
    return any(
        (RDF.type, _container_type) in bnode
        for _container_type in (RDF.Seq, RDF.Bag, RDF.Alt, RDF.Container)
    )


def sequence(
    items: Iterable[RdfObject], *,
    with_twoples: Iterable[RdfTwople] = (),
) -> RdfBlanknode:
    '''
    >>> sequence([3,2,1]) == frozenset((
    ...     (RDF.type, RDF.Seq),
    ...     (RDF._1, 3),
    ...     (RDF._2, 2),
    ...     (RDF._3, 1),
    ... ))
    True
    '''
    return container(RDF.Seq, items, with_twoples=with_twoples)


def sequence_objects_in_order(seq: RdfBlanknode) -> Iterator[RdfObject]:
    '''
    >>> _seq = sequence([5,4,3,2,1])
    >>> list(sequence_objects_in_order(_seq))
    [5, 4, 3, 2, 1]
    '''
    assert (RDF.type, RDF.Seq) in seq
    yield from map(
        operator.itemgetter(1),
        sorted(_enumerate_container(seq), key=operator.itemgetter(0)),
    )


def container_objects(bnode: RdfBlanknode) -> Iterator[RdfObject]:
    '''
    >>> _seq = sequence([5,4,3,2,1])
    >>> set(container_objects(_seq)) == {1,2,3,4,5}
    True
    >>> list(container_objects(_seq)) == [5,4,3,2,1]
    True
    '''
    if (RDF.type, RDF.Seq) in bnode:
        yield from sequence_objects_in_order(bnode)
    else:
        for _, _obj in _enumerate_container(bnode):
            yield _obj


def _enumerate_container(
    bnode: RdfBlanknode,
) -> Iterator[tuple[int, RdfObject]]:
    _INDEX_NAMESPACE = IriNamespace(RDF['_'])  # rdf:_1, rdf:_2, ...
    for _pred, _obj in bnode:
        try:
            _index = int(iri_minus_namespace(
                _pred,
                namespace=_INDEX_NAMESPACE,
            ))
        except ValueError:
            pass
        else:
            yield (_index, _obj)


###
# a tuple of names of increasing length (TODO: validate, use)
# choose which name to use based on the space available
Namestory = tuple['Literal', ...]


###
# for using iris without having to type out full iris
class IriNamespace:
    '''IriNamespace: the set of all possible names which begin with a given iri

    is a convenience for building and using IRIs easily in python code
    (ideally IRLs ("L" for "Locator", an IRI which locates an internet
    document (like via `http`/`https`) and resolves to something which
    makes enough sense given context), but this toolkit does not check
    for locatorishness and treats any IRI like an IRN ("N" for "Name")

    >>> BLARG.foo
    'http://blarg.example/vocab/foo'
    >>> BLARG.blah
    'http://blarg.example/vocab/blah'
    >>> BLARG['blip']
    'http://blarg.example/vocab/blip'
    >>> 'http://florb.example' in BLARG
    False
    >>> 'http://blarg.example/vocab/foo' in BLARG
    True
    >>> _subvocab = IriNamespace(BLARG['subvocab#'])
    >>> _subvocab
    IriNamespace("http://blarg.example/vocab/subvocab#")
    >>> str(_subvocab)
    'http://blarg.example/vocab/subvocab#'
    >>> _subvocab in BLARG
    True
    >>> BLARG in _subvocab
    False
    >>> _subvocab.ooo
    'http://blarg.example/vocab/subvocab#ooo'
    >>> _subvocab['🦎']
    'http://blarg.example/vocab/subvocab#🦎'
    >>> _subvocab['🦎🦎🦎🦎🦎']
    'http://blarg.example/vocab/subvocab#🦎🦎🦎🦎🦎'
    >>> BLARG['subvocab#', '🦎'] == _subvocab['🦎']
    True
    >>> BLARG['another/', 'subvocab#', '🦎']
    'http://blarg.example/vocab/another/subvocab#🦎'
    '''
    def __init__(
        self, iri: str, *,
        nameset: Optional[set[str]] = None,
        namestory: Optional[Namestory | Callable[[], Namestory]] = None,
    ):
        # TODO: namespace metadata/definition
        if ':' not in iri:
            raise ValueError(f'expected iri to have a ":" (got "{iri}")')
        # assume python's "private name mangling" will avoid conflicts
        self.__iri = iri
        self.__nameset = (
            frozenset(nameset)
            if nameset is not None
            else None
        )
        self.__namestory = namestory

    @functools.cached_property
    def namestory(self):
        return (
            self.__namestory()
            if callable(self.__namestory)
            else self.__namestory
        )

    def __join_name(self, name: str) -> str:
        if (self.__nameset is not None) and (name not in self.__nameset):
            raise ValueError(
                f'name "{name}" not in namespace "{self.__iri}"'
                f' (allowed names: {self.__nameset})'
            )
        return ''.join((self.__iri, name))

    def __getitem__(self, names) -> str:
        '''IriNamespace.__getitem__: build iri with `SQUARE['bracket']` syntax

        >>> BLARG['blah']
        'http://blarg.example/vocab/blah'

        concatenates multiple args (like for namespaces within namespaces)
        >>> BLARG['blah/', 'blum#']
        'http://blarg.example/vocab/blah/blum#'
        >>> BLARG['blah/', 'blum#', 'blee']
        'http://blarg.example/vocab/blah/blum#blee'
        '''
        return (
            self.__join_name(names)
            if isinstance(names, str)
            else self.__join_name(''.join(names))
        )

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


def get_namespace_iri(namespace: IriNamespace):
    '''get the iri for a namespace

    >>> get_namespace_iri(BLARG)
    'http://blarg.example/vocab/'
    '''
    return namespace._IriNamespace__iri


def iri_minus_namespace(
    iri: str,
    namespace: Union[str, 'IriNamespace'],
) -> str:
    '''get the rest of the iri after its namespace

    >>> iri_minus_namespace(BLARG.foo, BLARG)
    'foo'

    raises `ValueError` if the iri does not belong to the namespace
    >>> iri_minus_namespace(BLARG.foo, RDF)
    Traceback (most recent call last):
      ...
    ValueError: "http://blarg.example/vocab/foo" does not start with
      "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    '''
    _namespace_iri = (
        namespace
        if isinstance(namespace, str)
        else get_namespace_iri(namespace)
    )
    if not iri.startswith(_namespace_iri):
        raise ValueError(f'"{iri}" does not start with "{_namespace_iri}"')
    return iri[len(_namespace_iri):]  # the remainder after the namespace


###
# static iri namespaces

LITERAL = IriNamespace('literal:')  # a joke that might be serious

# some standard namespaces used herein
RDF = IriNamespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#')
RDFS = IriNamespace('http://www.w3.org/2000/01/rdf-schema#')
OWL = IriNamespace('http://www.w3.org/2002/07/owl#')
XSD = IriNamespace('http://www.w3.org/2001/XMLSchema#')

# in this implementation, `Literal` can have many
# datatype iris, which includes languages by iri:
# here is a probably-reliable way to express IETF
# language tags in iri form (TODO: consider using
# id.loc.gov instead? is authority for ISO 639-1,
# ISO 639-2; is intended for linked-data context;
# but is only a subset of valid IETF BCP 47 tags)
IANA_LANGUAGE = IriNamespace(
    'https://www.iana.org/assignments/language-subtag-registry#',
    namestory=lambda: (
        literal('language', language='en'),
        literal('language tag', language='en'),
        literal((
            'a "language tag" (as used by RDF and defined by IETF'
            ' in BCP 47 (https://www.ietf.org/rfc/bcp/bcp47.txt))'
            ' is a hyphen-delimited list of "subtags", where each'
            ' subtag has an entry in the Language Subtag Registry'
            ' maintained by IANA -- the URL of that IANA registry'
            ' (with appended "#") is used as an IRI namespace for'
            ' language tags (even tho the tag may contain several'
            ' registered subtags) -- this is probably okay to do.'
        ), language='en'),
    ),
)

# another IANA-based probably-reliable namespace:
IANA_MEDIATYPE = IriNamespace(
    'https://www.iana.org/assignments/media-types/',
    namestory=lambda: (
        literal('mediatype', language='en'),
        literal(
            'an IRI namespace for media-types (without parameters)',
            language='en',
        ),
        literal((
            'if a literal conforms to a media type (aka "MIME type"'
            ' or "Content-Type") could use an iri in this namespace'
            ' namespace as a datatype/language iri -- '
            ' for media types that do not require parameters to use'
            ' utf-8 (since rdf literals in lexical form are utf-8).'
            ' for example, IANA_MEDIATYPE["text/turtle"]'
        ), language='en'),
    ),
)


def iri_from_mediatype(mediatype: str) -> str:
    '''build an iri for the given mediatype

    mediatype parameters (e.g. "; charset=utf-8") are put in the iri fragment,
    so the iri can be used to locate the iana mediatype registration (usually)

    >>> iri_from_mediatype('text/turtle')
    'https://www.iana.org/assignments/media-types/text/turtle'
    >>> iri_from_mediatype('text/markdown; charset=utf-8')
    'https://www.iana.org/assignments/media-types/text/markdown#charset=utf-8'

    note that equivalent mediatypes may be expressed multiple ways -- this iri
    is specific to how the given mediatype was expressed, including parameter
    ordering, quotes, and spaces
    '''
    _typename, _, _parameters = mediatype.partition(';')
    return (
        IANA_MEDIATYPE[_typename.strip(), '#', _parameters.strip()]
        if _parameters
        else IANA_MEDIATYPE[_typename.strip()]
    )


def mediatype_from_iri(iri: str) -> str:
    '''get a mediatype from the given iri (assumed to be from IANA_MEDIATYPE)

    reverses the behavior of `iri_from_mediatype`:  the iri fragment, if any,
    is assumed to be mediatype parameters and will be appended after ';'

    >>> mediatype_from_iri(IANA_MEDIATYPE['text/turtle'])
    'text/turtle'
    >>> mediatype_from_iri(IANA_MEDIATYPE['text/markdown#charset=utf-8'])
    'text/markdown; charset=utf-8'
    '''
    _name = iri_minus_namespace(iri, IANA_MEDIATYPE)
    _typename, _, _parameters = _name.partition('#')
    return (
        f'{_typename}; {_parameters}'
        if _parameters
        else _typename
    )


# map a short string to a longer iri (or IriNamespace)
ShorthandPrefixMap = dict[str, Union[str, IriNamespace]]


class IriShorthand:
    delimiter = ':'
    __used_shorts = None  # for track_used_shorts

    def __init__(self, prefix_map: Optional[ShorthandPrefixMap] = None):
        self.prefix_map = {**(prefix_map or {})}  # make a copy; handle None

    def __repr__(self):
        return f'{self.__class__.__qualname__}({self.prefix_map})'

    def with_update(
        self,
        another_prefix_map: ShorthandPrefixMap,
    ) -> 'IriShorthand':
        '''create a new IriShorthand with the given updates

        >>> _foo = IriShorthand({'foo': 'urn:foo:', 'bar': 'urn:bar:'})
        >>> _foo.with_update({'baz': 'urn:baz'})
        IriShorthand({'foo': 'urn:foo:', 'bar': 'urn:bar:', 'baz': 'urn:baz'})
        >>> _foo.with_update({'bar': None, 'qux': 'urn:qux:'})
        IriShorthand({'foo': 'urn:foo:', 'qux': 'urn:qux:'})
        '''
        _updated_prefix_map = {
            **self.prefix_map,
            **another_prefix_map,
        }
        return IriShorthand({
            _label: _iri_or_namespace
            for _label, _iri_or_namespace in _updated_prefix_map.items()
            if _iri_or_namespace is not None
        })

    @contextlib.contextmanager
    def track_used_shorts(self):
        assert self.__used_shorts is None
        _used_shorts = self.__used_shorts = set()
        try:
            yield _used_shorts
        finally:
            self.__used_shorts = None

    def compact_iri(self, iri: str) -> str:
        '''return a compacted form of the given iri (or the iri unchanged)

        >>> _shorthand = IriShorthand({'blarg': BLARG})
        >>> _shorthand.compact_iri(BLARG.haha)
        'blarg:haha'
        >>> _shorthand.prefix_map['lol'] = BLARG.haha
        >>> _shorthand.compact_iri(BLARG.haha)
        'lol'
        >>> _shorthand.delimiter = '--'
        >>> _shorthand.compact_iri(BLARG.blah)
        'blarg--blah'
        >>> _shorthand.prefix_map = {'lol': f'{BLARG.haha}#heehee'}
        >>> _shorthand.compact_iri(BLARG.haha)
        'http://blarg.example/vocab/haha'
        >>> IriShorthand({}).compact_iri(BLARG.haha)
        'http://blarg.example/vocab/haha'
        '''
        _matches = set(self._iter_shortenings(iri))
        if not _matches:
            return iri  # no shortening
        # if multiple ways to shorten, use the shortest compact iri
        _matchdict = dict(_matches)
        _compact_iri = choose_one_iri(_matchdict.keys())
        self.__used_short(_matchdict[_compact_iri])
        return _compact_iri

    def expand_iri(self, iri: str) -> str:
        '''return the expanded form of the given iri (or the iri unchanged)

        >>> _shorthand = IriShorthand({'blarg': BLARG, 'blargl': BLARG.l})
        >>> _shorthand.expand_iri('blarg')
        'http://blarg.example/vocab/'
        >>> _shorthand.expand_iri('blargl')
        'http://blarg.example/vocab/l'
        >>> _shorthand.expand_iri('blarg:foo')
        'http://blarg.example/vocab/foo'
        >>> _shorthand.expand_iri('flarg:boo')
        'flarg:boo'
        >>> _shorthand.expand_iri('http://something.example/else')
        'http://something.example/else'
        >>> IriShorthand({'http': BLARG}).expand_iri('http://foo.example')
        'http://foo.example'
        '''
        try:
            _exact_match = self.prefix_map[iri]
        except KeyError:
            pass
        else:  # found exact match
            self.__used_short(iri)
            return (
                str(_exact_match)
                if isinstance(_exact_match, IriNamespace)
                else _exact_match
            )
        _short_prefix, _delimiter, _remainder = iri.partition(self.delimiter)
        if _delimiter and not _remainder.startswith('//'):
            try:
                _long_prefix = self.prefix_map[_short_prefix]
            except KeyError:
                pass
            else:
                self.__used_short(_short_prefix)
                return f'{_long_prefix}{_remainder}'
        return iri  # not a recognized shorthand

    def expand_triple(self, triple):
        (_subj, _pred, _obj) = triple
        return (
            self.expand_term(_subj),
            self.expand_term(_pred),
            self.expand_term(_obj),
        )

    def expand_term(self, term):
        if isinstance(term, str):
            return self.expand_iri(term)
        if isinstance(term, frozenset):
            return frozenset(
                (self.expand_term(_pred), self.expand_term(_obj))
                for _pred, _obj in term
            )
        return term

    def _iter_shortenings(self, iri):
        for _short, _long in self.prefix_map.items():
            _is_match = (
                (iri in _long)
                if isinstance(_long, IriNamespace)
                else iri.startswith(_long)
            )
            if _is_match:
                _name = iri_minus_namespace(iri, namespace=_long)
                if _name:
                    yield (f'{_short}{self.delimiter}{_name}', _short)
                else:
                    yield (_short, _short)

    def __used_short(self, short_prefix):
        if self.__used_shorts is not None:
            self.__used_shorts.add(short_prefix)


class RdfGraph:
    '''rdf-lingo convenience interface around a primitive RdfTripleDictionary

    create an RdfGraph wrapping an empty tripledict
    >>> _mytripledict = {}
    >>> _mygraph = RdfGraph(_mytripledict)

    add some triples
    >>> _mygraph.add((BLARG.foo, BLARG.bar, BLARG.baz))
    >>> _mygraph.add((BLARG.foo, BLARG.bar, BLARG.zab))
    >>> _mygraph.add((BLARG.oof, BLARG.rab, BLARG.zab))

    see the tripledict has been updated
    >>> _mytripledict == _mygraph.tripledict == {
    ...     BLARG.foo: {BLARG.bar: {BLARG.baz, BLARG.zab}},
    ...     BLARG.oof: {BLARG.rab: {BLARG.zab}},
    ... }
    True

    can use `in` to check for a given triple
    >>> (BLARG.foo, BLARG.bar, BLARG.baz) in _mygraph
    True
    >>> (BLARG.oof, BLARG.bar, BLARG.baz) in _mygraph
    False

    can use `.q()` to query and get an iterable of matching objects
    >>> set(_mygraph.q(BLARG.foo, BLARG.bar)) == {BLARG.baz, BLARG.zab}
    True
    '''
    tripledict: RdfTripleDictionary

    def __init__(
        self,
        triples: Union[RdfTripleDictionary, Iterable[RdfTriple], None] = None,
    ):
        if triples is None:
            self.tripledict = {}
        elif isinstance(triples, dict):
            self.tripledict = triples
        elif isinstance(triples, types.MappingProxyType):
            # makes a read-only RdfGraph -- this is fine
            self.tripledict = triples  # type: ignore[assignment]
        else:  # assume Iterable[RdfTriple]
            self.tripledict = tripledict_from_tripleset(triples)

    def add(self, triple: RdfTriple):
        add_triple(self.tripledict, triple)

    def remove(self, triple: RdfTriple):
        '''remove a triple from the graph

        >>> _mygraph = RdfGraph({'foo:subj': {'foo:pred': {'foo:obj'}}})
        >>> _mygraph.tripledict
        {'foo:subj': {'foo:pred': {'foo:obj'}}}
        >>> _mygraph.remove(('foo:subj', 'foo:pred', 'foo:obj'))
        >>> _mygraph.tripledict
        {}

        raises KeyError if not found
        >>> _mygraph.remove(('foo:triple', 'foo:not', 'foo:found'))
        Traceback (most recent call last):
            ...
        KeyError: ('foo:triple', 'foo:not', 'foo:found')

        '''
        (_subj, _pred, _obj) = triple
        try:
            _twopledict = self.tripledict[_subj]
            _objectset = _twopledict[_pred]
            _objectset.remove(_obj)
            if not _objectset:
                del _twopledict[_pred]
                if not _twopledict:
                    del self.tripledict[_subj]
        except KeyError:
            raise KeyError(triple)

    def discard(self, triple: RdfTriple):
        '''
        same as `remove`, but do nothing if the triple is not found
        '''
        try:
            self.remove(triple)
        except KeyError:
            pass

    def add_twopledict(self, subject: str, twopledict: RdfTwopleDictionary):
        for _pred, _obj in iter_twoples(twopledict):
            self.add((subject, _pred, _obj))

    def add_tripledict(self, tripledict: RdfTripleDictionary):
        for _triple in iter_tripleset(tripledict):
            self.add(_triple)

    def __contains__(self, triple: RdfTriple) -> bool:
        (_subj, _pred, _obj) = triple
        try:
            return (_obj in self.tripledict[_subj][_pred])
        except KeyError:
            return False

    def q(self, subj: str, pathset: MessyPathset) -> Iterator[RdfObject]:
        '''query the wrapped tripledict, iterate over matching objects

        >>> _tw = RdfGraph({
        ...     ':a': {
        ...         ':nums': {1, 2},
        ...         ':nums2': {2, 3},
        ...         ':blorg': {':b'},
        ...     },
        ...     ':b': {
        ...         ':nums': {7},
        ...         ':blorg': {':a', frozenset([(':blorg', ':c')])},
        ...     },
        ... })
        >>> set(_tw.q(':a', ':nums')) == {1, 2}
        True
        >>> sorted(_tw.q(':a', [':nums', ':nums2']))
        [1, 2, 2, 3]
        >>> list(_tw.q(':a', {':blorg': {':nums'}}))
        [7]
        >>> sorted(_tw.q(':a', [':nums', {':blorg': ':nums'}]))
        [1, 2, 7]
        >>> sorted(_tw.q(':a', {':blorg': {':blorg': ':blorg'}}))
        [':b', ':c']
        '''
        return self._iter_twopledict_objects(
            self.tripledict.get(subj) or {},
            tidy_pathset(pathset),
        )

    def _iter_twopledict_objects(
        self,
        twopledict: RdfTwopleDictionary,
        tidy_pathset: TidyPathset,
    ) -> Iterator[RdfObject]:
        for _pred, _next_pathset in tidy_pathset.items():
            _object_set = twopledict.get(_pred) or set()
            if not _next_pathset:  # end of path
                yield from _object_set
            else:  # more path
                for _obj in _object_set:
                    if isinstance(_obj, str):
                        _next_twopledict = self.tripledict.get(_obj) or {}
                    elif isinstance(_obj, frozenset):
                        _next_twopledict = twopledict_from_twopleset(_obj)
                    else:
                        continue
                    yield from self._iter_twopledict_objects(
                        _next_twopledict,
                        _next_pathset,
                    )


class QuotedGraph(RdfGraph):
    focus_iri: str

    def __init__(self, *args, focus_iri: str, **kwargs):
        self.focus_iri = focus_iri
        super().__init__(*args, **kwargs)


def tidy_pathset(messy_pathset: MessyPathset) -> TidyPathset:
    if not messy_pathset:
        return {}
    if isinstance(messy_pathset, str):
        return {messy_pathset: {}}
    if isinstance(messy_pathset, dict):
        return {
            _pred: tidy_pathset(_nested_pathset)
            for _pred, _nested_pathset in messy_pathset.items()
        }

    # assume Iterable[MessyPathset]
    def _merge_pathset(from_pathset: TidyPathset, *, into: TidyPathset):
        for _pred, _next_pathset in from_pathset.items():
            _merge_pathset(
                _next_pathset,
                into=into.setdefault(_pred, {}),
            )
    _pathset: TidyPathset = {}
    for _parallel_pathset in messy_pathset:
        _merge_pathset(
            tidy_pathset(_parallel_pathset),
            into=_pathset,
        )
    return _pathset


###
# no-context json-ld serialization

def tripledict_as_nocontext_jsonld(tripledict: RdfTripleDictionary) -> list:
    '''build json-ld of the rdf graph that can be parsed without `@context`

    return a json-serializable list

    TODO: doctest>>> tripledict_as_nocontext_jsonld({
    ...     RDFS.isDefinedBy: {RDFS.isDefinedBy: {str(RDFS)}},
    ... })  # TODO: doctest
    '''
    return [
        twopledict_as_nocontext_jsonld(_twopledict, iri=_subject_iri)
        for _subject_iri, _twopledict in tripledict.items()
    ]


def twopledict_as_nocontext_jsonld(
    twopledict: RdfTwopleDictionary, *,
    iri: Optional[str] = None,
) -> dict:
    '''build json-ld of the rdf twoples that can be parsed without `@context`

    return a json-serializable dict
    '''
    _jsonld_twopledict = {
        _predicate_iri: sorted(  # sort for stable serialization
            map(rdfobject_as_nocontext_jsonld, _objset),
            key=json.dumps,
        )
        for _predicate_iri, _objset in twopledict.items()
    }
    if iri:
        _jsonld_twopledict['@id'] = iri  # type: ignore[assignment]
    return _jsonld_twopledict


def rdfobject_as_nocontext_jsonld(rdfobj: RdfObject):
    '''build json-ld of the rdf object that can be parsed without `@context`

    return a json-serializable dict
    '''
    if isinstance(rdfobj, str):
        return {'@id': rdfobj}
    if isinstance(rdfobj, Literal):
        _jsonld_obj = {'@value': rdfobj.unicode_value}
        _language_tag_iris = {
            _iri
            for _iri in rdfobj.datatype_iris
            if _iri in IANA_LANGUAGE
        }
        if _language_tag_iris:  # standard language(s)
            _jsonld_obj['@language'] = _json_item_or_list(
                iri_minus_namespace(_iri, namespace=IANA_LANGUAGE)
                for _iri in _language_tag_iris
            )
        _datatype_iris = {
            _iri
            for _iri in rdfobj.datatype_iris
            if _iri not in IANA_LANGUAGE
        }
        if _datatype_iris:  # datatype or non-standard language
            _jsonld_obj['@type'] = _json_item_or_list(_datatype_iris)
        return _jsonld_obj
    elif isinstance(rdfobj, (int, float)):
        return {'@value': rdfobj}
    elif isinstance(rdfobj, datetime.datetime):
        return {
            '@value': rdfobj.isoformat(),
            '@type': XSD.dateTime,
        }
    elif isinstance(rdfobj, datetime.date):
        return {
            '@value': rdfobj.isoformat(),
            '@type': XSD.date,
        }
    elif isinstance(rdfobj, frozenset):
        # TODO: handle container
        return twopledict_as_nocontext_jsonld(
            twopledict_from_twopleset(rdfobj),
        )
    # TODO: QuotedTriple
    raise ValueError(f'expected RdfObject, got {rdfobj}')


###
# no-context json-ld de-serialization
# (only meant for handling the output of the functions above, not most json-ld)

def tripledict_from_nocontext_jsonld(jsonld_nodes: list):
    '''inverse of `tripledict_as_nocontext_jsonld` (not for arbitrary json-ld)
    '''
    _tripledict = {}
    for _jsonld_node in jsonld_nodes:
        _iri = _jsonld_node['@id']  # required
        if _iri in _tripledict:
            raise ValueError(
                f'nocontext jsonld has repeated node ("@id": "{_iri}")',
            )
        _tripledict[_iri] = twopledict_from_nocontext_jsonld(_jsonld_node)
    return _tripledict


def twopledict_from_nocontext_jsonld(jsonld_twopledict: dict):
    '''inverse of `twopledict_as_nocontext_jsonld` (not for arbitrary json-ld)
    '''
    return {
        _predicate_iri: {
            rdfobject_from_nocontext_jsonld(_obj)
            for _obj in _objset
        }
        for _predicate_iri, _objset in jsonld_twopledict.items()
    }


def rdfobject_from_nocontext_jsonld(jsonld_obj: dict):
    '''inverse of `rdfobject_as_nocontext_jsonld` (not for arbitrary json-ld)
    '''
    _iri = jsonld_obj.get('@id')
    if _iri:
        return _iri  # NOTE: ignores any other keys
    _value = jsonld_obj.get('@value')
    if _value:
        if isinstance(_value, (int, float)):
            return _value
        _language_tag = jsonld_obj.get('@language')
        if _language_tag:
            return literal(_value, language=_language_tag)
        _type_iri = jsonld_obj.get('@type')
        if _type_iri == XSD.date:
            return datetime.date.fromisoformat(_value)  # python 3.7+
        if _type_iri == XSD.dateTime:
            return datetime.datetime.fromisoformat(_value)  # python 3.7+
        if _type_iri:
            return literal(_value, datatype_iris=_type_iri)
    # if no '@id' or '@value', treat as blank node
    return twopledict_from_nocontext_jsonld(jsonld_obj)


###
# utilities for working with dataclasses
#
# use `dataclasses.Field.metadata` as RdfTwopleDictionary describing a property
# (iri keys are safe enough against collision), with implicit `rdfs:label` from
# `Field.name` (possible TODO: gather a `shacl:PropertyShape` for `Field.type`)
#
# similarly, imagine the `dataclasses.dataclass` decorator allowed a `metadata`
# dictionary (defined same as `Field.metadata`) that we could treat as rdf data
# describing an `rdfs:Class` corresponding to the dataclass itself (an instance
# of the dataclass might have an implicit `rdf:type` in its rdf representation)
# -- see `dataclass_metadata` and `get_dataclass_metadata`
#
# may treat a dataclass instance as blanknode, twople-dictionary, or twople-set
# (TODO: maybe build a Focus based on fields mapped to owl:sameAs and rdf:type)


@functools.cache
def _all_dataclass_metadata():
    '''for storing dataclass metadata, keyed by the dataclass itself'''
    return weakref.WeakKeyDictionary()


def get_dataclass_metadata(datacls_or_instance) -> types.MappingProxyType:
    _datacls = (
        datacls_or_instance
        if isinstance(datacls_or_instance, type)
        else type(datacls_or_instance)
    )
    return types.MappingProxyType(_all_dataclass_metadata().get(_datacls, {}))


def dataclass_metadata(metadata: dict):
    '''pretend `dataclasses.dataclass` had a `metadata` kwarg like `field`

    decorate a dataclass with `dataclass_metadata` (put it before
    `@dataclasses.dataclass` so it applies after) and pass twopledict to
    `metadata` to describe the rdf:Class for this dataclass
    >>> @dataclass_metadata({
    ...     # values for owl:sameAs on the dataclass will be used
    ...     # as the rdf:type for instances of this dataclass
    ...     OWL.sameAs: {BLARG.MyWord},
    ...     BLARG.meeble: {BLARG.plo},
    ... })
    ... @dataclasses.dataclass
    ... class MyWord:
    ...     word: str = dataclasses.field(metadata={
    ...         OWL.sameAs: {BLARG.wordWord},
    ...     })
    ...     comment: str = dataclasses.field(metadata={
    ...         OWL.sameAs: {RDFS.comment},
    ...     })
    ...
    >>> iter_dataclass_twoples(MyWord('what', 'whomever'))
    <generator object iter_dataclass_twoples at 0x...>
    >>> set(_) == {
    ...     (RDF.type, BLARG.MyWord),
    ...     (BLARG.wordWord, 'what'),
    ...     (RDFS.comment, 'whomever'),
    ... }
    True
    >>> iter_dataclass_class_triples(MyWord)
    <generator object iter_dataclass_class_triples at 0x...>
    >>> set(_) == {(BLARG.MyWord, BLARG.meeble, BLARG.plo)}
    True
    '''
    def _dataclass_metadata_decorator(cls):
        assert dataclasses.is_dataclass(cls)
        _dataclass_metadata_dict = _all_dataclass_metadata()
        assert cls not in _dataclass_metadata_dict
        _dataclass_metadata_dict[cls] = metadata
        return cls
    return _dataclass_metadata_decorator


def iter_dataclass_twoples(
    datacls_instance,
    iri_by_fieldname: Optional[
        dict[str, Union[str, Iterable[str]]]
    ] = None,
) -> Iterator[RdfTwople]:
    '''
    >>> _blarg = BlargDataclass(foo='foo', bar='bar')
    >>> set(iter_dataclass_twoples(_blarg)) == {(BLARG.foo, 'foo')}
    True
    >>> set(iter_dataclass_twoples(_blarg, {'bar': BLARG.barrr})) == {
    ...     (BLARG.barrr, 'bar'),
    ...     (BLARG.foo, 'foo'),
    ... }
    True
    >>> set(iter_dataclass_twoples(_blarg, {
    ...     'foo': BLARG.fool,
    ...     'bar': BLARG.barr,
    ...     'baz': BLARG.baz,
    ... })) == {
    ...     (BLARG.foo, 'foo'),
    ...     (BLARG.fool, 'foo'),
    ...     (BLARG.barr, 'bar'),
    ... }
    True
    '''
    assert (
        dataclasses.is_dataclass(datacls_instance)
        and not isinstance(datacls_instance, type)
    )
    _datacls_metadata = get_dataclass_metadata(datacls_instance)
    for _type_iri in _datacls_metadata.get(OWL.sameAs, ()):
        yield (RDF.type, _type_iri)
    for _field in dataclasses.fields(datacls_instance):
        _field_iris = set(_field.metadata.get(OWL.sameAs, ()))
        if iri_by_fieldname:
            _additional_fields = iri_by_fieldname.get(_field.name, ())
            if isinstance(_additional_fields, str):
                _field_iris.add(_additional_fields)
            else:  # assume Iterable[str]
                _field_iris.update(_additional_fields)
        if _field_iris:
            _field_value = getattr(datacls_instance, _field.name, None)
            if _field_value is not None:
                for _field_iri in _field_iris:
                    yield (_field_iri, _field_value)


def iter_dataclass_triples(
    datacls_instance,
    iri_by_fieldname: Optional[
        dict[str, Union[str, Iterable[str]]]
    ] = None,
    subject_iri: Optional[str] = None,
) -> Iterator[RdfTriple]:
    _subj = subject_iri
    if _subj is None:
        for _field in dataclasses.fields(datacls_instance):
            if OWL.sameAs in _field.metadata.get(OWL.sameAs, ()):
                _subj = getattr(datacls_instance, _field.name)
        if _subj is None:
            raise ValueError(
                'must provide `subject_iri` or define a dataclass field'
                'with `metadata={OWL.sameAs: {OWL.sameAs}}`'
            )
    _twoples = iter_dataclass_twoples(datacls_instance, iri_by_fieldname)
    for _pred, _obj in _twoples:
        yield (_subj, _pred, _obj)


def iter_dataclass_class_triples(
    datacls, *,
    class_iri: Optional[str] = None,
) -> Iterator[RdfTriple]:
    # the dataclass itself, not an instance
    assert dataclasses.is_dataclass(datacls) and isinstance(datacls, type)
    _datacls_metadata = get_dataclass_metadata(datacls)
    _class_iri = class_iri
    if _class_iri is None:
        try:
            _class_iri = next(iter(_datacls_metadata[OWL.sameAs]))
        except (KeyError, StopIteration):
            raise ValueError(
                'must provide `subject_iri` or add dataclass metadata'
                'like `@dataclass_metadata={OWL.sameAs: {OWL.sameAs}}`'
            )
    for (_pred, _obj) in iter_twoples(_datacls_metadata):
        if (_pred, _obj) != (OWL.sameAs, _class_iri):
            yield (_class_iri, _pred, _obj)
    for _field in dataclasses.fields(datacls):
        _field_iri = next(iter(_datacls_metadata[OWL.sameAs]))
        _field_iris = _field.metadata.get(OWL.sameAs, ())
        for _field_iri in _field_iris:
            for (_pred, _obj) in iter_twoples(_field.metadata):
                if (_pred, _obj) != (OWL.sameAs, _field_iri):
                    yield (_field_iri, _pred, _obj)


def dataclass_as_twopledict(
    dataclass_instance,
    iri_by_fieldname=None,
) -> RdfTwopleDictionary:
    return twopledict_from_twopleset(
        iter_dataclass_twoples(dataclass_instance, iri_by_fieldname),
    )


def dataclass_as_blanknode(
    dataclass_instance,
    iri_by_fieldname=None,
) -> RdfBlanknode:
    '''
    >>> _blarg = BlargDataclass(foo='bloo', bar='blip')
    >>> _blank_blarg = dataclass_as_blanknode(_blarg)
    >>> type(_blank_blarg) is frozenset
    True
    >>> _blank_blarg == {(BLARG.foo, 'bloo')}
    True
    >>> dataclass_as_blanknode(_blarg, {'bar': BLARG.bar}) == {
    ...     (BLARG.foo, 'bloo'),
    ...     (BLARG.bar, 'blip'),
    ... }
    True
    '''
    return frozenset(
        iter_dataclass_twoples(dataclass_instance, iri_by_fieldname),
    )


###
# translating to/from rdflib.Graph (and thereby turtle)

try:
    import rdflib
except ImportError:
    logger.info(
        'primitive_rdf.py: no rdflib; omitting rdflib utilities',
    )
else:

    def turtle_from_tripledict(
        tripledict: RdfTripleDictionary, *,
        focus: Optional[str] = None,
        shorthand: Optional[IriShorthand] = None,  # TODO: add to turtle prefix
    ) -> str:
        _rdflib_graph = rdflib_graph_from_tripledict(tripledict)
        # TODO: sort blocks, focus first
        return _rdflib_graph.serialize(format='turtle')

    def rdflib_graph_from_tripledict(tripledict: RdfTripleDictionary):
        '''

        an rdf graph expressed as primitive tripledict:
        >>> _tripledict = {
        ...     BLARG.ha: {  # subject
        ...         BLARG.pa: {  # predicate
        ...             BLARG.ya,  # objects...
        ...             BLARG.xa,
        ...             blanknode({
        ...                 BLARG.a: {BLARG.b},
        ...                 BLARG.c: {BLARG.d},
        ...                 BLARG.e: {
        ...                     blanknode({BLARG.f: {BLARG.ya}}),
        ...                 },
        ...             }),
        ...         },
        ...         BLARG.na: {  # predicate
        ...             BLARG.ya,  # objects...
        ...         },
        ...     },
        ...     BLARG.ya: {  # another subject
        ...         BLARG.pa: {BLARG.ha},
        ...         BLARG.ba: {
        ...             literal('ha pa la xa', datatype_iris=BLARG.Dunno),
        ...             literal('naja yaba', datatype_iris=BLARG.Mystery),
        ...             literal('basic', language='en'),
        ...             literal('মৌলিক', language='bn'),
        ...         },
        ...     }
        ... }

        the same graph expressed as turtle:
        >>> _turtle = f"""
        ...     @prefix blarg: <{str(BLARG)}> .
        ...     blarg:ha
        ...         blarg:pa blarg:ya ,
        ...                  blarg:xa ,
        ...                  [
        ...                     blarg:a blarg:b ;
        ...                     blarg:c blarg:d ;
        ...                     blarg:e [ blarg:f blarg:ya ] ;
        ...                  ] ;
        ...         blarg:na blarg:ya .
        ...     blarg:ya
        ...         blarg:pa blarg:ha ;
        ...         blarg:ba "ha pa la xa"^^blarg:Dunno ,
        ...                       "naja yaba"^^blarg:Mystery ,
        ...                       "basic"@en ,
        ...                       "মৌলিক"@bn .
        ... """

        the rdflib translations of those expressions agree:
        >>> from rdflib.compare import to_isomorphic, graph_diff
        >>> _from_tripledict = rdflib_graph_from_tripledict(_tripledict)
        >>> _from_turtle = rdflib.Graph().parse(format='turtle', data=_turtle)
        >>> to_isomorphic(_from_tripledict) == to_isomorphic(_from_turtle)
        True

        and may be converted back to tripledict:
        >>> _td_from_turtle = tripledict_from_rdflib(_from_turtle)
        >>> _td_from_tripledict = tripledict_from_rdflib(_from_tripledict)
        >>> _tripledict == _td_from_turtle == _td_from_tripledict
        True
        '''

        _rdflib_graph = rdflib.Graph()  # TODO: namespace prefixes?
        _blanknode_map: dict[RdfBlanknode, rdflib.BNode] = {}

        # a local helper
        def _add_to_rdflib_graph(
            rdflib_subj: rdflib.term.Node,
            rdflib_pred: rdflib.term.Node,
            obj: RdfObject,
        ):
            _rdflib_graph.add((
                rdflib_subj,
                rdflib_pred,
                _simple_rdflib_obj(obj),
            ))

        def _simple_rdflib_obj(obj: RdfObject):
            if isinstance(obj, str):
                return rdflib.URIRef(obj)
            if isinstance(obj, Literal):
                _language_tag_iris = {
                    _iri
                    for _iri in obj.datatype_iris
                    if _iri in IANA_LANGUAGE
                }
                if _language_tag_iris:
                    return rdflib.Literal(
                        obj.unicode_value,
                        lang=iri_minus_namespace(
                            next(iter(_language_tag_iris)),  # choose any one
                            namespace=IANA_LANGUAGE,
                        ),
                    )
                elif obj.datatype_iris:  # non-standard language (or datatype)
                    return rdflib.Literal(
                        obj.unicode_value,
                        datatype=rdflib.URIRef(
                            next(iter(obj.datatype_iris)),  # choose any one
                        ),
                    )
                else:  # no language or datatype
                    return rdflib.Literal(obj.unicode_value)
            elif isinstance(obj, (int, float, datetime.date)):
                return rdflib.Literal(obj)
            elif isinstance(obj, frozenset):
                try:
                    _bnode = _blanknode_map[obj]
                except KeyError:
                    _bnode = rdflib.BNode()
                    _blanknode_map[obj] = _bnode
                for _pred, _obj in obj:
                    _add_to_rdflib_graph(_bnode, rdflib.URIRef(_pred), _obj)
                return _bnode
            # TODO: QuotedTriple
            raise ValueError(f'expected RdfObject, got {obj}')

        for (_subj, _pred, _obj) in iter_tripleset(tripledict):
            _add_to_rdflib_graph(
                rdflib.URIRef(_subj),
                rdflib.URIRef(_pred),
                _obj,
            )
        return _rdflib_graph

    def tripledict_from_turtle(turtle: str):
        # TODO: without rdflib (should be simpler;
        # turtle already structured like RdfTripleDictionary)
        _rdflib_graph = rdflib.Graph()
        _rdflib_graph.parse(data=turtle, format='turtle')
        return tripledict_from_rdflib(_rdflib_graph)

    def tripledict_from_rdflib(rdflib_graph):
        _open_subjects = set()

        def _twoples(rdflib_subj) -> Iterator[RdfTwople]:
            if rdflib_subj in _open_subjects:
                raise ValueError(
                    'cannot handle loopy blanknodes'
                    f' (reached {rdflib_subj} again after {_open_subjects})'
                )
            _open_subjects.add(rdflib_subj)
            for _rdflib_pred, _rdflib_obj in rdflib_graph.predicate_objects(
                rdflib_subj
            ):
                if not isinstance(_rdflib_pred, rdflib.URIRef):
                    raise ValueError(
                        f'predicates must be str iris (got {_rdflib_pred})',
                    )
                _obj = _obj_from_rdflib(_rdflib_obj)
                if _obj:
                    yield (str(_rdflib_pred), _obj)
            _open_subjects.remove(rdflib_subj)

        def _obj_from_rdflib(rdflib_obj) -> RdfObject:
            # TODO: handle rdf:List and friends?
            if isinstance(rdflib_obj, rdflib.URIRef):
                return str(rdflib_obj)
            if isinstance(rdflib_obj, rdflib.BNode):
                return frozenset(_twoples(rdflib_obj))
            if isinstance(rdflib_obj, rdflib.Literal):
                if rdflib_obj.language:
                    return literal(
                        str(rdflib_obj),
                        language=rdflib_obj.language,
                    )
                if rdflib_obj.datatype:
                    return literal(
                        str(rdflib_obj),
                        datatype_iris=str(rdflib_obj.datatype),
                    )
                return literal(str(rdflib_obj.value))
            raise ValueError(f'how obj? ({rdflib_obj})')

        _td_wrapper = RdfGraph({})
        for _rdflib_subj in rdflib_graph.subjects():
            if isinstance(_rdflib_subj, rdflib.URIRef):
                _subj = str(_rdflib_subj)
                for _pred, _obj in _twoples(_rdflib_subj):
                    _td_wrapper.add((_subj, _pred, _obj))
        if rdflib_graph and not _td_wrapper.tripledict:
            raise ValueError(
                'there was something, but we got nothing -- note that'
                ' blanknodes not reachable from an IRI subject are omitted'
            )
        return _td_wrapper.tripledict


###
# local utilities

def _json_sort(items: Iterable):
    def _sortkey(item):
        return json.dumps(item, sort_keys=True)
    # sort objects for a stable serialization
    return sorted(items, key=_sortkey)


def _json_item_or_list(items: Iterable):
    try:
        (_only_item,) = items
    except ValueError:
        return _json_sort(items)
    else:
        return _only_item


###
# for use in doctests
if __debug__:
    # a nonsense namespace for unknowable language
    BLARG = IriNamespace('http://blarg.example/vocab/')

    @dataclasses.dataclass
    class BlargDataclass:
        foo: str = dataclasses.field(metadata={
            OWL.sameAs: {BLARG.foo},
        })
        bar: str  # unadorned


###
# running this module as main
#
# to run doctests: `python3 primitive_rdf.py`

if __name__ == '__main__':
    import doctest
    _fail, _total = doctest.testmod(optionflags=(
        doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS
    ))
    print("{} failures out of {} tests".format(_fail, _total))
