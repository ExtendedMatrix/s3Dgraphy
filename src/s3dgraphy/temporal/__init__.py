"""
Temporal Inference Module for s3dgraphy

Handles temporal relationship inference from topological stratigraphic relations.
"""

from .inference_engine import TemporalInferenceEngine
from .relative_chronology import (
    ORIGINS,
    RELATIVE_CHRONOLOGY_EDGES,
    derive_relative_chronology,
    mark_origin,
    origin_of,
)

__all__ = ['TemporalInferenceEngine', 'derive_relative_chronology',
           'mark_origin', 'origin_of', 'ORIGINS', 'RELATIVE_CHRONOLOGY_EDGES']
