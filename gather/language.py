import dataclasses
import typing

import rdflib


@dataclasses.dataclass
class LangString:
    language_text_pairs: typing.Iterable[tuple]

    # duck-type for gather.render
    def as_rdf_valueset(self):
        for language, text in self.language_text_pairs:
            yield rdflib.Literal(text, lang=language)
