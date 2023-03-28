from gather.language import LangString
from gather.shacl_shape import ShaclShape


class DefinedWord(ShaclShape):
    IRI = GATHER.DefinedWord
    NAME = LangString(
        ('en', 'DefinedWord'),
    )
    DESCRIPTION = LangString(
        ('en', 'a short name for a persistently defined term'),
    )

    name: LangString


class Terminology(ShaclShape):
    IRI = GATHER.Terminology
    NAME = LangString(
        ('en', 'Terminology'),
    )
    DESCRIPTION = LangString(
        ('en', 'a set of short names with accessible, persistent definitions'),
    )

    hasPart = ShaclProperty(
        DCTERMS.hasPart,
        -v
    )
