#!/usr/bin/env python3
"""Shortest paths over the memory-mapped CSR format."""

from __future__ import annotations

import argparse
import heapq
import time
from typing import List, Optional, Tuple

import numpy as np

from csr_graph import CSRGraph

INF = np.iinfo(np.int64).max // 4


def dijkstra(graph: CSRGraph, source: int, target: Optional[int] = None) -> Tuple[int, List[int]]:
    distance = np.full(graph.nodes + 1, INF, dtype=np.int64)
    parent = np.full(graph.nodes + 1, -1, dtype=np.int32)
    distance[source] = 0
    queue = [(0, source)]
    while queue:
        current, node = heapq.heappop(queue)
        if current != int(distance[node]):
            continue
        if target is not None and node == target:
            break
        col, weight = graph.neighbors(node)
        for child, edge_weight in zip(col, weight):
            candidate = current + int(edge_weight)
            child = int(child)
            if candidate < int(distance[child]):
                distance[child] = candidate
                parent[child] = node
                heapq.heappush(queue, (candidate, child))
    return _result(distance, parent, source, target)


def bidirectional_dijkstra(graph: CSRGraph, source: int, target: int) -> Tuple[int, List[int]]:
    forward = np.full(graph.nodes + 1, INF, dtype=np.int64)
    backward = np.full(graph.nodes + 1, INF, dtype=np.int64)
    parent_forward = np.full(graph.nodes + 1, -1, dtype=np.int32)
    parent_backward = np.full(graph.nodes + 1, -1, dtype=np.int32)
    forward[source] = backward[target] = 0
    qf, qb = [(0, source)], [(0, target)]
    best, meeting = INF, -1
    while qf and qb:
        if qf[0][0] + qb[0][0] >= best:
            break
        if qf[0][0] <= qb[0][0]:
            current, node = heapq.heappop(qf)
            if current != int(forward[node]):
                continue
            if int(backward[node]) < INF and current + int(backward[node]) < best:
                best, meeting = current + int(backward[node]), node
            col, weight = graph.neighbors(node)
            for child, edge_weight in zip(col, weight):
                child = int(child)
                candidate = current + int(edge_weight)
                if candidate < int(forward[child]):
                    forward[child], parent_forward[child] = candidate, node
                    heapq.heappush(qf, (candidate, child))
        else:
            current, node = heapq.heappop(qb)
            if current != int(backward[node]):
                continue
            if int(forward[node]) < INF and current + int(forward[node]) < best:
                best, meeting = current + int(forward[node]), node
            col, weight = graph.neighbors(node, reverse=True)
            for child, edge_weight in zip(col, weight):
                child = int(child)
                candidate = current + int(edge_weight)
                if candidate < int(backward[child]):
                    backward[child], parent_backward[child] = candidate, node
                    heapq.heappush(qb, (candidate, child))
    if meeting < 0:
        return INF, []
    left = []
    node = meeting
    while node != -1:
        left.append(node)
        if node == source:
            break
        node = int(parent_forward[node])
    left.reverse()
    right, node = [], meeting
    while node != target:
        node = int(parent_backward[node])
        if node == -1:
            return INF, []
        right.append(node)
    return int(best), left + right


def delta_stepping(graph: CSRGraph, source: int, target: Optional[int], delta: int) -> Tuple[int, List[int]]:
    """Sequential Delta-stepping baseline; MPI parallelism is added separately."""
    distance = np.full(graph.nodes + 1, INF, dtype=np.int64)
    parent = np.full(graph.nodes + 1, -1, dtype=np.int32)
    buckets = {0: {source}}
    distance[source] = 0
    index = 0
    while buckets:
        while index not in buckets:
            index += 1
        active = buckets.pop(index)
        settled = set()
        pending = set(active)
        while pending:
            node = pending.pop()
            if int(distance[node]) // delta != index:
                continue
            settled.add(node)
            col, weight = graph.neighbors(node)
            for child, edge_weight in zip(col, weight):
                if int(edge_weight) > delta:
                    continue
                _relax(distance, parent, buckets, pending, node, int(child), int(edge_weight), delta, index)
        for node in settled:
            col, weight = graph.neighbors(node)
            for child, edge_weight in zip(col, weight):
                if int(edge_weight) <= delta:
                    continue
                _relax(distance, parent, buckets, None, node, int(child), int(edge_weight), delta, index)
        if target is not None and int(distance[target]) < INF and index >= int(distance[target]) // delta:
            # Later buckets cannot improve a settled target.
            break
    return _result(distance, parent, source, target)


def _relax(distance, parent, buckets, pending, node, child, weight, delta, current_bucket):
    candidate = int(distance[node]) + weight
    if candidate < int(distance[child]):
        old_bucket = int(distance[child]) // delta if int(distance[child]) < INF else None
        distance[child], parent[child] = candidate, node
        new_bucket = candidate // delta
        if old_bucket is not None and old_bucket in buckets:
            buckets[old_bucket].discard(child)
        buckets.setdefault(new_bucket, set()).add(child)
        if pending is not None and new_bucket == current_bucket:
            pending.add(child)


def _result(distance, parent, source, target):
    if target is None:
        return 0, []
    if int(distance[target]) >= INF:
        return INF, []
    path = []
    node = target
    while node != -1:
        path.append(int(node))
        if node == source:
            return int(distance[target]), list(reversed(path))
        node = int(parent[node])
    return INF, []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", required=True, help="CSR prefix created by preprocess_csr.py")
    parser.add_argument("--algorithm", choices=("dijkstra", "bidirectional", "delta"), default="bidirectional")
    parser.add_argument("--source", type=int, required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--delta", type=int, default=100)
    parser.add_argument("--print-path", action="store_true")
    args = parser.parse_args()
    graph = CSRGraph(args.graph)
    if not 1 <= args.source <= graph.nodes or not 1 <= args.target <= graph.nodes:
        raise SystemExit(f"source/target must be in [1, {graph.nodes}]")
    started = time.perf_counter()
    if args.algorithm == "dijkstra":
        distance, path = dijkstra(graph, args.source, args.target)
    elif args.algorithm == "bidirectional":
        distance, path = bidirectional_dijkstra(graph, args.source, args.target)
    else:
        distance, path = delta_stepping(graph, args.source, args.target, args.delta)
    elapsed = time.perf_counter() - started
    value = "unreachable" if distance >= INF else str(distance)
    print(f"algorithm={args.algorithm} nodes={graph.nodes} arcs={graph.arcs}")
    print(f"source={args.source} target={args.target} distance={value}")
    print(f"path_nodes={len(path)} elapsed_seconds={elapsed:.6f}")
    if path and args.print_path:
        print(f"path={' '.join(map(str, path))}")


if __name__ == "__main__":
    main()
