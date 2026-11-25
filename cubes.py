"""Cube generation: split one search on the choices of the first gates.

A cube is a list of [gate, op, a, b] choices. Every cube fixes gates 0 and 1
(only gate 0 when k = 1). If that gives fewer than CUBES_PER_SHARD * shards
cubes and k >= 3, cubes are replaced, one at a time, by their children (one per
choice of gate 2) until there are enough.
"""
from pysat.solvers import Cadical153

from minc import selector_choices

CUBES_PER_SHARD = 32


def make_cubes(n, mode, k, shards):
    target = CUBES_PER_SHARD * shards
    cubes = [[]]
    for g in range(min(k, 2)):
        choices = selector_choices(n, mode, g)
        cubes = [parent + [[g, *c]] for parent in cubes for c in choices]
    if k < 3:
        return cubes
    third = [[2, *c] for c in selector_choices(n, mode, 2)]
    children = []
    while cubes and len(cubes) + len(children) < target:
        parent = cubes.pop(0)
        children.extend(parent + [list(c)] for c in third)
    return cubes + children


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
