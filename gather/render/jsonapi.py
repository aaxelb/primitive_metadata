import abc
import contextlib
import json
import re

import rdflib

from gather.basket import Basket
from gather.basket_crawler import BasketCrawler
from gather.focus import Focus


# https://jsonapi.org/format/#document-member-names-allowed-characters
JSONAPI_MEMBER_NAME = re.compile(r'\b[a-zA-Z0-9][-_a-zA-Z0-9]*\b')


# def render_jsonapi(basket: Basket, ) -> str:
#     return JsonapiBasketCrawler(basket).crawl()

class JsonapiRenderConfig(abc.ABC):
    '''subclass with your own api's names and assumptions
    '''

    # TODO: use to build linked-data context

    @abc.abstractmethod
    def iri_to_docid(self, iri) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def should_render_in_place(self, predicate_iri) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def type_iris(self) -> dict[str, rdflib.URIRef]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_attribute_iris(self) -> dict[str, rdflib.URIRef]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_relationship_iris(self) -> dict[str, rdflib.URIRef]:
        raise NotImplementedError

    @property
    def attribute_iris_by_name(self):
        try:
            return self.__attribute_iris_by_name
        except AttributeError:
            self.__attribute_iris_by_name = self.get_attribute_iris()
            return self.__attribute_iris_by_name

    @property
    def relationship_iris_by_name(self):
        try:
            return self.__relationship_iris
        except AttributeError:
            self.__relationship_iris = self.get_relationship_iris()
            return self.__relationship_iris

    @property
    def attribute_names_by_iri(self):
        try:
            return self.__attribute_names_by_iri
        except AttributeError:
            self.__attribute_names_by_iri = {
                value: key
                for key, value in self.attribute_iris_by_name
            }
            return self.__attribute_names_by_iri

    @property
    def relationship_names_by_iri(self):
        try:
            return self.__relationship_names_by_iri
        except AttributeError:
            self.__relationship_names_by_iri = {
                value: key
                for key, value in self.get_relationship_iris()
            }
            return self.__relationship_names_by_iri

    def is_relationship(self, iri):
        return iri in self.relationship_names_by_iri

    def assert_valid_self(self):
        attrs_by_name = self.attribute_iris_by_name
        attrs_by_iri = self.attribute_iris_by_iri
        relations_by_name = self.relationship_iris_by_name
        relations_by_iri = self.relationship_names_by_iri
        for by_name in (attrs_by_name, relations_by_name):
            for name, iri in by_name.items():
                assert JSONAPI_MEMBER_NAME.fullmatch(name)
                assert isinstance(iri, rdflib.URIRef)
        for by_iri in (attrs_by_iri, relations_by_iri):
            for iri, name in by_iri.items():
                assert isinstance(iri, rdflib.URIRef)
                assert JSONAPI_MEMBER_NAME.fullmatch(name)
        nonintersecting_pairs = (
            (attrs_by_name.keys(), relations_by_name.keys()),
            (attrs_by_iri.keys(), relations_by_iri.keys()),
            (attrs_by_name.values(), relations_by_name.values()),
            (attrs_by_iri.values(), relations_by_iri.values()),
        )
        equal_pairs = (
            (attrs_by_name.keys(), attrs_by_iri.values()),
            (attrs_by_iri.keys(), attrs_by_name.values()),
            (relations_by_name.keys(), relations_by_iri.values()),
            (relations_by_iri.keys(), relations_by_name.values()),
        )
        for (one, another) in nonintersecting_pairs:
            assert not set(one).intersection(another)
        for (one, another) in equal_pairs:
            assert set(one) == set(another)


