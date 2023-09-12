'''primitive_rdf.py: some rdf primitives implemented with python primitives

j
to be found in standard rdf concepts: https://www.w3.org/TR/rdf11-concepts/
'''
# only standard imports (python 3.? (TODO: specificity informed by testing))
import datetime
import json
import logging
import operator
from typing import Iterable, Union, Optional, NamedTuple

if __debug__:  # examples/tests thru-out, wrapped in `__debug__`
    # run tests with the command `python3 -m unittest gather.py`
    # (or discard tests with `-O` or `-OO` command-line options)
    import unittest  # TODO: doctest instead (or in addition?)


logger = logging.getLogger(__name__)


###
# RDF data represented using built-in or standard python types supporting
# most (but not all) RDF concepts [https://www.w3.org/TR/rdf11-concepts/]
RdfSubject = str    # iri (not a blank node)
RdfPredicate = str  # iri
RdfObject = Union[
    str,         # iri references as plain strings
    'Dropping',  # dataclass for value of any type or language
    frozenset['RdfTwople'],  # blanknodes as frozenset[twople]
]
RdfTwople = tuple[RdfPredicate, RdfObject]  # implicit subject
RdfTriple = tuple[RdfSubject, RdfPredicate, RdfObject]
RdfBlanknode = frozenset[RdfTwople]
RdfTripleSet = frozenset[RdfTriple]

# an RDF graph as a dictionary of dictionaries
# note: these are the only mutable "Rdf" types
RdfTwopleDictionary = dict[RdfPredicate, set[RdfObject]]
RdfTripleDictionary = dict[RdfSubject, RdfTwopleDictionary]


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

