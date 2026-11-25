"""Local check: split search and unsplit search find the same minimum on small graphs."""
import sys
import tempfile

from aggregate import aggregate
from minc import parse_edges, solve_unsplit
from solve import run_shard

SHARDS = 4
# name, edges, known minimum number of monotone gates (None: no value assumed)
GRAPHS = [
    ("single edge", "0-1", 1),
    ("path on 3 vertices", "0-1,1-2", 2),
    ("triangle", "0-1,1-2,0-2", 4),
    ("5-cycle", "0-1,1-2,2-3,3-4,0-4", None),
]


def split_verdict(edges, mode, k):
    with tempfile.TemporaryDirectory() as tmp:
        for shard in range(SHARDS):
            run_shard(edges, mode, k, shard, SHARDS, f"{tmp}/shard-{shard}.json")
        return aggregate(edges, mode, k, SHARDS, tmp)


def main():
    ok = True
    rows = []
    for name, edges, known in GRAPHS:
        n, parsed = parse_edges(edges)
        for mode in ("mono", "not"):
            unsplit = split = None
            for k in range(1, 13):
                if solve_unsplit(n, parsed, mode, k):
                    unsplit = k
                    break
            for k in range(1, 13):
                res = split_verdict(edges, mode, k)
                if res["problems"] or res["verdict"] == "INCOMPLETE":
                    sys.exit(f"{name} {mode} k={k}: {res}")
                if res["verdict"] == "SAT":
                    split = k
                    break
            good = split is not None and split == unsplit
            if mode == "mono" and known is not None:
                good = good and split == known
            ok = ok and good
            rows.append(f"{name:20} {mode:4} unsplit {unsplit}  split {split}  "
                        f"known {known if mode == 'mono' else '-'}  {'ok' if good else 'FAIL'}")
    print("\n--- summary ---")
    print("\n".join(rows))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
