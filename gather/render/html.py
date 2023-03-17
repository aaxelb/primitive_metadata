import contextlib
import hashlib
from xml.etree.ElementTree import (
    TreeBuilder,
    tostring as etree_tostring,
)

import rdflib

from gather.basket import Basket
from gather.basket_crawler import BasketCrawler
from gather.exceptions import BasketRenderError
from gather.focus import Focus


def render_html(basket: Basket) -> str:
    return HtmlBasketCrawler(basket).crawl()


class HtmlBasketCrawler(BasketCrawler):
    # override from BasketCrawler
    @contextlib.contextmanager
    def _crawl_context(self):
        self.itemid_to_elementid = {}
        self.tree_builder = TreeBuilder()
        self.tree_builder.start('article', {})
        try:
            yield
        finally:
            self.tree_builder.end('article')

    # abstract method from BasketCrawler
    def _crawl_result(self):
        return etree_tostring(
            self.tree_builder.close(),
            encoding='unicode',
            method='html',
        )

    # override from BasketCrawler
    @contextlib.contextmanager
    def _item_context(self, itemid):
        dl_attrs = {
            'itemscope': '',
            'itemtype': ' '.join(set(self.basket[itemid:rdflib.RDF.type]))
        }
        if isinstance(itemid, rdflib.URIRef):
            dl_attrs['id'] = self._item_elementid(itemid)
            dl_attrs['itemid'] = itemid
        elif not isinstance(itemid, rdflib.BNode):
            raise BasketRenderError(
                f'invalid itemid (should be URIRef or BNode): {itemid}',
            )
        with self._parent_element('dl', dl_attrs):
            yield

    # override from BasketCrawler
    @contextlib.contextmanager
    def _itemproperty_context(self, itemid, property_iri):
        self._leaf_element('dt', text=self._display_iri(property_iri))
        yield

    # override from BasketCrawler
    @contextlib.contextmanager
    def _itempropertyvalue_context(self, itemid, property_iri, value_obj):
        with self._parent_element('dd', {'itemprop': property_iri}):
            yield

    # abstract method from BasketCrawler
    def _visit_literal_value(self, itemid, property_iri, literal_value):
        # TODO: datatype, language tags, dates
        self.tree_builder.data(literal_value)

    # abstract method from BasketCrawler
    def _visit_blank_node(self, itemid, property_iri, blank_node):
        # item without iri rendered in place;
        # duplicated if referenced multiple times
        self._visit_item(blank_node)

    # abstract method from BasketCrawler
    def _visit_iri_reference(self, itemid, property_iri, iri):
        self._leaf_element(
            'a',
            {'href': f'#{self._item_elementid(iri)}'},
            text=self._display_iri(iri),
        )
        self._add_item_to_visit(iri)

    def _item_elementid(self, itemid):
        try:
            return self.itemid_to_elementid[itemid]
        except KeyError:
            itemid_hexdigest = hashlib.sha256(str(itemid).encode()).hexdigest()
            elementid = f'itemdescription-{itemid_hexdigest}'
            self.itemid_to_elementid[itemid] = elementid
            return elementid

    @contextlib.contextmanager
    def _parent_element(self, element_name, element_attrs=None):
        self.tree_builder.start(element_name, element_attrs or {})
        try:
            yield
        finally:
            self.tree_builder.end(element_name)

    def _leaf_element(self, element_name, element_attrs=None, text=None):
        with self._parent_element(element_name, element_attrs):
            if text is not None:
                self.tree_builder.data(text)


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
                (one_iri, BLARG.itemTitle, rdflib.Literal('one thing', lang='en')),
                (one_iri, BLARG.likes, two_iri),
                (one_iri, BLARG.complexProperty, one_bnode),
                (one_bnode, rdflib.RDF.type, BLARG.InnerObject),
                (one_bnode, BLARG.innerA, rdflib.Literal('a', lang='en')),
                (one_bnode, BLARG.innerB, rdflib.Literal('b', lang='en')),
                (one_bnode, BLARG.innerC, rdflib.Literal('c', lang='en')),
                (two_iri, rdflib.RDF.type, BLARG.Item),
                (two_iri, BLARG.itemTitle, rdflib.Literal('two thing', lang='en')),
            }
            self.basket = Basket(Focus(one_iri, BLARG.Item))
            self.basket.gathered_metadata.bind('blarg', BLARG)
            for triple in triples:
                self.basket.gathered_metadata.add(triple)

        def test_html(self):
            actual_html = render_html(self.basket)
            # TODO: indentation?
            self.assertEqual(actual_html, '<article><dl itemscope="" itemtype="https://blarg.example/blarg/Item" id="itemdescription-ea0e00f8ac6e27e457fbae19b0f351700355089608d1a1874d64df22807ef3b8" itemid="https://foo.example/one"><dt>rdf:type</dt><dd itemprop="http://www.w3.org/1999/02/22-rdf-syntax-ns#type"><a href="#itemdescription-7192147f234839d7b03749f54873e03093fea735e29b6e088138b928dd72be94">blarg:Item</a></dd><dt>blarg:complexProperty</dt><dd itemprop="https://blarg.example/blarg/complexProperty"><dl itemscope="" itemtype="https://blarg.example/blarg/InnerObject"><dt>rdf:type</dt><dd itemprop="http://www.w3.org/1999/02/22-rdf-syntax-ns#type"><a href="#itemdescription-0ede218fe60a5ea885351f2c74c86a42ced720b453b93f2931a20326ba2c0cc3">blarg:InnerObject</a></dd><dt>blarg:innerA</dt><dd itemprop="https://blarg.example/blarg/innerA">a</dd><dt>blarg:innerB</dt><dd itemprop="https://blarg.example/blarg/innerB">b</dd><dt>blarg:innerC</dt><dd itemprop="https://blarg.example/blarg/innerC">c</dd></dl></dd><dt>blarg:itemTitle</dt><dd itemprop="https://blarg.example/blarg/itemTitle">one thing</dd><dt>blarg:likes</dt><dd itemprop="https://blarg.example/blarg/likes"><a href="#itemdescription-b8c7a8fde8ab953a5cf5032dae5b445aad60797e2ee463097fc800e9da3abdf3">&lt;https://foo.example/two&gt;</a></dd></dl><dl itemscope="" itemtype="" id="itemdescription-7192147f234839d7b03749f54873e03093fea735e29b6e088138b928dd72be94" itemid="https://blarg.example/blarg/Item"></dl><dl itemscope="" itemtype="" id="itemdescription-0ede218fe60a5ea885351f2c74c86a42ced720b453b93f2931a20326ba2c0cc3" itemid="https://blarg.example/blarg/InnerObject"></dl><dl itemscope="" itemtype="https://blarg.example/blarg/Item" id="itemdescription-b8c7a8fde8ab953a5cf5032dae5b445aad60797e2ee463097fc800e9da3abdf3" itemid="https://foo.example/two"><dt>rdf:type</dt><dd itemprop="http://www.w3.org/1999/02/22-rdf-syntax-ns#type"><a href="#itemdescription-7192147f234839d7b03749f54873e03093fea735e29b6e088138b928dd72be94">blarg:Item</a></dd><dt>blarg:itemTitle</dt><dd itemprop="https://blarg.example/blarg/itemTitle">two thing</dd></dl></article>')
