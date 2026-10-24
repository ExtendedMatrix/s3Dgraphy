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
    same_time_pairs,
)

__all__ = ['TemporalInferenceEngine', 'derive_relative_chronology',
           'mark_origin', 'origin_of', 'same_time_pairs', 'ORIGINS', 'RELATIVE_CHRONOLOGY_EDGES']
