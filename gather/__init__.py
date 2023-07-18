'''gather: a (decreasingly) tiny python toolkit for gathering information
'''
__all__ = (
    'IriNamespace',
    'GatheringNorms',
    'GatheringOrganizer',
    'Gathering',
)
from .primitive_rdf import (
    IriNamespace,
)
from .gathering import (
    GatheringNorms,
    GatheringOrganizer,
    Gathering,
)
