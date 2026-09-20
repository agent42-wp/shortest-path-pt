#!/usr/bin/env python3
"""Streaming DIMACS road graph conversion and memory-mapped CSR access."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Iterator, Tuple

import numpy as np


def _open_graph(path: str):
    return gzip.open(path, "rt", encoding="ascii") if path.endswith(".gz") else open(path, "rt", encoding="ascii")


def _edges(path: str) -> Iterator[Tuple[int, int, int]]:
    with _open_graph(path) as stream:
        for line in stream:
            if line.startswith("a "):
                _, u, v, weight = line.split()
                yield int(u), int(v), int(weight)


def graph_metadata(path: str) -> Tuple[int, int]:
    with _open_graph(path) as stream:
        for line in stream:
            if line.startswith("p "):
                fields = line.split()
                if len(fields) >= 4 and fields[1] == "sp":
                    return int(fields[2]), int(fields[3])
    raise ValueError(f"No DIMACS shortest-path header found in {path}")


def _write_csr(prefix: Path, nodes: int, arcs: int, reverse: bool, source: str) -> None:
    degrees = np.zeros(nodes + 2, dtype=np.int64)
    for u, v, _ in _edges(source):
        degrees[v if reverse else u] += 1
    row_ptr = np.zeros(nodes + 2, dtype=np.int64)
    # Node IDs are 1-based: row_ptr[u] is the first edge of u and
    # row_ptr[u + 1] is one past its last edge.
    np.cumsum(degrees[1 : nodes + 1], out=row_ptr[2:])
    cursor = row_ptr.copy()
    col_idx = np.lib.format.open_memmap(prefix.with_suffix(".col.npy"), mode="w+", dtype=np.int32, shape=(arcs,))
    weights = np.lib.format.open_memmap(prefix.with_suffix(".weight.npy"), mode="w+", dtype=np.int32, shape=(arcs,))
    for u, v, weight in _edges(source):
        node = v if reverse else u
        index = cursor[node]
        col_idx[index] = u if reverse else v
        weights[index] = weight
        cursor[node] += 1
    np.save(prefix.with_suffix(".row.npy"), row_ptr)
    del col_idx, weights


def convert(source: str, output: str) -> Path:
    nodes, arcs = graph_metadata(source)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    prefix = out.with_suffix("")
    _write_csr(prefix, nodes, arcs, False, source)
    _write_csr(Path(str(prefix) + ".reverse"), nodes, arcs, True, source)
    meta = {"source": source, "nodes": nodes, "arcs": arcs, "format": "csr-v1"}
    prefix.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n", encoding="ascii")
    return prefix


class CSRGraph:
    """Forward CSR with an optional reverse CSR, all loaded read-only via mmap."""

    def __init__(self, prefix: str):
        base = Path(prefix).with_suffix("")
        meta = json.loads(base.with_suffix(".json").read_text(encoding="ascii"))
        self.nodes = int(meta["nodes"])
        self.arcs = int(meta["arcs"])
        self.row = np.load(base.with_suffix(".row.npy"), mmap_mode="r")
        self.col = np.load(base.with_suffix(".col.npy"), mmap_mode="r")
        self.weight = np.load(base.with_suffix(".weight.npy"), mmap_mode="r")
        reverse = Path(str(base) + ".reverse")
        self.reverse_row = np.load(reverse.with_suffix(".row.npy"), mmap_mode="r")
        self.reverse_col = np.load(reverse.with_suffix(".col.npy"), mmap_mode="r")
        self.reverse_weight = np.load(reverse.with_suffix(".weight.npy"), mmap_mode="r")

    def neighbors(self, node: int, reverse: bool = False):
        row, col, weight = (self.reverse_row, self.reverse_col, self.reverse_weight) if reverse else (self.row, self.col, self.weight)
        start, end = int(row[node]), int(row[node + 1])
        return col[start:end], weight[start:end]
