from .turtle import render_turtle


BASKET_RENDERER_BY_MEDIATYPE = {
    'text/turtle': render_turtle,
    # 'text/html': render_html,
    # 'application/ld+json': render_jsonld,
    # 'application/api+json': render_jsonapi,
}


def get_basket_renderer(mediatype):
    try:
        return BASKET_RENDERER_BY_MEDIATYPE[mediatype]
    except KeyError:
        raise ValueError(f'unknown mediatype: {mediatype}')