class JsonapiBasketCrawler(BasketCrawler):
    # serializing rdf as a jsonapi document may require more input
    # to behave as expected -- allow specifying which metadata properties
    # should be represented as "related resources" (otherwise will be
    # attributes with json-object values)
    def __init__(self, basket, jsonapi_render_config: JsonapiRenderConfig):
        super().__init__(basket)
        self._jsonapi_config = jsonapi_render_config

    # abstract method from BasketCrawler
    def _crawl_result(self):
        jsonapi_document = {
            'data': self._primary_data,
            'included': self._included,
            # TODO: consider other top-level keys
        }
        # TODO: jsonld @context?
        return json.dumps(jsonapi_document, indent=4)

    # override from BasketCrawler
    @contextlib.contextmanager
    def _crawl_context(self):
        self._primary_data = None
        self._included = []
        self._current_item = None
        self._current_values = None
        self._rendering_in_place = False
        yield

    # override from BasketCrawler
    @contextlib.contextmanager
    def _item_context(self, itemid):
        jsonapi_resource = {
            'id': self._display_iri(itemid),
            # TODO: 'type': self._display_iri(...),
            'attributes': {},
            'relationships': {},
        }
        if self._primary_data is None:
            self._primary_data = jsonapi_resource
        else:
            self._included.append(jsonapi_resource)
        last_item = self._current_item
        item_dict = self._current_item = {}
        try:
            yield  # crawl item property/value
        finally:
            self._current_item = last_item
        self._update_jsonapi_resource(jsonapi_resource, item_dict)

    # override from BasketCrawler
    @contextlib.contextmanager
    def _itemproperty_context(self, itemid, property_iri):
        values = []
        last_values = self._current_values
        self._current_values = values
        try:
            yield
        finally:
            self._current_values = last_values
        assert property_iri not in self._current_item
        self._current_item[property_iri] = values

    # abstract method from BasketCrawler
    def _visit_literal_value(self, itemid, property_iri, literal_value):
        assert not self._is_relationship(property_iri)
        value_object = {'@value': literal_value.toPython()}
        if literal_value.language is not None:
            value_object['@language'] = literal_value.language
        elif literal_value.datatype is not None:
            value_object['@type'] = self._display_iri(literal_value.datatype)
        self._current_values.append(value_object)

    # abstract method from BasketCrawler
    def _visit_blank_node(self, itemid, property_iri, blank_node):
        assert not self._is_relationship(property_iri)
        self._render_in_place(blank_node)

    # abstract method from BasketCrawler
    def _visit_iri_reference(self, itemid, property_iri, iri):
        if property_iri == rdflib.RDF.type:
            self._current_values.append(iri)
        elif self._is_relationship(property_iri):
            self._current_values.append(iri)
            self._add_item_to_visit(iri)
        else:
            self._render_in_place(iri)

    def _render_in_place(self, iri_or_bnode):
        outer_rendering_in_place = self._rendering_in_place
        self._rendering_in_place = True
        try:
            self._visit_item(iri_or_bnode)  # item rendered in place
        finally:
            self._rendering_in_place = outer_rendering_in_place

    def _update_jsonapi_resource(self, jsonapi_resource, item_dict):
        for property_iri, values in item_dict.items():
            if property_iri == rdflib.RDF.type:
                jsonapi_resource['@type'] = [
                    self._display_iri(iri)
                    for iri in values
                ]
                # TODO: user-provided type_iris?
                jsonapi_resource['type'] = jsonapi_resource['@type'][0]
            elif self._is_relationship(property_iri):
                relationship_data = []
                for iri in values:
                    self._add_item_to_visit(iri)
                    relationship_data.append({
                        'id': self._display_iri(iri),
                        # TODO 'type':
                    })
                jsonapi_resource['relationships'][
                    self._display_iri(property_iri)
                ] = {'data': relationship_data}
            else:
                jsonapi_resource['attributes'][
                    self._display_iri(property_iri)
                ] = values


