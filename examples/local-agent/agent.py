"""Toy deterministic agent used to demonstrate the `command` adapter. It never calls a model."""
import argparse
import pathlib
import time

parser = argparse.ArgumentParser()
parser.add_argument("--task", required=True)
parser.add_argument("--workspace", required=True)
args = parser.parse_args()
ws = pathlib.Path(args.workspace)

if args.task == "write-module":
    (ws / "mathutils.py").write_text("def add(a, b):\n    return a + b\n")
    print("Created mathutils.py with add()")
elif args.task == "buggy-module":
    (ws / "mathutils.py").write_text("def add(a, b):\n    return a - b\n")
    print("Created mathutils.py with add()")
elif args.task == "hang":
    print("Thinking...", flush=True)
    time.sleep(60)
else:
    print(f"Unknown task: {args.task}")
    raise SystemExit(3)
