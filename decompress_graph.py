#!/usr/bin/env python3
"""Stream-decompress a DIMACS road graph from .gr.gz to .gr."""

import argparse
import gzip
import shutil
import time
from pathlib import Path


def decompress(source: Path, destination: Path, buffer_size: int = 1024 * 1024) -> float:
    if not source.exists():
        raise FileNotFoundError(source)
    if source.suffix != ".gz":
        raise ValueError("source must end with .gz")
    destination.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with gzip.open(source, "rb") as input_stream, destination.open("wb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, length=buffer_size)
    return time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="input .gr.gz file")
    parser.add_argument("--output", type=Path, help="output .gr file (default: remove .gz)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing output")
    args = parser.parse_args()
    destination = args.output or args.source.with_suffix("")
    if destination.exists() and not args.force:
        parser.error(f"output exists: {destination}; use --force to overwrite")
    elapsed = decompress(args.source, destination)
    print(f"source={args.source} output={destination} bytes={destination.stat().st_size} elapsed_seconds={elapsed:.6f}")


if __name__ == "__main__":
    main()
