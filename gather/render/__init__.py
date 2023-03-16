from . import turtle, jsonld, html


BASKET_RENDERER_BY_MEDIATYPE = {
    'text/turtle': turtle.render_turtle,
    'text/html': html.render_html,
    'application/ld+json': jsonld.render_jsonld,
    # 'application/api+json': render_jsonapi,
}


def get_basket_renderer(mediatype):
    try:
        return BASKET_RENDERER_BY_MEDIATYPE[mediatype]
    except KeyError:
        raise ValueError(f'unknown mediatype: {mediatype}')


if __debug__:
    import unittest

    # implement "load_tests protocol" for unittest
    def load_tests(loader, tests, pattern):
        suite = unittest.TestSuite()
        for module in (turtle, jsonld, html):
            suite.addTests(loader.loadTestsFromModule(module))
        return suite
