"""SAT encoding: is there a k-gate circuit for the edge function of a graph?

Edge function: f(x) = OR over edges (u, v) of x_u AND x_v.
Circuits: AND and OR gates on two different earlier wires; in mode 'not' also
at most one NOT gate. The last gate is the output and every other gate is read.

Run directly for an unsplit search:  python minc.py --edges 0-1,1-2 --mode mono --k-max 8
"""
import argparse
import time

from pysat.formula import IDPool
from pysat.solvers import Cadical153

MODES = ("mono", "not")


def parse_edges(text):
    edges = []
    for part in text.split(","):
        u, v = (int(t) for t in part.strip().split("-"))
        if u == v or u < 0 or v < 0:
            raise ValueError(f"bad edge {part!r}")
        edges.append((min(u, v), max(u, v)))
    edges = sorted(set(edges))
    n = max(v for _, v in edges) + 1
    if n > 16:
        raise ValueError("at most 16 vertices")
    return n, edges


def selector_choices(n, mode, g):
    """Every (op, a, b) that gate g may be. NOT uses a == b."""
    m = n + g
    choices = [(o, a, b) for b in range(m) for a in range(b) for o in ("and", "or")]
    if mode == "not":
        choices += [("not", a, a) for a in range(m)]
    return choices


def edge_function(n, edges):
    return [any((x >> u) & 1 and (x >> v) & 1 for u, v in edges) for x in range(1 << n)]


class Encoding:
    def __init__(self, n, edges, mode, k):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if k < 1:
            raise ValueError("k must be at least 1")
        pool = IDPool()
        f = edge_function(n, edges)
        R = 1 << n
        V = lambda g, r: pool.id(("v", g, r))
        S = []          # S[g] maps (op, a, b) to its selector variable
        card = []       # exactly-one clauses, one list per gate
        cl = []
        for g in range(k):
            sel = {c: pool.id(("s", g) + c) for c in selector_choices(n, mode, g)}
            S.append(sel)
            L = list(sel.values())
            one = [L]
            # at most one (sequential counter)
            prev = None
            for i, l in enumerate(L):
                q = pool.id(("am", g, i))
                one.append([-l, q])
                if prev:
                    one.append([-prev, q])
                    one.append([-prev, -l])
                prev = q
            card.append(one)
            cl.extend(one)
            for (o, a, b), s in sel.items():
                for r in range(R):
                    def lit(w):
                        if w < n:
                            return bool((r >> w) & 1)
                        return V(w - n, r)
                    A, B, O = lit(a), lit(b), V(g, r)

                    def add(*lits):
                        c = [-s]
                        for l in lits:
                            if l is True:
                                return
                            if l is False:
                                continue
                            c.append(l)
                        cl.append(c)

                    neg = lambda l: (not l) if isinstance(l, bool) else -l
                    if o == "and":
                        add(neg(A), neg(B), O)
                        add(A, -O)
                        add(B, -O)
                    elif o == "or":
                        add(A, B, -O)
                        add(neg(A), O)
                        add(neg(B), O)
                    else:
                        add(A, O)
                        add(neg(A), -O)
        for r in range(R):
            cl.append([V(k - 1, r) if f[r] else -V(k - 1, r)])
        # every earlier gate is read
        for g in range(k - 1):
            cl.append([s for h in range(g + 1, k) for (o, a, b), s in S[h].items()
                       if n + g in (a, b)])
        if mode == "not":
            nots = [pool.id(("isnot", g)) for g in range(k)]
            for g in range(k):
                for (o, a, b), s in S[g].items():
                    if o == "not":
                        cl.append([-s, nots[g]])
            for i in range(k):
                for j in range(i + 1, k):
                    cl.append([-nots[i], -nots[j]])
        # order independent neighbours by operand pair
        for g in range(k - 1):
            for (o, a, b), s in S[g].items():
                for (o2, c, d), t in S[g + 1].items():
                    if n + g in (c, d):
                        continue
                    if (d, c) < (b, a):
                        cl.append([-s, -t])
        self.k = k
        self.selectors = S
        self.card = card
        self.clauses = cl

    def literals(self, cube):
        """Assumption literals for a cube [[gate, op, a, b], ...]."""
        return [self.selectors[g][(o, a, b)] for g, o, a, b in cube]

    def circuit(self, model):
        true = set(x for x in model if x > 0)
        return [list(next(c for c, s in sel.items() if s in true)) for sel in self.selectors]


def solve_unsplit(n, edges, mode, k):
    enc = Encoding(n, edges, mode, k)
    with Cadical153(bootstrap_with=enc.clauses) as sv:
        if not sv.solve():
            return None
        return enc.circuit(sv.get_model())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="unsplit search, k = k-min .. k-max")
    p.add_argument("--edges", required=True)
    p.add_argument("--mode", choices=MODES, required=True)
    p.add_argument("--k-min", type=int, default=1)
    p.add_argument("--k-max", type=int, required=True)
    args = p.parse_args()
    n, edges = parse_edges(args.edges)
    for k in range(args.k_min, args.k_max + 1):
        t = time.time()
        res = solve_unsplit(n, edges, args.mode, k)
        print(args.mode, "k", k, "SAT" if res else "UNSAT", round(time.time() - t, 1), flush=True)
        if res:
            print(res, flush=True)
            break
