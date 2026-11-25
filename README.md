# pnp-solver

Split SAT searches for pequalnp desk steps across GitHub Actions runners.

The question one search answers: **is there a circuit with k gates for the edge
function of a graph**, `f(x) = OR over edges (u, v) of x_u AND x_v`?

* mode `mono`: AND and OR gates.
* mode `not`: AND and OR gates and at most one NOT gate.

## Run on GitHub Actions

Needs Python 3.10+ and the `gh` CLI, signed in with access to this repository.

```
python drive.py --edges 0-3,1-3,0-4,2-4,0-5,1-5,3-5,0-6,2-6,3-6,4-6 --mode mono --k 8 --shards 4
```

Options: `--shards` (1 to 20, default 4), `--timeout-minutes` (per shard job,
5 to 350, default 60), `--repo`, `--out` (download folder, default `runs`).
The same inputs are on the `search` workflow in the Actions tab.

Vertices are numbered from 0. The number of inputs is the largest vertex plus one
(at most 16).

## Run locally

```
pip install python-sat==1.9.dev25
python minc.py --edges 0-1,1-2,0-2 --mode mono --k-max 8
mkdir results
python solve.py --edges 0-1,1-2,0-2 --mode mono --k 4 --shard 0 --shards 1 --out results/shard-0.json
python aggregate.py --edges 0-1,1-2,0-2 --mode mono --k 4 --shards 1 --dir results --out aggregate.json
python validate.py
```

`solve.py` also takes `--time-limit` and `--cube-timeout`, in seconds.
Report files must be named `shard-*.json`.

## Verdicts

| Verdict | Meaning |
|---|---|
| `SAT` | A circuit was found. It was evaluated on all 2^n inputs, without using the SAT encoding, both by the shard and by the aggregate step. |
| `UNSAT` | Every cube was solved and has no solution. |
| `INCOMPLETE` | No verified circuit, and at least one cube is not proved UNSAT. The cubes are listed with `TIMEOUT`, `ERROR`, `REJECTED` or `MISSING` (no report). It says nothing about whether a circuit exists. |

A green workflow run only means the search ran. Read the verdict.

## What UNSAT does and does not show

* The encoding looks for **exactly k gates** in a normal form: each AND/OR reads
  two different earlier wires, there are no constants, the last gate is the
  output, every other gate is read, and independent neighbouring gates are
  ordered. A smallest circuit can be put in this form. A circuit padded to a
  larger size cannot always be, so UNSAT at k alone does **not** rule out smaller
  circuits. To show that more than k gates are needed, get UNSAT for every size
  from 1 to k.
* No proof certificate is produced. UNSAT rests on the encoding and on the
  solver (CaDiCaL 1.5.3 through python-sat). It is not a Lean proof.

## How the split works

A cube fixes the operation and operands of gate 0, or of gates 0 and 1. It starts
with one cube per choice of gate 0, then expands cubes into one child per choice
of gate 1 until there are at least 8 cubes per shard, so the count can overshoot
that target. Shard `i` of `S` takes cubes `i, i+S, i+2S, ...`.

`check_partition` in `cubes.py` proves with the SAT solver that the cubes are
exhaustive (no assignment of the split gates is outside all of them) and disjoint
(no two can hold together). It runs in the `plan` job before any solving and again
in the `aggregate` job.

Each shard runs one solver process and stops after its first verified circuit.
The other shards keep running.
