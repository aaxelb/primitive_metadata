import rdflib


class Text(rdflib.Literal):
    # subclass to make `language` required
    def __init__(self, literal_text: str, *, language: str):
        super.__init__(literal_text, lang=language)
