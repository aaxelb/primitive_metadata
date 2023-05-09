import abc
import collections
import contextlib

import rdflib

from .exceptions import BasketCrawlError


class BasketCrawler(abc.ABC):
    '''for crawling a Basket (an RDF graph with starting focus node)

    may be helpful for rendering, serializing, analyzing
    '''

    __items_to_visit: collections.deque
    __items_visited: set
    __items_visiting: set

# # # # # # # # # # # # #
# BEGIN public interface
#

    def __init__(self, basket):
        self.basket = basket

    def crawl(self):
        self.__items_to_visit = collections.deque([self.basket.focus.iri])
        self.__items_visited = set()
        self.__items_visiting = set()
        with self._crawl_context():
            while self.__items_to_visit:
                itemid = self.__items_to_visit.popleft()
                if itemid not in self.__items_visited:
                    self._visit_item(itemid)
        return self._crawl_result()

#
# END public interface
# # # # # # # # # # # #

# # # # # # # # # # # # # #
# BEGIN "protected" interface (for subclasses)
#

    def _add_item_to_visit(self, itemid):
        self.__items_to_visit.append(itemid)

    def _has_visited_item(self, itemid):
        return itemid in self.__items_to_visit

    def _visit_item(self, itemid):
        with self.__item_context(itemid):
            property_iter = (
                self.basket
                .gathered_metadata
                .predicates(subject=itemid, unique=True)
            )
            property_set = sorted(
                property_iter,
                key=self._property_sort_key,
            )
            for property_iri in property_set:
                self._visit_itemproperty(itemid, property_iri)

    def _visit_itemproperty(self, itemid, property_iri):
        with self._itemproperty_context(itemid, property_iri):
            value_set = sorted(
                self.basket[itemid:property_iri],
                key=self._value_sort_key,
            )
            for value_obj in value_set:
                self._visit_value(itemid, property_iri, value_obj)

    def _visit_value(self, itemid, property_iri, value_obj):
        with self._itempropertyvalue_context(itemid, property_iri, value_obj):
            if isinstance(value_obj, rdflib.term.Literal):
                self._visit_literal_value(itemid, property_iri, value_obj)
            elif isinstance(value_obj, rdflib.term.BNode):
                self._visit_blank_node(itemid, property_iri, value_obj)
            elif isinstance(value_obj, rdflib.term.URIRef):
                self._visit_iri_reference(itemid, property_iri, value_obj)
            else:
                raise BasketCrawlError(f'unrecognized value ({value_obj})')

    def _display_iri(self, iri):
        return (
            self.basket
            .gathered_metadata
            .namespace_manager
            .normalizeUri(iri)
        )

    def _display_types(self, itemid):
        return sorted(
            (
                self._display_iri(iri)
                for iri in self.basket[itemid:rdflib.RDF.type]
            ),
            key=self._value_sort_key,
        )

#
# END "protected" interface (for subclasses)
# # # # # # # # # # # # # #

# # # # # # # # # # # # # # # # # #
# BEGIN subclass responsibilities
#

    @abc.abstractmethod
    def _visit_literal_value(self, itemid, property_iri, literal_value):
        raise NotImplementedError

    @abc.abstractmethod
    def _visit_blank_node(self, itemid, property_iri, blank_node):
        raise NotImplementedError

    @abc.abstractmethod
    def _visit_iri_reference(self, itemid, property_iri, iri):
        raise NotImplementedError

    @abc.abstractmethod
    def _crawl_result(self):
        raise NotImplementedError

    # optional override
    def _crawl_context(self):
        return contextlib.nullcontext()

    # optional override
    def _item_context(self, itemid):
        return contextlib.nullcontext()

    # optional override
    def _itemproperty_context(self, itemid, property_iri):
        return contextlib.nullcontext()

    # optional override
    def _itempropertyvalue_context(self, itemid, property_iri, value_obj):
        return contextlib.nullcontext()

    # optional override
    def _property_sort_key(self, property_iri):
        return property_iri  # TODO: put important/helpful properties first?

    # optional override
    def _value_sort_key(self, value_obj):
        return value_obj  # TODO: are there any values should go first/last?

#
# END subclass responsibilities
# # # # # # # # # # # # # # # # # #

# # # # # # # # # # # # # # # # # #
# BEGIN private implementation
#
    @contextlib.contextmanager
    def __item_context(self, itemid):
        if itemid in self.__items_visiting:
            raise BasketCrawlError(
                f'detected cycle on {itemid} (invalid '
                'basket.gathered_metadata graph)'
            )
        self.__items_visiting.add(itemid)
        self.__items_visited.add(itemid)
        try:
            with self._item_context(itemid):
                yield
        finally:
            self.__items_visiting.remove(itemid)
