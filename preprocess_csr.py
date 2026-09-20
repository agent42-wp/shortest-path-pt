#!/usr/bin/env python3
"""Convert a DIMACS .gr/.gr.gz graph to forward and reverse CSR arrays."""

import argparse
import time

from csr_graph import convert


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("graph")
    parser.add_argument("--output", required=True, help="output prefix, e.g. data/NY")
    args = parser.parse_args()
    started = time.perf_counter()
    prefix = convert(args.graph, args.output)
    print(f"output={prefix} elapsed_seconds={time.perf_counter() - started:.3f}")


if __name__ == "__main__":
    main()
