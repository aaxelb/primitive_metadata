'''some helpful iri namespaces
'''
from .primitive_rdf import (
    IriNamespace,
    IriShorthand,
    # core rdf namespaces
    OWL,
    RDF,
    RDFS,
    XSD,
    # namespaces for some iana controlled vocabularies
    IANA_MEDIATYPE,
    IANA_LANGUAGE,
)


# a good standard:
DCAT = IriNamespace('http://www.w3.org/ns/dcat#')

# dcat's normative namespaces (in addition to OWL, RDF, RDFS, XSD)
# https://www.w3.org/TR/vocab-dcat/#normative-namespaces
DC = IriNamespace('http://purl.org/dc/elements/1.1/')
DCTYPE = IriNamespace('http://purl.org/dc/dcmitype/')
DCTERMS = IriNamespace('http://purl.org/dc/terms/')
FOAF = IriNamespace('http://xmlns.com/foaf/0.1/')
PROV = IriNamespace('http://www.w3.org/ns/prov#')
SKOS = IriNamespace('http://www.w3.org/2004/02/skos/core#')
LOCN = IriNamespace('http://www.w3.org/ns/locn#')
ODRL = IriNamespace('http://www.w3.org/ns/odrl/2/')
TIME = IriNamespace('http://www.w3.org/2006/time#')
VCARD = IriNamespace('http://www.w3.org/2006/vcard/ns#')

# a little too "one to rule them all" for my taste, but commonly used:
SDO = IriNamespace('https://schema.org/')


# all of the above in a convenient shorthand
DEFAULT_SHORTHAND = IriShorthand({
    'dc': DC,
    'dcat': DCAT,
    'dcterms': DCTERMS,
    'dctype': DCTYPE,
    'foaf': FOAF,
    'language': IANA_LANGUAGE,
    'locn': LOCN,
    'mediatype': IANA_MEDIATYPE,
    'odrl': ODRL,
    'owl': OWL,
    'prov': PROV,
    'rdf': RDF,
    'rdfs': RDFS,
    'sdo': SDO,
    'skos': SKOS,
    'time': TIME,
    'vcard': VCARD,
    'xsd': XSD,
})
