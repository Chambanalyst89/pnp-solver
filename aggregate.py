"""Combine shard reports into one verdict.

SAT         at least one circuit that passes verification here.
UNSAT       every cube of the split is reported UNSAT.
INCOMPLETE  anything else; the unfinished cubes are listed.

python aggregate.py --edges ... --mode mono --k 8 --shards 4 --dir results --out aggregate.json
"""
import argparse
import glob
import json
import os

from cubes import check_partition, make_cubes
from minc import MODES, Encoding, parse_edges
from verify import verify_circuit


def aggregate(edges_text, mode, k, shards, directory):
    n, edges = parse_edges(edges_text)
    cubes = make_cubes(n, mode, k, shards)
    check_partition(Encoding(n, edges, mode, k), cubes)
    want = {"n": n, "edges": [list(e) for e in edges], "mode": mode, "k": k,
            "shards": shards, "total_cubes": len(cubes)}
    status = {}
    circuits, problems, times = [], [], []
    for path in sorted(glob.glob(os.path.join(directory, "**", "*.json"), recursive=True)):
        name = os.path.basename(path)
        if not name.startswith("shard-"):
            continue
        try:
            with open(path) as fh:
                report = json.load(fh)
            if any(report[key] != value for key, value in want.items()):
                problems.append(f"{name}: belongs to a different search, ignored")
                continue
            for entry in report["results"]:
                i = entry["cube"]
                if not 0 <= i < len(cubes) or entry["choices"] != cubes[i]:
                    problems.append(f"{name}: cube {i} does not match the split, ignored")
                    continue
                if entry["status"] == "SAT":
                    fault = verify_circuit(n, edges, mode, k, entry["circuit"])
                    if fault:
                        problems.append(f"{name}: cube {i} circuit rejected: {fault}")
                        status[i] = "REJECTED"
                        continue
                    circuits.append(entry["circuit"])
                status[i] = entry["status"]
                times.append(entry["seconds"])
        except (ValueError, KeyError, TypeError) as err:
            problems.append(f"{name}: unreadable ({err!r})")
    unfinished = [{"cube": i, "status": status.get(i, "MISSING"), "choices": cubes[i]}
                  for i in range(len(cubes)) if status.get(i) not in ("SAT", "UNSAT")]
    unsat = sum(1 for s in status.values() if s == "UNSAT")
    if circuits:
        verdict = "SAT"
    elif unsat == len(cubes):
        verdict = "UNSAT"
    else:
        verdict = "INCOMPLETE"
    result = {**want, "verdict": verdict, "unsat_cubes": unsat,
              "cube_seconds_total": round(sum(times), 2),
              "cube_seconds_max": max(times, default=0),
              "problems": problems}
    if circuits:
        result["circuit"] = circuits[0]
    if verdict == "INCOMPLETE":
        result["unfinished"] = unfinished
    return result


def summary(result):
    lines = [f"{result['verdict']}: mode {result['mode']}, k {result['k']}, "
             f"{result['unsat_cubes']}/{result['total_cubes']} cubes UNSAT",
             f"solver time over all cubes {result['cube_seconds_total']}s, "
             f"slowest cube {result['cube_seconds_max']}s"]
    if "circuit" in result:
        lines.append(f"verified circuit (wires 0..{result['n'] - 1} are the vertices):")
        for g, (op, a, b) in enumerate(result["circuit"]):
            operands = f"w{a}" if op == "not" else f"w{a}, w{b}"
            lines.append(f"  w{result['n'] + g} = {op}({operands})")
    if "unfinished" in result:
        lines.append("unfinished cubes: " + ", ".join(
            f"{u['cube']} ({u['status']})" for u in result["unfinished"]))
    lines += [f"problem: {p}" for p in result["problems"]]
    return "\n".join(lines)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="combine shard reports")
    p.add_argument("--edges", required=True)
    p.add_argument("--mode", choices=MODES, required=True)
    p.add_argument("--k", type=int, required=True)
    p.add_argument("--shards", type=int, required=True)
    p.add_argument("--dir", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    res = aggregate(a.edges, a.mode, a.k, a.shards, a.dir)
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1)
    print(summary(res))
