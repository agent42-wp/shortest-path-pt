#!/usr/bin/env python3
"""Small repeatable benchmark for the CSR shortest-path backends."""

import argparse
import csv
import statistics
import time

from csr_graph import CSRGraph
from shortest_path import bidirectional_dijkstra, delta_stepping, dijkstra


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", required=True)
    parser.add_argument("--source", type=int, required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--delta", type=int, default=100)
    parser.add_argument("--output", default="benchmark.csv")
    args = parser.parse_args()
    graph = CSRGraph(args.graph)
    algorithms = {
        "dijkstra": lambda: dijkstra(graph, args.source, args.target),
        "bidirectional": lambda: bidirectional_dijkstra(graph, args.source, args.target),
        "delta": lambda: delta_stepping(graph, args.source, args.target, args.delta),
    }
    rows = []
    for name, run in algorithms.items():
        times, distance, path_nodes = [], None, None
        for _ in range(args.repeats):
            started = time.perf_counter()
            distance, path = run()
            times.append(time.perf_counter() - started)
            path_nodes = len(path)
        rows.append({
            "graph": args.graph,
            "algorithm": name,
            "source": args.source,
            "target": args.target,
            "distance": distance,
            "path_nodes": path_nodes,
            "repeats": args.repeats,
            "median_seconds": statistics.median(times),
        })
    with open(args.output, "w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['algorithm']}: distance={row['distance']} median_seconds={row['median_seconds']:.6f}")


if __name__ == "__main__":
    main()