def ensure_frozenset(something) -> frozenset:
    '''convenience for building frozensets

    >>> ensure_frozenset([])  # convert list to frozenset
    frozenset()
    >>> ensure_frozenset(['foo'])
    frozenset({'foo'})
    >>> ensure_frozenset('foo')  # str treated as a value, not list of letters
    frozenset({'foo'})
    >>> _ab = ensure_frozenset(['a', 'b'])
    >>> type(_ab) is frozenset and _ab == {'b', 'a'}
    True
    >>> ensure_frozenset(['a','b']) == {'a', 'b'}
    True
    >>> _r = ensure_frozenset(range(5))
    >>> type(_r) is frozenset and _r == {4, 3, 2, 1, 0}
    True
    >>> ensure_frozenset(_r) is _r  # given a frozenset, do nothing
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


def freeze_blanknode(twopledict: RdfTwopleDictionary) -> RdfBlanknode:
    '''build a "blank node" frozenset of twoples (rdf triples without subjects)

    >>> freeze_blanknode({})
    frozenset()
    >>> _blank = freeze_blanknode({RDF.value: {RDF.Bag, RDF.Seq, RDF.Alt}})
    >>> type(_blank) is frozenset and _blank == {
    ...     (RDF.value, RDF.Bag),
    ...     (RDF.value, RDF.Seq),
    ...     (RDF.value, RDF.Alt),
    ... }
    True
    '''
    return frozenset(
        (_pred, _obj)
        for _pred, _objectset in twopledict.items()
        for _obj in _objectset
    )


def twopleset_as_twopledict(
    twopleset: Iterable[RdfTwople],
) -> RdfTwopleDictionary:
    '''build a "twople dictionary" of RDF objects indexed by predicate

    @param twopleset: iterable of (str, obj) twoples
    @returns: dict[str, set] built from twoples

    >>> _tdict = twopleset_as_twopledict([
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
    _twopledict = {}
    for _pred, _obj in twopleset:
        if _pred in _twopledict:
            _objectset = _twopledict[_pred]
        else:
            _objectset = _twopledict[_pred] = set()
        _objectset.add(_obj)
    return _twopledict


def smells_like_rdf_tripledict(rdf_dictionary) -> bool:
    '''
    >>> smells_like_rdf_tripledict(None)
    False
    >>> smells_like_rdf_tripledict(7)
    False
    >>> smells_like_rdf_tripledict({})
    True
    >>> smells_like_rdf_tripledict({RDF.type: {}})
    True
    >>> smells_like_rdf_tripledict({RDF.type: 7})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type}})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type: [RDF.Property]}})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type: [RDF.Property]}})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type: RDF.Property}})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type: {RDF.Property: 7}}})
    False
    >>> smells_like_rdf_tripledict({RDF.type: {RDF.type: {RDF.Property}}})
    True
    '''
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
) -> Iterable[RdfTriple]:
    '''
    >>> tripledict_as_tripleset({})
    <generator object tripledict_as_tripleset at 0x...>
    >>> list(_) == []
    True
    >>> tripledict_as_tripleset({RDF.type: {RDF.type: {RDF.Property}}})
    <generator object tripledict_as_tripleset at 0x...>
    >>> set(_) == {(RDF.type, RDF.type, RDF.Property)}
    True
    >>> tripledict_as_tripleset({
    ...     RDF.type: {RDF.type: {RDF.Property, RDF.Resource}},
    ...     RDF.Property: {RDF.type: {RDFS.Class, RDF.Resource}},
    ...     RDF.Resource: {
    ...         RDF.type: {RDFS.Class},
    ...         RDF.value: {RDF.nil},
    ...     },
    ... })
    <generator object tripledict_as_tripleset at 0x...>
    >>> set(_) == {
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
        if isinstance(obj, Dropping):
            _language_iri = obj.language_iri
            if not _language_iri:  # no language
                return rdflib.Literal(obj.unicode_text)
            if _language_iri in IANA_LANGUAGE:  # standard language
                _language_tag = IriNamespace.without_namespace(
                    _language_iri,
                    namespace=IANA_LANGUAGE,
                )
                return rdflib.Literal(obj.unicode_text, lang=_language_tag)
            # non-standard language (treat as datatype)
            return rdflib.Literal(
                obj.unicode_text,
                datatype=rdflib.URIRef(_language_iri),
            )
        elif isinstance(obj, (int, float, datetime.date)):
            return rdflib.Literal(obj)
        elif isinstance(obj, frozenset):
            # may result in duplicates -- don't do shared blanknodes
            _blanknode = rdflib.BNode()
            for _pred, _obj in obj:
                _add_to_rdflib_graph(_blanknode, rdflib.URIRef(_pred), _obj)
            return _blanknode
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

    def _twoples(rdflib_subj) -> Iterable[RdfTwople]:
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
                    f'cannot handle non-iri predicates (got {_rdflib_pred})',
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
                return drop(str(rdflib_obj), language_tag=rdflib_obj.language)
            _as_python = rdflib_obj.toPython()
            if isinstance(_as_python, (int, float, datetime.date)):
                return _as_python
            if rdflib_obj.datatype:
                return drop(
                    str(rdflib_obj),
                    language_iri=str(rdflib_obj.datatype),
                )
            return drop(str(rdflib_obj.value))
        raise ValueError(f'how obj? ({rdflib_obj})')

    _td_wrapper = TripledictWrapper({})
    for _rdflib_subj in rdflib_graph.subjects():
        if isinstance(_rdflib_subj, rdflib.URIRef):
            _subj = str(_rdflib_subj)
            for _pred, _obj in _twoples(_rdflib_subj):
                _td_wrapper.add_triple((_subj, _pred, _obj))
    if rdflib_graph and not _td_wrapper.tripledict:
        raise ValueError(
            'there was something, but we got nothing -- note that'
            ' blanknodes not reachable from an IRI subject are omitted'
        )
    return _td_wrapper.tripledict


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
                        drop('ha pa la xa', language_iri=BLARG.Dunno),
                        drop('naja yaba', language_iri=BLARG.Dunno),
                        drop('basic', language_tag='en'),
                        drop('মৌলিক', language_tag='bn'),
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
                                  "basic"@en ,
                                  "মৌলিক"@bn .
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


class Dropping(NamedTuple):
    unicode_value: str  # an rdf value serialized to unicode string
    language_iris: frozenset[str]  # iris for any languages, codebooks,
    #                            thesauruseseses, datatypes, or web
    #                            links that help read the value str
    # (if you wish to constrain to IETF language tags
    # in https://www.rfc-editor.org/rfc/bcp/bcp47.txt
    # use the `drop` helper with `language_tag` param
    # or an iri within the `IANA_LANGUAGE` namespace)

    def language_tag(self) -> Union[str, None]:
        try:
            return next(
                IriNamespace.without_namespace(_iri, namespace=IANA_LANGUAGE)
                for _iri in self.language_iris
                if _iri in IANA_LANGUAGE
            )
        except StopIteration:
            return None

    def single_datatype(self) -> str:
        if self.language_tag:
            return RDF.langString
        if not self.language_iris:
            return RDF.string
        return min(
            self.language_iris,
            key=lambda iri: (len(iri), iri),  # sort by length and alphabet
        )


def drop(
    textdrop: str, *,
    language_iris: Iterable[str] = (),
    language_tag=None,
) -> Union[Dropping, None]:
    '''convenience wrapper for Text
    '''
    if (textdrop is None) or ('' == textdrop):
        return None  # is ok to drop nothing sometimes
    if not isinstance(textdrop, str):
        raise ValueError(
            f'expected None or str, got {textdrop} (a {type(textdrop)})'
            ' -- non-str values should be serialized with datatype like'
            ' `language_iris=[XSD.boolean]` (or whichever types it has)'
        )

    def _iter_language_iris():
        yield from language_iris
        if language_tag is not None:
            yield IANA_LANGUAGE[language_tag]
    return Dropping(
        unicode_value=textdrop,
        language_iris=frozenset(_iter_language_iris()),
    )


if __debug__:
    class TestText(unittest.TestCase):
        def test_blurb(self):
            my_blurb = drop(
                'blurbl di blarbl ga',
                language_iri=BLARG['my-language'],
            )
            self.assertIsInstance(my_blurb.unicode_text, str)
            self.assertIsInstance(my_blurb.language_iri, str)
            self.assertEqual(my_blurb.unicode_text, 'blurbl di blarbl ga')
            self.assertEqual(
                my_blurb.language_iri,
                'https://blarg.example/my-language',
            )


def container(container_type: str, items: Iterable[RdfObject]) -> RdfBlanknode:
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
    ))


def is_container(bnode: RdfBlanknode) -> bool:
    return any(
        (RDF.type, _container_type) in bnode
        for _container_type in (RDF.Seq, RDF.Bag, RDF.Alt, RDF.Container)
    )


def sequence(items: Iterable[RdfObject]) -> RdfBlanknode:
    '''
    >>> sequence([3,2,1]) == frozenset((
    ...     (RDF.type, RDF.Seq),
    ...     (RDF._1, 3),
    ...     (RDF._2, 2),
    ...     (RDF._3, 1),
    ... ))
    True
    '''
    return container(RDF.Seq, items)


def sequence_objects_in_order(seq: RdfBlanknode) -> Iterable[RdfObject]:
    '''
    >>> _seq = sequence([5,4,3,2,1])
    >>> list(sequence_objects_in_order(_seq))
    [5, 4, 3, 2, 1]
    '''
    assert (RDF.type, RDF.Seq) in seq
    yield from map(
        operator.itemgetter(1),
        sorted(_container_indexobjects(seq), key=operator.itemgetter(0)),
    )


def container_objects(bnode: RdfBlanknode) -> Iterable[RdfObject]:
    '''
    >>> _seq = sequence([5,4,3,2,1])
    >>> set(container_objects(_seq)) == {1,2,3,4,5}
    True
    '''
    for _, _obj in _container_indexobjects(bnode):
        yield _obj


def _container_indexobjects(
    bnode: RdfBlanknode,
) -> Iterable[tuple[int, RdfObject]]:
    _INDEX_NAMESPACE = IriNamespace(RDF['_'])  # rdf:_1, rdf:_2, ...
    for _pred, _obj in bnode:
        try:
            _index = int(IriNamespace.without_namespace(
                _pred,
                namespace=_INDEX_NAMESPACE,
            ))
        except ValueError:
            pass
        else:
            yield (_index, _obj)


###
# a tuple of names of increasing length (TODO: validate)
# choose which name to use based on the space available
Namestory = tuple['Dropping', ...]


###
# for using iris without having to type out full iris
class IriNamespace:
    '''IriNamespace: the set of all possible names which begin with a given iri

    is a convenience for building and using IRIs easily in python code
    (ideally IRLs ("L" for "Locator", an IRI which locates an internet
    document (like via `http`/`https`) and resolves to something which
    makes enough sense given context), but this toolkit does not check
    for locatorishness and treats any IRI like an IRN ("N" for "Name")

    >>> BLARG = IriNamespace('http://blarg.example/')
    >>> BLARG.foo
    'http://blarg.example/foo'
    >>> BLARG.blah
    'http://blarg.example/blah'
    >>> BLARG['blip']
    'http://blarg.example/blip'
    >>> 'http://florb.example' in BLARG
    False
    >>> 'http://blarg.example/foo' in BLARG
    True
    >>> _subvocab = IriNamespace(BLARG['subvocab#'])
    >>> _subvocab
    IriNamespace("http://blarg.example/subvocab#")
    >>> str(_subvocab)
    'http://blarg.example/subvocab#'
    >>> _subvocab in BLARG
    True
    >>> BLARG in _subvocab
    False
    >>> _subvocab.ooo
    'http://blarg.example/subvocab#ooo'
    >>> _subvocab['🦎']
    'http://blarg.example/subvocab#🦎'
    >>> _subvocab['🦎🦎🦎🦎🦎']
    'http://blarg.example/subvocab#🦎🦎🦎🦎🦎'
    >>> BLARG['subvocab#':'🦎'] == _subvocab['🦎']
    True
    >>> BLARG['another/':'subvocab#':'🦎']
    'http://blarg.example/another/subvocab#🦎'
    '''
    def __init__(
        self, iri: str, *,
        nameset: Optional[set[str]] = None,
        namestory: Optional[Namestory] = None,
    ):
        # TODO: namespace metadata/definition
        if ':' not in iri:
            raise ValueError(f'expected iri to have a ":" (got "{iri}")')
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
        namespace: Union[str, 'IriNamespace'],
    ) -> str:
        '''
        >>> BLARG = IriNamespace('http://blarg.example/')
        >>> IriNamespace.without_namespace(BLARG.foo, namespace=BLARG)
        'foo'
        >>> IriNamespace.without_namespace(BLARG.foo, namespace=RDF)
        Traceback (most recent call last):
          ...
        ValueError: "http://blarg.example/foo" does not start with
          "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        '''
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
        up to three parts separated by colons will be concatenated:
        >>> FOO = IriNamespace('http://foo.example/')
        >>> FOO['blah']
        'http://foo.example/blah'
        >>> FOO['blah/':'blum#']
        'http://foo.example/blah/blum#'
        >>> FOO['blah/':'blum#':'blee']
        'http://foo.example/blah/blum#blee'
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
# some standard namespaces used herein
RDF = IriNamespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#')
RDFS = IriNamespace('http://www.w3.org/2000/01/rdf-schema#')
OWL = IriNamespace('http://www.w3.org/2002/07/owl#')
XSD = IriNamespace('http://www.w3.org/2001/XMLSchema#')

# `gather.Text` uses an iri to identify language;
# here is a probably-reliable way to express IETF
# language tags in iri form (TODO: consider using
# id.loc.gov instead? is authority for ISO 639-1,
# ISO 639-2; is intended for linked-data context;
# but is only a subset of valid IETF BCP 47 tags)
IANA_LANGUAGE_REGISTRY_IRI = (
    'https://www.iana.org/assignments/language-subtag-registry'
)
IANA_LANGUAGE = IriNamespace(
    f'{IANA_LANGUAGE_REGISTRY_IRI}#',
    namestory=lambda: (
        drop('language', language_tag='en'),
        drop('language tag', language_tag='en'),
        drop((
            'a "language tag" (as used by RDF and defined by IETF'
            ' in BCP 47 (https://www.ietf.org/rfc/bcp/bcp47.txt))'
            ' is a hyphen-delimited list of "subtags", where each'
            ' subtag has an entry in the Language Subtag Registry'
            ' maintained by IANA -- the URL of that IANA registry'
            ' (with appended "#") is used as an IRI namespace for'
            ' language tags (even tho the tag may contain several'
            ' registered subtags) -- this is probably okay to do.'
        ), language_tag='en'),
    ),
)

if __debug__:
    BLARG = IriNamespace('https://blarg.example/')

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
                    drop(
                        'my-subvocab',
                        language_iri=IANA_LANGUAGE['en-US'],
                    ),
                    drop(
                        'a namespace nested within the BLARG namespace',
                        language_iri=IANA_LANGUAGE['en-US'],
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


class TripledictWrapper:
    def __init__(self, tripledict: RdfTripleDictionary):
        self.tripledict = tripledict

    def add_triple(self, triple: RdfTriple):
        (_subj, _pred, _obj) = triple
        (
            self.tripledict
            .setdefault(_subj, dict())
            .setdefault(_pred, set())
            .add(_obj)
        )

    def has_triple(self, triple: RdfTriple) -> bool:
        (_subj, _pred, _obj) = triple
        try:
            return (_obj in self.tripledict[_subj][_pred])
        except KeyError:
            return False

    def q(self, subj: str, pathset: MessyPathset) -> Iterable[RdfObject]:
        '''query the wrapped tripledict, iterate over matching objects

        >>> _tw = TripledictWrapper({
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
    ) -> Iterable[RdfObject]:
        for _pred, _next_pathset in tidy_pathset.items():
            _object_set = twopledict.get(_pred) or set()
            if not _next_pathset:  # end of path
                yield from _object_set
            else:  # more path
                for _obj in _object_set:
                    if isinstance(_obj, str):
                        _next_twopledict = self.tripledict.get(_obj) or {}
                    elif isinstance(_obj, frozenset):
                        _next_twopledict = twopleset_as_twopledict(_obj)
                    else:
                        continue
                    yield from self._iter_twopledict_objects(
                        _next_twopledict,
                        _next_pathset,
                    )


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
    _pathset = {}
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
        _jsonld_twopledict['@id'] = iri
    return _jsonld_twopledict


def rdfobject_as_nocontext_jsonld(rdfobj: RdfObject):
    '''build json-ld of the rdf object that can be parsed without `@context`

    return a json-serializable dict
    '''
    if isinstance(rdfobj, str):
        return {'@id': rdfobj}
    if isinstance(rdfobj, Dropping):
        _jsonld_obj = {'@value': rdfobj.unicode_text}
        _language_iri = rdfobj.language_iri
        if _language_iri in IANA_LANGUAGE:  # standard language
            _jsonld_obj['@language'] = IriNamespace.without_namespace(
                _language_iri,
                namespace=IANA_LANGUAGE,
            )
        else:  # non-standard language (treat as datatype)
            _jsonld_obj['@type'] = _language_iri
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
            twopleset_as_twopledict(rdfobj),
        )
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
            return drop(_value, language_tag=_language_tag)
        _type_iri = jsonld_obj.get('@type')
        if _type_iri == XSD.date:
            return datetime.date.fromisoformat(_value)  # python 3.7+
        if _type_iri == XSD.dateTime:
            return datetime.datetime.fromisoformat(_value)  # python 3.7+
        if _type_iri:
            return drop(_value, language_iri=_type_iri)
    # if no '@id' or '@value', treat as blank node
    return twopledict_from_nocontext_jsonld(jsonld_obj)


###
# primitive-context json-ld serialization

# constant PRIMITIVE_JSONLD_CONTEXT assumed part of the jsonld @context
# make sure full iris can be reconstructed without any network requests
PRIMITIVE_JSONLD_CONTEXT = {
    '@container': '@id',  # object with iri keys as RdfTripleDictionary
}


def compact_iri(
    iri: str,
    shortnames: dict[str, str],
    *,
    delimiter=':',
) -> str:
    '''
    >>> BLARG = IriNamespace('http://blarg.example/')
    >>> _namespaces = {'blarg': BLARG}
    >>> compact_iri(BLARG.haha, _namespaces)
    'blarg:haha'
    >>> _namespaces['lol'] = BLARG.haha
    >>> compact_iri(BLARG.haha, _namespaces)
    'lol'
    >>> compact_iri(BLARG.haha, {'lol': 'http://blarg.example/haha#heehee'})
    'http://blarg.example/haha'
    >>> compact_iri(BLARG.haha, {})
    'http://blarg.example/haha'
    '''
    def _shortname_matches(shortname, namespace) -> bool:
        return (
            (iri in namespace)
            if isinstance(namespace, IriNamespace)
            else iri.startswith(namespace)
        )

    def _build_compact_iri(shortname, namespace) -> str:
        _leafname = IriNamespace.without_namespace(iri, namespace=namespace)
        return (
            f'{shortname}{delimiter}{_leafname}'
            if _leafname
            else shortname
        )

    _shortened_iris = {
        _build_compact_iri(_shortname, _namespace)
        for _shortname, _namespace in shortnames.items()
        if _shortname_matches(_shortname, _namespace)
    }
    if not _shortened_iris:
        return iri  # no shortening
    return min(_shortened_iris, key=len)


def _primitive_names():
    return {
        'owl': OWL,
        'rdf': RDF,
        'rdfs': RDFS,
    }


def tripledict_as_jsonld(
    tripledict: RdfTripleDictionary, *,
    no_context: bool = False,
    shortnames: Optional[dict[str, IriNamespace]] = None,
) -> dict:
    '''build a json-serializable copy of the given tripledict
    '''
    _jsonld = {
        # TODO
    }
    if not no_context:
        _jsonld['@context'] = {
            **PRIMITIVE_JSONLD_CONTEXT,
            **(shortnames or {}),
        }
    return _jsonld


def rdfobject_as_jsonld(obj: RdfObject):
    pass


###
# utilities for working with dataclasses
#
# use `dataclasses.Field.metadata` as RdfTwopleDictionary describing a property
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
    ) -> Iterable[RdfTwople]:
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


if __name__ == '__main__':
    import doctest
    _fail, _total = doctest.testmod(optionflags=(
        doctest.NORMALIZE_WHITESPACE
        | doctest.ELLIPSIS
    ))
    print("{} failures out of {} tests".format(_fail, _total))
