"""#27: a matrix with redundant relations and one contradiction must fail fast.

Before, transitive_reduction enumerated every simple cycle only to print the
first; on a chain with i→i+1 and i→i+2 plus one edge from the bottom to the
top the count grows like Fibonacci (32 US: 3 s, 40 US: minutes).
"""
import time

import pytest

from s3dgraphy.temporal.inference_engine import TemporalInferenceEngine


def _redundant_chain_with_one_contradiction(n):
    edges = [(f"US{i}", f"US{i+1}") for i in range(n - 1)]
    edges += [(f"US{i}", f"US{i+2}") for i in range(n - 2)]
    edges.append((f"US{n-1}", "US0"))
    return edges


def test_one_contradiction_in_a_large_matrix_is_reported_at_once():
    engine = TemporalInferenceEngine()
    edges = _redundant_chain_with_one_contradiction(200)
    t = time.perf_counter()
    with pytest.raises(ValueError) as err:
        engine.transitive_reduction(edges)
    assert time.perf_counter() - t < 2.0
    msg = str(err.value)
    assert "Temporal graph contains cycle" in msg
    first = msg.split("cycle: ")[1].split("\n")[0].split(" → ")
    assert first[0] == first[-1] and len(first) >= 3