if __debug__:
    import unittest

    BLARG = rdflib.Namespace('https://blarg.example/blarg/')

    class SimpleBasketHtmlTest(unittest.TestCase):
        maxDiff = None

        def setUp(self):
            one_iri = rdflib.URIRef('https://foo.example/one')
            two_iri = rdflib.URIRef('https://foo.example/two')
            one_bnode = rdflib.BNode()
            triples = {
                (one_iri, rdflib.RDF.type, BLARG.Item),
                (
                    one_iri,
                    BLARG.itemTitle,
                    rdflib.Literal('one thing', lang='en'),
                ),
                (one_iri, BLARG.likes, two_iri),
                (one_iri, BLARG.complexProperty, one_bnode),
                (one_bnode, rdflib.RDF.type, BLARG.InnerObject),
                (one_bnode, BLARG.innerA, rdflib.Literal('a', lang='en')),
                (one_bnode, BLARG.innerA, rdflib.Literal('a', lang='es')),
                (one_bnode, BLARG.innerB, rdflib.Literal('b', lang='en')),
                (one_bnode, BLARG.innerC, rdflib.Literal('c', lang='en')),
                (two_iri, rdflib.RDF.type, BLARG.Item),
                (
                    two_iri,
                    BLARG.itemTitle,
                    rdflib.Literal('two thing', lang='en'),
                ),
            }
            self.basket = Basket(Focus(one_iri, BLARG.Item))
            self.basket.gathered_metadata.bind('blarg', BLARG)
            for triple in triples:
                self.basket.gathered_metadata.add(triple)

        def test_render(self):
            actual_json = JsonapiBasketCrawler(self.basket).crawl()
            self.assertEqual(actual_json, '''{
    "data": {
        "id": "<https://foo.example/one>",
        "attributes": {
            "blarg:complexProperty": [
                {
                    "rdf:type": [
                        "https://blarg.example/blarg/InnerObject"
                    ],
                    "blarg:innerA": [
                        {
                            "@value": "a",
                            "@language": "en"
                        },
                        {
                            "@value": "a",
                            "@language": "es"
                        }
                    ],
                    "blarg:innerB": [
                        {
                            "@value": "b",
                            "@language": "en"
                        }
                    ],
                    "blarg:innerC": [
                        {
                            "@value": "c",
                            "@language": "en"
                        }
                    ]
                }
            ],
            "blarg:itemTitle": [
                {
                    "@value": "one thing",
                    "@language": "en"
                }
            ],
            "blarg:likes": [
                {
                    "rdf:type": [
                        "https://blarg.example/blarg/Item"
                    ],
                    "blarg:itemTitle": [
                        {
                            "@value": "two thing",
                            "@language": "en"
                        }
                    ]
                }
            ]
        },
        "relationships": {},
        "@type": [
            "blarg:Item"
        ],
        "type": "blarg:Item"
    },
    "included": []
}''')

        def test_render_with_relationships(self):
            crawler = JsonapiBasketCrawler(
                self.basket,
                relationship_iris={BLARG.likes}
            )
            actual_json = crawler.crawl()
            self.assertEqual(actual_json, '''{
    "data": {
        "id": "<https://foo.example/one>",
        "attributes": {
            "blarg:complexProperty": [
                {
                    "rdf:type": [
                        "https://blarg.example/blarg/InnerObject"
                    ],
                    "blarg:innerA": [
                        {
                            "@value": "a",
                            "@language": "en"
                        },
                        {
                            "@value": "a",
                            "@language": "es"
                        }
                    ],
                    "blarg:innerB": [
                        {
                            "@value": "b",
                            "@language": "en"
                        }
                    ],
                    "blarg:innerC": [
                        {
                            "@value": "c",
                            "@language": "en"
                        }
                    ]
                }
            ],
            "blarg:itemTitle": [
                {
                    "@value": "one thing",
                    "@language": "en"
                }
            ]
        },
        "relationships": {
            "blarg:likes": {
                "data": [
                    {
                        "id": "<https://foo.example/two>"
                    }
                ]
            }
        },
        "@type": [
            "blarg:Item"
        ],
        "type": "blarg:Item"
    },
    "included": [
        {
            "id": "<https://foo.example/two>",
            "attributes": {
                "blarg:itemTitle": [
                    {
                        "@value": "two thing",
                        "@language": "en"
                    }
                ]
            },
            "relationships": {},
            "@type": [
                "blarg:Item"
            ],
            "type": "blarg:Item"
        }
    ]
}''')
