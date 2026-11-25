"""Solve one shard's cubes and write a JSON report.

python solve.py --edges 0-1,1-2 --mode mono --k 3 --shard 0 --shards 4 --out shard-0.json
"""
import argparse
import json
import multiprocessing as mp
import time

from pysat.solvers import Cadical153

from cubes import make_cubes, shard_indices
from minc import MODES, Encoding, parse_edges
from verify import verify_circuit


def worker(conn, n, edges, mode, k):
    """One solver process. It keeps learned clauses from cube to cube."""
    enc = Encoding(n, edges, mode, k)
    with Cadical153(bootstrap_with=enc.clauses) as sv:
        conn.send("ready")
        while True:
            cube = conn.recv()
            if sv.solve(assumptions=enc.literals(cube)):
                conn.send(("SAT", enc.circuit(sv.get_model())))
            else:
                conn.send(("UNSAT", None))


class Solver:
    """Runs the worker in a child process so that a cube can be stopped on timeout."""

    def __init__(self, *spec):
        self.spec = spec
        self.proc = None

    def solve(self, cube, timeout):
        start = time.time()
        if self.proc is None:
            self.conn, child = mp.Pipe()
            self.proc = mp.Process(target=worker, args=(child, *self.spec), daemon=True)
            self.proc.start()
            child.close()
            if not self._wait(timeout):
                return self._stop("TIMEOUT")
            try:
                self.conn.recv()
            except EOFError:
                return self._stop("ERROR")
        self.conn.send(cube)
        left = None if timeout is None else max(0.0, timeout - (time.time() - start))
        if not self._wait(left):
            return self._stop("TIMEOUT")
        try:
            return self.conn.recv()
        except EOFError:
            return self._stop("ERROR")

    def _wait(self, timeout):
        return self.conn.poll(timeout)

    def _stop(self, status):
        self.close()
        return status, None

    def close(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.join()
            self.conn.close()
            self.proc = None


def run_shard(edges_text, mode, k, shard, shards, out, time_limit=None, cube_timeout=None):
    if not 0 <= shard < shards:
        raise ValueError("need 0 <= shard < shards")
    n, edges = parse_edges(edges_text)
    cubes = make_cubes(n, mode, k, shards)
    report = {
        "n": n, "edges": [list(e) for e in edges], "mode": mode, "k": k,
        "shard": shard, "shards": shards, "total_cubes": len(cubes),
        "seconds": 0.0, "results": [],
    }

    def save():
        report["seconds"] = round(time.time() - start, 2)
        with open(out, "w") as fh:
            json.dump(report, fh, indent=1)

    start = time.time()
    save()
    solver = Solver(n, edges, mode, k)
    try:
        for i in shard_indices(len(cubes), shard, shards):
            limits = [cube_timeout]
            if time_limit is not None:
                limits.append(time_limit - (time.time() - start))
            limits = [x for x in limits if x is not None]
            timeout = min(limits) if limits else None
            t = time.time()
            if timeout is not None and timeout <= 0:
                status, circuit = "TIMEOUT", None
            else:
                status, circuit = solver.solve(cubes[i], timeout)
            entry = {"cube": i, "choices": cubes[i], "status": status,
                     "seconds": round(time.time() - t, 3)}
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
        solver.close()
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
