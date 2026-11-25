"""Cube generation: split one search on the choices of gate 0 and gate 1.

A cube is a list of [gate, op, a, b] choices. Start with one cube per choice of
gate 0, then replace cubes, one at a time, by their children (one per choice of
gate 1) until there are at least CUBES_PER_SHARD * shards cubes.
"""
from pysat.solvers import Cadical153

from minc import selector_choices

CUBES_PER_SHARD = 8


def make_cubes(n, mode, k, shards):
    target = CUBES_PER_SHARD * shards
    first = [[[0, *c]] for c in selector_choices(n, mode, 0)]
    if k < 2:
        return first
    second = [[1, *c] for c in selector_choices(n, mode, 1)]
    children = []
    while first and len(first) + len(children) < target:
        parent = first.pop(0)
        children.extend(parent + [list(c)] for c in second)
    return first + children


def shard_indices(total, shard, shards):
    """Interleaved: shard i takes cubes i, i + S, i + 2S, ..."""
    return list(range(shard, total, shards))


def check_partition(enc, cubes):
    """Prove by SAT that the cubes are exhaustive and disjoint over the split gates.

    Uses only the exactly-one clauses of the split gates, which are part of the
    full formula. Exhaustive: those clauses plus the negation of every cube are
    unsatisfiable. Disjoint: no two cubes are satisfiable together.
    Raises AssertionError on failure.
    """
    gates = sorted({choice[0] for cube in cubes for choice in cube})
    base = [c for g in gates for c in enc.card[g]]
    lits = [enc.literals(cube) for cube in cubes]
    with Cadical153(bootstrap_with=base) as sv:
        if not sv.solve():
            raise AssertionError("exactly-one clauses are unsatisfiable")
        for i in range(len(lits)):
            if not sv.solve(assumptions=lits[i]):
                raise AssertionError(f"cube {i} is empty")
            for j in range(i + 1, len(lits)):
                if sv.solve(assumptions=lits[i] + lits[j]):
                    raise AssertionError(f"cubes {i} and {j} overlap")
    with Cadical153(bootstrap_with=base + [[-l for l in c] for c in lits]) as sv:
        if sv.solve():
            raise AssertionError("cubes are not exhaustive")
