"""Solve one shard's cubes and write a JSON report.

python solve.py --edges 0-1,1-2 --mode mono --k 3 --shard 0 --shards 4 --out shard-0.json
"""
import argparse
import json
import multiprocessing as mp
import multiprocessing.connection
import os
import time

from pysat.solvers import Cadical153

from cubes import make_cubes, shard_indices
from minc import MODES, Encoding, parse_edges
from verify import verify_circuit


def worker(conn, n, edges, mode, k):
    """Solver process body. It keeps learned clauses from cube to cube."""
    enc = Encoding(n, edges, mode, k)
    with Cadical153(bootstrap_with=enc.clauses) as sv:
        conn.send("ready")
        while True:
            cube = conn.recv()
            if sv.solve(assumptions=enc.literals(cube)):
                conn.send(("SAT", enc.circuit(sv.get_model())))
            else:
                conn.send(("UNSAT", None))


class Worker:
    """One solver process, so that a cube can be stopped on timeout."""

    def __init__(self, spec):
        ctx = mp.get_context("spawn")
        self.conn, child = ctx.Pipe()
        self.proc = ctx.Process(target=worker, args=(child, *spec), daemon=True)
        self.proc.start()
        child.close()
        self.ready = False
        self.cube = None        # index of the cube being solved
        self.started = None

    def close(self):
        self.proc.kill()
        self.proc.join()
        self.conn.close()


def largest_first(cubes, indices):
    """A cube that fixes fewer gates covers more of the search, so it goes first."""
    return sorted(indices, key=lambda i: (len(cubes[i]), i))


def solve_cubes(spec, cubes, order, workers, time_limit=None, cube_timeout=None):
    """Yield (index, status, circuit, seconds) as cubes finish, on parallel processes.

    The cube timeout counts from the moment the cube is sent to a ready worker.
    Closing the generator stops all processes.
    """
    end = None if time_limit is None else time.time() + time_limit
    pending = list(order)
    pool = []
    try:
        while pending or any(w.cube is not None for w in pool):
            if end is not None and time.time() >= end:
                for w in pool:
                    if w.cube is not None:
                        yield w.cube, "TIMEOUT", None, time.time() - w.started
                for i in pending:
                    yield i, "TIMEOUT", None, 0.0
                return
            free = sum(w.cube is None for w in pool)     # building or idle
            while len(pool) < workers and free < len(pending):
                pool.append(Worker(spec))
                free += 1
            for w in pool:
                if w.ready and w.cube is None and pending:
                    w.cube, w.started = pending.pop(0), time.time()
                    w.conn.send(cubes[w.cube])
            deadlines = [] if end is None else [end]
            if cube_timeout is not None:
                deadlines += [w.started + cube_timeout for w in pool if w.cube is not None]
            wait = max(0.0, min(deadlines) - time.time()) if deadlines else None
            readable = mp.connection.wait([w.conn for w in pool], wait)
            for w in list(pool):
                if w.conn in readable:
                    try:
                        message = w.conn.recv()
                    except (EOFError, ConnectionError):
                        pool.remove(w)
                        w.close()
                        if w.cube is not None:
                            yield w.cube, "ERROR", None, time.time() - w.started
                        elif pending:
                            # died while building: charge one cube, so the loop ends
                            yield pending.pop(0), "ERROR", None, 0.0
                        continue
                    if not w.ready:
                        w.ready = True
                    else:
                        i, w.cube = w.cube, None
                        yield (i, *message, time.time() - w.started)
                elif (cube_timeout is not None and w.cube is not None
                        and time.time() >= w.started + cube_timeout):
                    pool.remove(w)
                    w.close()
                    yield w.cube, "TIMEOUT", None, time.time() - w.started
    finally:
        for w in pool:
            w.close()


def run_shard(edges_text, mode, k, shard, shards, out, time_limit=None, cube_timeout=None,
              workers=None):
    if not 0 <= shard < shards:
        raise ValueError("need 0 <= shard < shards")
    n, edges = parse_edges(edges_text)
    cubes = make_cubes(n, mode, k, shards)
    workers = workers or os.cpu_count() or 1
    report = {
        "n": n, "edges": [list(e) for e in edges], "mode": mode, "k": k,
        "shard": shard, "shards": shards, "total_cubes": len(cubes),
        "workers": workers, "seconds": 0.0, "results": [],
    }

    def save():
        report["seconds"] = round(time.time() - start, 2)
        with open(out, "w") as fh:
            json.dump(report, fh, indent=1)

    start = time.time()
    save()
    order = largest_first(cubes, shard_indices(len(cubes), shard, shards))
    finished = solve_cubes((n, edges, mode, k), cubes, order, workers, time_limit, cube_timeout)
    try:
        for i, status, circuit, seconds in finished:
            entry = {"cube": i, "choices": cubes[i], "status": status,
                     "seconds": round(seconds, 3)}
            if status == "SAT":
                fault = verify_circuit(n, edges, mode, k, circuit)
                entry["circuit"] = circuit
                entry["verified"] = fault is None
                if fault:
                    entry["fault"] = fault
            report["results"].append(entry)
            save()
            print(f"cube {i}: {status} {entry['seconds']}s", flush=True)
            if status == "SAT":
                if not entry["verified"]:
                    raise SystemExit(f"circuit failed verification: {entry['fault']}")
                break
    finally:
        finished.close()
        save()
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="solve one shard of a split search")
    p.add_argument("--edges", required=True, help="e.g. 0-1,1-2,0-2")
    p.add_argument("--mode", choices=MODES, required=True)
    p.add_argument("--k", type=int, required=True)
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--shards", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--time-limit", type=float, help="seconds for the whole shard")
    p.add_argument("--cube-timeout", type=float, help="seconds for one cube")
    a = p.parse_args()
    run_shard(a.edges, a.mode, a.k, a.shard, a.shards, a.out, a.time_limit, a.cube_timeout)
