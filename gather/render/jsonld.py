import contextlib
import json
import typing

import rdflib

from gather.basket import Basket
from gather.basket_crawler import BasketCrawler
from gather.exceptions import BasketRenderError
from gather.focus import Focus


def render_jsonld(basket: Basket) -> str:
    return JsonldBasketCrawler(basket).crawl()


class JsonldBasketCrawler(BasketCrawler):
    # abstract method from BasketCrawler
    def _crawl_result(self):
        return json.dumps(self._current_item, indent=4)

    # override from BasketCrawler
    @contextlib.contextmanager
    def _crawl_context(self):
        self._current_item = {}
        self._current_property_iri: typing.Optional[str] = None
        self._current_values: typing.Optional[list] = None
        yield

    # override from BasketCrawler
    @contextlib.contextmanager
    def _item_context(self, itemid):
        if isinstance(itemid, rdflib.URIRef):
            self._current_item['@id'] = self._display_iri(itemid)
        elif not isinstance(itemid, rdflib.BNode):
            raise BasketRenderError(
                f'invalid itemid (should be URIRef or BNode): {itemid}',
            )
        yield

    # override from BasketCrawler
    @contextlib.contextmanager
    def _itemproperty_context(self, itemid, property_iri):
        values = []
        last_values = self._current_values
        last_property_iri = self._current_property_iri
        self._current_values = values
        self._current_property_iri = property_iri
        try:
            yield
        finally:
            self._current_values = last_values
            self._current_property_iri = last_property_iri
        if property_iri == rdflib.RDF.type:
            values = [
                v['@id']
                for v in values
            ]
        self._current_item[self._display_iri(property_iri)] = values

    # abstract method from BasketCrawler
    def _visit_literal_value(self, itemid, property_iri, literal_value):
        value_object = {'@value': literal_value.toPython()}
        if literal_value.language is not None:
            value_object['@language'] = literal_value.language
        elif literal_value.datatype is not None:
            value_object['@type'] = self._display_iri(literal_value.datatype)
        self._current_values.append(value_object)

    # abstract method from BasketCrawler
    def _visit_blank_node(self, itemid, property_iri, blank_node):
        self._render_in_place(blank_node)

    # abstract method from BasketCrawler
    def _visit_iri_reference(self, itemid, property_iri, iri):
        if self._has_visited_item(itemid):
            self._current_values.append({'@id': itemid})  # TODO: @type?
        else:
            self._render_in_place(iri)

    def _display_iri(self, iri):
        if iri == rdflib.RDF.type:
            return '@type'
        return super()._display_iri(iri)

    def _render_in_place(self, iri_or_bnode):
        parent_item = self._current_item
        nested_object = {}
        self._current_item = nested_object
        try:
            self._visit_item(iri_or_bnode)  # item rendered in place
        finally:
            self._current_values.append(nested_object)
            self._current_item = parent_item


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
            actual_json = render_jsonld(self.basket)
            self.assertEqual(actual_json, '''{
    "@id": "<https://foo.example/one>",
    "@type": [
        "blarg:Item"
    ],
    "blarg:complexProperty": [
        {
            "@type": [
                "blarg:InnerObject"
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
            "@id": "<https://foo.example/two>",
            "@type": [
                "blarg:Item"
            ],
            "blarg:itemTitle": [
                {
                    "@value": "two thing",
                    "@language": "en"
                }
            ]
        }
    ]
}''')
