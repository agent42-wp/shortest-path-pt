#!/usr/bin/env python3
"""Distributed Bellman-Ford for DIMACS .gr/.gr.gz road graphs.

The implementation uses synchronous supersteps.  Each worker owns the arcs
whose source node belongs to its modulo partition, reads a shared, immutable
distance snapshot, and sends candidate relaxations to the coordinator.  The
coordinator applies the minimum candidates and publishes the next snapshot.
"""

from __future__ import annotations

import argparse
import gzip
import multiprocessing as mp
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

INF = (1 << 62)

_dist = None
_adj: List[Tuple[int, int, int]] = []
_graph_path = ""
_workers = 1
_partitions: Dict[int, List[Tuple[int, int, int]]] = {}
_ranges: Dict[int, Dict[int, Tuple[int, int]]] = {}


def _open_graph(path: str):
    return gzip.open(path, "rt", encoding="ascii") if path.endswith(".gz") else open(path, "rt", encoding="ascii")


def graph_metadata(path: str) -> Tuple[int, int]:
    """Read the DIMACS problem header without loading the graph."""
    with _open_graph(path) as stream:
        for line in stream:
            if line.startswith("p "):
                fields = line.split()
                if len(fields) >= 4 and fields[1] == "sp":
                    return int(fields[2]), int(fields[3])
    raise ValueError(f"No DIMACS shortest-path header found in {path}")


def _load_partition(path: str, worker_id: int, workers: int) -> None:
    global _adj
    local: List[Tuple[int, int, int]] = []
    with _open_graph(path) as stream:
        for line in stream:
            if not line or line[0] != "a":
                continue
            _, u, v, weight = line.split()
            u_i = int(u)
            if u_i % workers == worker_id:
                local.append((u_i, int(v), int(weight)))
    local.sort(key=lambda edge: edge[0])
    source_ranges: Dict[int, Tuple[int, int]] = {}
    start = 0
    while start < len(local):
        node = local[start][0]
        end = start + 1
        while end < len(local) and local[end][0] == node:
            end += 1
        source_ranges[node] = (start, end)
        start = end
    _adj = local
    _ranges[worker_id] = source_ranges


def _relax_partition(task) -> Dict[int, Tuple[int, int]]:
    """Compute candidates for one partition and its current frontier."""
    global _adj
    partition_id, frontier, frontier_mode = task
    if partition_id not in _partitions:
        _load_partition(_graph_path, partition_id, _workers)
        _partitions[partition_id] = _adj
        _ranges[partition_id] = _ranges.get(partition_id, {})
    else:
        _adj = _partitions[partition_id]
    distances = _dist
    candidates: Dict[int, Tuple[int, int]] = {}
    if frontier_mode:
        source_ranges = _ranges[partition_id]
        for u in frontier:
            bounds = source_ranges.get(u)
            if bounds is None:
                continue
            du = distances[u]
            if du == INF:
                continue
            for index in range(*bounds):
                _, v, weight = _adj[index]
                candidate = du + weight
                previous = candidates.get(v)
                if previous is None or candidate < previous[0]:
                    candidates[v] = (candidate, u)
    else:
        for u, v, weight in _adj:
            du = distances[u]
            if du == INF:
                continue
            candidate = du + weight
            previous = candidates.get(v)
            if previous is None or candidate < previous[0]:
                candidates[v] = (candidate, u)
    return candidates


def distributed_bellman_ford(
    graph_path: str,
    source: int,
    target: Optional[int] = None,
    workers: Optional[int] = None,
    max_rounds: Optional[int] = None,
    frontier_mode: bool = True,
) -> Tuple[List[int], List[int], int, float]:
    """Return distances, predecessors, rounds and elapsed seconds."""
    nodes, arcs = graph_metadata(graph_path)
    if not 1 <= source <= nodes:
        raise ValueError(f"source must be in [1, {nodes}]")
    if target is not None and not 1 <= target <= nodes:
        raise ValueError(f"target must be in [1, {nodes}]")
    worker_count = max(1, min(workers or (os.cpu_count() or 1), nodes))
    rounds_limit = max_rounds or max(1, nodes - 1)

    # RawArray avoids serializing a many-million-element distance vector each round.
    shared_dist = mp.RawArray("q", [INF] * (nodes + 1))
    shared_dist[source] = 0
    global _dist
    _dist = shared_dist

    distances = [INF] * (nodes + 1)
    distances[source] = 0
    predecessor = [-1] * (nodes + 1)
    started = time.perf_counter()
    context = mp.get_context("fork")
    with context.Pool(
        processes=worker_count,
        initializer=_worker_initializer,
        initargs=(graph_path, worker_count, shared_dist),
    ) as pool:
        rounds = 0
        frontier = [source]
        for round_number in range(1, rounds_limit + 1):
            if frontier_mode:
                by_partition = [[] for _ in range(worker_count)]
                for node in frontier:
                    by_partition[node % worker_count].append(node)
                tasks = [(partition_id, by_partition[partition_id], True) for partition_id in range(worker_count)]
            else:
                tasks = [(partition_id, [], False) for partition_id in range(worker_count)]
            proposals = pool.map(_relax_partition, tasks)
            changed = 0
            next_frontier = []
            for proposal in proposals:
                for node, (candidate, parent) in proposal.items():
                    if candidate < distances[node]:
                        distances[node] = candidate
                        predecessor[node] = parent
                        shared_dist[node] = candidate
                        changed += 1
                        next_frontier.append(node)
            rounds = round_number
            if target is not None and distances[target] != INF:
                # Do not stop merely because target is reached: another route can
                # still improve it in a later superstep.
                pass
            if changed == 0:
                break
            frontier = next_frontier
    elapsed = time.perf_counter() - started
    return distances, predecessor, rounds, elapsed


def _worker_initializer(path: str, workers: int, shared_distances) -> None:
    global _dist, _graph_path, _workers
    _dist = shared_distances
    _graph_path = path
    _workers = workers


def reconstruct_path(predecessor: List[int], source: int, target: int) -> List[int]:
    if predecessor[target] == -1 and source != target:
        return []
    path: List[int] = []
    node = target
    while node != -1:
        path.append(node)
        if node == source:
            return list(reversed(path))
        node = predecessor[node]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path, help="DIMACS .gr or .gr.gz file")
    parser.add_argument("--source", type=int, required=True)
    parser.add_argument("--target", type=int)
    parser.add_argument("--workers", type=int,
                        default=max(1, (os.cpu_count() or 1) // 2))
    parser.add_argument("--max-rounds", type=int)
    parser.add_argument("--full-scan", action="store_true", help="scan every local edge each round (baseline)")
    args = parser.parse_args()
    nodes, arcs = graph_metadata(str(args.graph))
    distances, predecessor, rounds, elapsed = distributed_bellman_ford(
        str(args.graph), args.source, args.target, args.workers, args.max_rounds,
        not args.full_scan,
    )
    print(f"graph={args.graph} nodes={nodes} arcs={arcs} workers={args.workers}")
    print(f"rounds={rounds} elapsed_seconds={elapsed:.6f}")
    if args.target is not None:
        distance = distances[args.target]
        path = reconstruct_path(predecessor, args.source, args.target)
        print(
            f"source={args.source} target={args.target} distance={distance if distance != INF else 'unreachable'}")
        print(
            f"path_nodes={len(path)} path={' '.join(map(str, path)) if path else '(none)'}")


if __name__ == "__main__":
    main()
