"""Dispatch a search on GitHub Actions, wait, download the reports, print the verdict.

Needs the gh CLI, signed in. Uses only the standard library.

python drive.py --edges 0-1,1-2,0-2 --mode mono --k 3 --shards 4
"""
import argparse
import json
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def find_run(repo, tag):
    for _ in range(30):
        time.sleep(4)
        runs = json.loads(gh("run", "list", "-R", repo, "-w", "search.yml", "-L", "20",
                             "--json", "databaseId,displayTitle,url"))
        for run in runs:
            if run["displayTitle"].endswith(tag):
                return run
    raise SystemExit("dispatched, but the run did not appear; check the Actions tab")


def main():
    p = argparse.ArgumentParser(description="run a split search on GitHub Actions")
    p.add_argument("--repo", default="Chambanalyst89/pnp-solver")
    p.add_argument("--edges", required=True)
    p.add_argument("--mode", choices=("mono", "not"), required=True)
    p.add_argument("--k", type=int, required=True)
    p.add_argument("--shards", type=int, default=4)
    p.add_argument("--timeout-minutes", type=int, default=60)
    p.add_argument("--out", default="runs", help="download directory")
    a = p.parse_args()

    tag = uuid.uuid4().hex[:10]
    fields = {"edges": a.edges, "mode": a.mode, "k": a.k, "shards": a.shards,
              "timeout-minutes": a.timeout_minutes, "tag": tag}
    gh("workflow", "run", "search.yml", "-R", a.repo,
       *[x for key, value in fields.items() for x in ("-f", f"{key}={value}")])
    run = find_run(a.repo, tag)
    run_id = str(run["databaseId"])
    print("run:", run["url"], flush=True)

    errors = 0
    while True:
        try:
            state = json.loads(gh("run", "view", run_id, "-R", a.repo, "--json",
                                  "status,conclusion,createdAt,updatedAt"))
            errors = 0
        except subprocess.CalledProcessError as err:
            errors += 1
            if errors >= 5:
                raise SystemExit(f"lost contact with the run: {err.stderr}")
            state = {"status": "unknown"}
        if state["status"] == "completed":
            break
        time.sleep(15)

    wall = (datetime.fromisoformat(state["updatedAt"].replace("Z", "+00:00"))
            - datetime.fromisoformat(state["createdAt"].replace("Z", "+00:00"))).total_seconds()
    print(f"workflow {state['conclusion']}, wall time {wall:.0f}s")

    target = Path(a.out) / run_id
    gh("run", "download", run_id, "-R", a.repo, "-D", str(target))
    path = target / "aggregate" / "aggregate.json"
    if not path.exists():
        raise SystemExit(f"no aggregate result; see {run['url']}")
    result = json.loads(path.read_text())
    print(f"{result['verdict']}: {result['unsat_cubes']}/{result['total_cubes']} cubes UNSAT")
    for key in ("circuit", "unfinished", "problems"):
        if result.get(key):
            print(f"{key}: {json.dumps(result[key])}")
    print("reports:", target)


if __name__ == "__main__":
    main()
