import contextlib
import json
import typing

import rdflib

from gather.basket import Basket
from gather.basket_crawler import BasketCrawler
from gather.exceptions import BasketRenderError
from gather.focus import Focus


def render_jsonapi(basket: Basket) -> str:
    return JsonapiBasketCrawler(basket).crawl()


class JsonapiBasketCrawler(BasketCrawler):
    # abstract method from BasketCrawler
    def _crawl_result(self):
        jsonapi_document = {
            'data': self._primary_data,
            'included': self._included,
            # TODO: consider other top-level keys
        }
        return json.dumps(jsonapi_document, indent=4)

    # override from BasketCrawler
    @contextlib.contextmanager
    def _crawl_context(self):
        self._primary_data = None
        self._included = []
        self._current_attributes = None
        self._current_relationships = None
        yield

    # override from BasketCrawler
    @contextlib.contextmanager
    def _item_context(self, itemid):
        attributes = {}
        relationships = {}
        last_attributes = self._current_attributes
        last_relationships = self._current_relationships
        self._current_attributes = attributes
        self._current_relationships = relationships
        yield  # crawl item property/value
        self._current_attributes = last_attributes
        self._current_relationships = last_relationships
        item_dict = {}
        if isinstance(itemid, rdflib.URIRef):
            item_dict = {
                'id': self._display_iri(itemid),
                # TODO: 'type': self._display_iri(...),
                'attributes': attributes,
                'relationships': relationships,
            }
            if self._primary_data is None:
                self._primary_data = item_dict
            else:
                self._included.append(item_dict)
        elif isinstance(itemid, rdflib.BNode):
            item_dict = {
                **attributes,
                **relationships,
            }
        else:
            raise BasketRenderError(
                f'invalid itemid (should be URIRef or BNode): {itemid}',
            )

    # override from BasketCrawler
    @contextlib.contextmanager
    def _itemproperty_context(self, itemid, property_iri):
        values = []
        last_values = self._current_values
        last_property_iri = self._current_property_iri
        self._current_values = values
        self._current_property_iri = property_iri
        yield
        if self._is_relationship(property_iri):
            self._current_relationships[self._display_iri(property_iri)] = {
                'data': values,
            }
        else:
            self._current_attributes[self._display_iri(property_iri)] = values
        self._current_values = last_values
        self._current_property_iri = last_property_iri

    # abstract method from BasketCrawler
    def _visit_literal_value(self, itemid, property_iri, literal_value):
        print(f'literal.datatype: {literal_value.datatype}')
        if literal_value.datatype == rdflib.RDF.langString:
            self._current_values.append({
                '@value': str(literal_value),
                '@language': literal_value.language,
            })
        else:
            self._current_values.append(literal_value.toPython())

    # abstract method from BasketCrawler
    def _visit_blank_node(self, itemid, property_iri, blank_node):
        self._render_in_place(blank_node)

    # abstract method from BasketCrawler
    def _visit_iri_reference(self, itemid, property_iri, iri):
        self._current_values.append({'@id': iri})  # TODO: @type
        self._add_item_to_visit(iri)

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
            self._current_item = parent_item
            self._current_values.append(nested_object)


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
            actual_json = render_jsonapi(self.basket)
            print(actual_json)
            self.assertEqual(actual_json, '')
