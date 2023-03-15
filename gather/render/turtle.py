from gather.basket import Basket


TURTLEBLOCK_DELIMITER = b'\n\n'
PREFIXBLOCK_START = b'@prefix'


def render_turtle(basket: Basket) -> str:
    # rdflib's turtle serializer:
    #   sorts keys alphabetically (by unicode string comparison)
    #   may emit blocks in any order
    turtleblocks = (
        turtleblock
        for turtleblock in (
            basket.gathered_metadata
            .serialize(format='turtle')
            .split(TURTLEBLOCK_DELIMITER)
        )
        if turtleblock  # skip empty blocks
    )
    focusblock_start = f'<{basket.focus.iri}> '.encode()

    def turtleblock_sortkey(block):
        # build a sort-key that:
        return (
            # sorts prefix block(s) first;
            (not block.startswith(PREFIXBLOCK_START)),
            # then the focus block;
            (not block.startswith(focusblock_start)),
            # then sort remaining blocks longest to shortest,
            -len(block),
            # and sort blocks of the same length by simple string comparison.
            block,
        )

    sorted_turtleblocks = sorted(
        (turtleblock.strip() for turtleblock in turtleblocks),
        key=turtleblock_sortkey,
    )
    return TURTLEBLOCK_DELIMITER.join(sorted_turtleblocks)
