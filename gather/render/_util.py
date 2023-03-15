import abc
import collections
import contextlib

import rdflib

from .exceptions import BasketRenderError


class BasketCrawler(abc.ABC):
    _items_to_visit: collections.deque
    _items_visited: set

    def __init__(self, basket):
        self.basket = basket

    def crawl(self):
        self._items_to_visit = collections.deque([self.basket.focus.iri])
        self._items_visited = set()
        with self.crawl_context():
            while self._items_to_visit:
                itemid = self._items_to_visit.popleft()
                if itemid not in self._items_visited:
                    self._items_visited.add(itemid)
                    self.visit_item(itemid)
        return self.crawl_result()

    def add_item_to_visit(self, itemid):
        self._items_to_visit.append(itemid)

    @abc.abstractmethod
    def crawl_result(self):
        raise NotImplementedError

    @abc.abstractmethod
    def visit_literal_value(self, itemid, property_iri, literal_value):
        raise NotImplementedError

    @abc.abstractmethod
    def visit_blank_node(self, itemid, property_iri, blank_node):
        raise NotImplementedError

    @abc.abstractmethod
    def visit_iri_reference(self, itemid, property_iri, iri):
        raise NotImplementedError

    # optional override
    @contextlib.contextmanager
    def crawl_context(self):
        yield

    # optional override
    @contextlib.contextmanager
    def item_context(self, itemid):
        yield

    # optional override
    @contextlib.contextmanager
    def itemproperty_context(self, itemid, property_iri):
        yield

    # optional override
    @contextlib.contextmanager
    def itempropertyvalue_context(self, itemid, property_iri, value_obj):
        yield

    # optional override
    def property_sort_key(self, property_iri):
        return property_iri  # TODO: put important/helpful properties first

    # optional override
    def value_sort_key(self, value_obj):
        return value_obj  # TODO: are there any values should go first/last?

    def visit_item(self, itemid):
        with self.item_context(itemid):
            property_iter = (
                self.basket
                .gathered_metadata
                .predicates(subject=itemid, unique=True)
            )
            property_set = sorted(property_iter, key=self.property_sort_key)
            for property_iri in property_set:
                self.visit_itemproperty(itemid, property_iri)

    def visit_itemproperty(self, itemid, property_iri):
        with self.itemproperty_context(itemid, property_iri):
            value_set = sorted(
                set(self.basket[itemid:property_iri]),
                key=self.value_sort_key,
            )
            for value_obj in value_set:
                self.visit_value(itemid, property_iri, value_obj)

    def visit_value(self, itemid, property_iri, value_obj):
        with self.itempropertyvalue_context(itemid, property_iri, value_obj):
            if isinstance(value_obj, rdflib.term.Literal):
                self.visit_literal_value(itemid, property_iri, value_obj)
            elif isinstance(value_obj, rdflib.term.BNode):
                self.visit_blank_node(itemid, property_iri, value_obj)
            elif isinstance(value_obj, rdflib.term.URIRef):
                self.visit_iri_reference(itemid, property_iri, value_obj)
            else:
                raise BasketRenderError(f'unrecognized value ({value_obj})')

    # oft-repeated utility
    def display_iri(self, iri):
        return (
            self.basket
            .gathered_metadata
            .namespace_manager
            .normalizeUri(iri)
        )
