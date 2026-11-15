#!/usr/bin/env python3
"""
mars_router.py - Quantumions backend routing engine
====================================================

Models a Martian region as a 2D weighted grid and finds low-risk / low-energy
routes with two solvers:

  * Classical : weighted A* over the full grid (10x10 demo ... 100x100+).
  * Quantum   : QAOA (COBYLA optimiser) on a small *waypoint graph* distilled
                from the grid, with shortest path written as a QUBO with
                flow-conservation constraints (qiskit_optimization).

Why a waypoint graph for the quantum side?
    A QUBO shortest path needs one qubit per directed arc. A 4x4 grid already
    has 48 arcs (= 48 qubits), far beyond statevector simulation. The default
    4-node waypoint overlay is capped at 6 directed-arc variables to keep the
    demo simulator small. Edge weights come from real A* legs on the full
    terrain, so the quantum route can be expanded and scored on the grid.
    The circuit size is capped. Classical leg construction still depends on grid size.

Dependencies
    required : numpy
    optional : qiskit>=1.2, qiskit-algorithms>=0.4, qiskit-optimization>=0.7
               (qiskit-aer only if you pass --backend aer)

Usage
    python mars_router.py --pretty
    python mars_router.py --size 100 --seed 3 --start 0,0 --goal 99,99 --classical-only
    python mars_router.py --include-terrain --out route.json

Output (always one JSON object):
    classical_path, quantum_path, total_cost{classical,quantum},
    hazard_score{...}, execution_time_ms{...}, plus `details` and `meta`.
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np

Cell = tuple[int, int]
SQRT2 = math.sqrt(2.0)


# =============================================================================
# 1. Configuration
# =============================================================================
@dataclass(frozen=True)
class CostModel:
    """Weights that turn terrain physics into a single scalar route cost.

    cost(move) = energy_weight * energy + risk_weight * hazard
      energy : distance, inflated by slope and by actual climbing (rover battery)
      hazard : radiation + crater-rim proximity + slope-rollover risk (survival)
    """
    energy_weight: float = 1.0
    risk_weight: float = 4.0     # risk matters ~4x more than a flat metre of driving
    slope_k: float = 6.0         # extra energy per unit local grade (rise/run)
    climb_k: float = 10.0        # extra energy per cell-height of ascent in a move
    max_grade: float = 0.6       # ~31 deg: steeper moves are impassable (rollover)
    w_rad: float = 0.45          # hazard mix: radiation exposure
    w_crater: float = 0.30       # hazard mix: proximity to crater rims
    w_slope: float = 0.25        # hazard mix: slope
    cell_size_m: float = 100.0   # reference length used to normalize scores


@dataclass(frozen=True)
class QuantumConfig:
    n_waypoints: int = 4         # nodes in the waypoint graph (incl. start & goal)
    k_nearest: int = 2           # initial waypoint-graph connectivity
    max_qubits: int = 6          # = max directed arcs (one qubit per arc)
    reps: int = 1                # QAOA depth p (laptop-friendly default)
    maxiter: int = 8              # bounded optimizer budget for a fast live demo
    shots: int = 1024             # samples per circuit evaluation
    cvar_alpha: float = 0.25     # CVaR aggregation: optimise the best 25% of samples
    penalty_factor: float = 2.0  # stronger flow-conservation bias; must stay >1
    backend: str = "statevector" # "statevector" | "aer"
    seed: int = 7
    verify: bool = True          # brute-force check that the QUBO ground state is correct


# =============================================================================
# 2. Terrain generation
# =============================================================================
class Terrain:
    """Grid terrain with cached per-cell fields and edge-cost evaluation."""

    def __init__(self, elevation, radiation, crater_prox, crater_mask, craters, model: CostModel,
                 spacing_m=None):
        self.model = model
        self.size = elevation.shape[0]
        self.rows, self.cols = elevation.shape
        self.dy, self.dx = spacing_m or (model.cell_size_m, model.cell_size_m)
        self.elevation = elevation          # metres
        self.radiation = radiation          # 0..1
        self.crater_prox = crater_prox      # 0..1 (1 inside / on crater)
        self.crater_mask = crater_mask      # True = impassable
        self.craters = craters              # [(row, col, radius_cells)]

        gy, gx = np.gradient(elevation, self.dy, self.dx)
        self.grade = np.hypot(gx, gy)       # local rise/run, dimensionless
        slope_norm = np.clip(self.grade / model.max_grade, 0.0, 1.0)
        self.hazard = np.clip(
            model.w_rad * radiation + model.w_crater * crater_prox + model.w_slope * slope_norm,
            0.0, 1.0,
        )
        # The "terrain cost matrix": cost to traverse one cell-length of each cell.
        # inf marks crater interiors (impassable). Edge costs average the two cells.
        cm = model.energy_weight * (1.0 + model.slope_k * self.grade) + model.risk_weight * self.hazard
        self.cost_matrix = np.where(crater_mask, np.inf, cm)

        # plain-python caches: A* is much faster on lists than on numpy scalars
        self._z = elevation.tolist()
        self._g = self.grade.tolist()
        self._h = self.hazard.tolist()
        self._x = crater_mask.tolist()

    # -- graph interface ------------------------------------------------------
    def passable(self, c: Cell) -> bool:
        r, k = c
        return 0 <= r < self.rows and 0 <= k < self.cols and not self._x[r][k]

    def edge(self, a: Cell, b: Cell, connectivity: int = 8) -> Optional[tuple[float, float, float]]:
        """Return (energy, hazard, weighted_cost) for the move a->b, or None if blocked."""
        m = self.model
        (r1, c1), (r2, c2) = a, b
        dr, dc = r2 - r1, c2 - c1
        if (max(abs(dr), abs(dc)) != 1 or (connectivity == 4 and dr and dc)
                or not self.passable(a) or not self.passable(b)):
            return None
        if dr and dc and (self._x[r1][c2] or self._x[r2][c1]):
            return None                                   # no cutting crater corners
        dist = math.hypot(dr * self.dy, dc * self.dx) / m.cell_size_m
        dz = self._z[r2][c2] - self._z[r1][c1]
        if abs(dz) / (dist * m.cell_size_m) > m.max_grade:
            return None                                   # too steep
        energy = dist * (1.0 + m.slope_k * 0.5 * (self._g[r1][c1] + self._g[r2][c2])) \
            + m.climb_k * max(dz, 0.0) / m.cell_size_m   # climbing costs more than descending
        hazard = dist * 0.5 * (self._h[r1][c1] + self._h[r2][c2])
        return energy, hazard, m.energy_weight * energy + m.risk_weight * hazard

    def moves(self, c: Cell, connectivity: int = 8) -> Iterable[tuple[Cell, float]]:
        offsets = _OFFSETS_8 if connectivity == 8 else _OFFSETS_4
        for dr, dc in offsets:
            nb = (c[0] + dr, c[1] + dc)
            e = self.edge(c, nb)
            if e is not None:
                yield nb, e[2]

    def reachable(self, start: Cell, goal: Cell, connectivity: int = 8) -> bool:
        seen, stack = {start}, [start]
        while stack:
            cur = stack.pop()
            if cur == goal:
                return True
            for nb, _ in self.moves(cur, connectivity):
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        return False

    def to_dict(self) -> dict:
        """JSON-friendly export for the map front-end (null = impassable)."""
        cm = [[None if math.isinf(v) else round(float(v), 4) for v in row] for row in self.cost_matrix]
        return {
            "size": self.size,
            "cost_matrix": cm,
            "elevation_m": np.round(self.elevation, 2).tolist(),
            "radiation": np.round(self.radiation, 4).tolist(),
            "hazard": np.round(self.hazard, 4).tolist(),
            "crater_mask": self.crater_mask.astype(int).tolist(),
            "craters": [{"row": round(r, 2), "col": round(c, 2), "radius_cells": round(rad, 2)}
                        for r, c, rad in self.craters],
        }


_OFFSETS_4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]
_OFFSETS_8 = _OFFSETS_4 + [(-1, -1), (-1, 1), (1, -1), (1, 1)]


def _normalise(a: np.ndarray) -> np.ndarray:
    lo, hi = float(a.min()), float(a.max())
    return (a - lo) / (hi - lo) if hi > lo else np.zeros_like(a)


def _smooth_noise(rng: np.random.Generator, size: int) -> np.ndarray:
    """Sum of plane waves, frequency-limited so small grids don't alias."""
    ys, xs = np.mgrid[0:size, 0:size] / max(size - 1, 1)
    field_, freq, amp = np.zeros((size, size)), 0.8, 1.0
    while freq <= max(size / 3.0, 1.0):
        for _ in range(2):                                # two directions per octave
            th, ph = rng.uniform(0, 2 * np.pi, 2)
            field_ += amp * np.sin(2 * np.pi * freq * (xs * np.cos(th) + ys * np.sin(th)) + ph)
        freq, amp = freq * 1.7, amp * 0.6
    return _normalise(field_)


def _build_terrain(size, base, hot, craters, model: CostModel) -> Terrain:
    rows, cols = np.mgrid[0:size, 0:size].astype(float)

    # Elevation: scale so the 90th-percentile cell-to-cell grade is ~0.2 regardless of grid size.
    p90 = np.percentile(np.hypot(*np.gradient(base)), 90) or 1.0
    elev = base * (0.2 * model.cell_size_m / p90)

    crater_mask = np.zeros((size, size), bool)
    prox = np.zeros((size, size))
    for cr, cc, r in craters:
        d = np.hypot(rows - cr, cols - cc)
        h_rim = 0.25 * r * model.cell_size_m
        elev += h_rim * np.exp(-(((d - r) / (0.5 * r + 0.5)) ** 2))              # raised rim
        elev -= 2.0 * h_rim * np.clip(1.0 - (d / r) ** 2, 0.0, None)            # bowl
        crater_mask |= d <= r                                                    # hazard zone
        prox = np.maximum(prox, np.exp(-np.clip(d - r, 0, None) / (0.6 * r + 0.5)))

    # Radiation: thinner atmosphere/shielding at altitude + local hotspots (0.05 floor).
    radiation = 0.05 + 0.95 * _normalise(0.5 * _normalise(elev) + 0.5 * hot)
    return Terrain(elev, radiation, prox, crater_mask, craters, model)


def generate_terrain(size: int = 10, seed: int = 7, start: Optional[Cell] = None,
                     goal: Optional[Cell] = None, model: CostModel = CostModel(),
                     crater_coverage: float = 0.12) -> Terrain:
    """Synthetic CLI fixture. Endpoints never alter its physical fields."""
    rng = np.random.default_rng(seed)

    base = _smooth_noise(rng, size)
    rows, cols = np.mgrid[0:size, 0:size].astype(float)
    hot = np.zeros((size, size))
    for _ in range(3):
        hr, hc = rng.uniform(0, size - 1, 2)
        hot += np.exp(-((rows - hr) ** 2 + (cols - hc) ** 2) / (2 * (0.15 * size + 0.5) ** 2))

    craters: list[tuple[float, float, float]] = []
    covered = np.zeros((size, size), bool)
    for _ in range(300):
        if covered.mean() >= crater_coverage:
            break
        r = max(0.9, rng.uniform(0.04, 0.09) * size)
        cr, cc = rng.uniform(0, size - 1, 2)
        # Preserve the original CLI's default corner launch and arrival sites.
        if min(math.hypot(cr, cc), math.hypot(cr-size+1, cc-size+1)) < r + 1.5:
            continue
        craters.append((float(cr), float(cc), float(r)))
        covered |= np.hypot(rows - cr, cols - cc) <= r

    return _build_terrain(size, base, hot, craters, model)


# =============================================================================
# 3. Classical weighted A*
# =============================================================================
@dataclass
class AStarResult:
    path: list[Cell]
    cost: float
    expanded: int


def astar(terrain: Terrain, start: Cell, goal: Cell, connectivity: int = 8) -> Optional[AStarResult]:
    """Weighted A* minimising total (energy + risk) cost.

    Heuristic: energy_weight * octile (8-conn) / Manhattan (4-conn) distance.
    Every real move costs >= energy_weight * step_length (slope and hazard terms
    are non-negative), so the heuristic never overestimates -> admissible and
    consistent -> the returned path is optimal.
    """
    if not (terrain.passable(start) and terrain.passable(goal)):
        raise ValueError("start and goal must be passable cells inside the grid")
    ew, (gr, gc) = terrain.model.energy_weight, goal

    def h(c: Cell) -> float:
        dr, dc = abs(c[0] - gr), abs(c[1] - gc)
        diagonal = min(dr, dc) if connectivity == 8 else 0
        meters = (diagonal * math.hypot(terrain.dx, terrain.dy)
                  + (dr - diagonal) * terrain.dy + (dc - diagonal) * terrain.dx)
        return ew * meters / terrain.model.cell_size_m

    best = {start: 0.0}
    parent: dict[Cell, Cell] = {}
    closed: set[Cell] = set()
    heap = [(h(start), 0, start)]
    tie = 0
    while heap:
        _, _, cur = heapq.heappop(heap)
        if cur in closed:
            continue
        closed.add(cur)
        if cur == goal:
            path = [cur]
            while path[-1] in parent:
                path.append(parent[path[-1]])
            return AStarResult(path[::-1], best[cur], len(closed))
        for nb, cost in terrain.moves(cur, connectivity):
            ng = best[cur] + cost
            if ng < best.get(nb, math.inf):
                best[nb], parent[nb] = ng, cur
                tie += 1
                heapq.heappush(heap, (ng + h(nb), tie, nb))
    return None


@dataclass
class PathMetrics:
    total_cost: float      # energy_weight*energy + risk_weight*hazard
    energy: float          # unweighted energy units (flat 1-cell move = 1.0)
    hazard_score: float    # integrated hazard exposure along the route (0..1 per cell-length)
    steps: int
    distance_cells: float


def evaluate_path(terrain: Terrain, path: list[Cell]) -> PathMetrics:
    """Score any cell path on the full terrain (used for both solvers)."""
    energy = hazard = dist = 0.0
    for a, b in zip(path, path[1:]):
        e = terrain.edge(a, b)
        if e is None:
            raise ValueError(f"illegal move {a}->{b}")
        energy += e[0]
        hazard += e[1]
        dist += SQRT2 if (a[0] != b[0] and a[1] != b[1]) else 1.0
    m = terrain.model
    return PathMetrics(m.energy_weight * energy + m.risk_weight * hazard, energy, hazard,
                       len(path) - 1, dist)


# =============================================================================
# 4. Waypoint graph (the subgraph the quantum solver works on)
# =============================================================================
@dataclass
class WaypointGraph:
    nodes: list[Cell]                          # nodes[0] = start, nodes[-1] = goal
    arcs: dict[tuple[int, int], float]         # directed arc -> raw route cost (from A*)
    legs: dict[tuple[int, int], list[Cell]]    # directed arc -> cell path on the grid

    @property
    def source(self) -> int:
        return 0

    @property
    def target(self) -> int:
        return len(self.nodes) - 1

    def stitch(self, node_path: list[int]) -> list[Cell]:
        cells: list[Cell] = []
        for a, b in zip(node_path, node_path[1:]):
            leg = self.legs[(a, b)]
            cells.extend(leg if not cells else leg[1:])
        return cells


def _arcs_connected(arcs: Iterable[tuple[int, int]], s: int, t: int) -> bool:
    adj: dict[int, list[int]] = {}
    for i, j in arcs:
        adj.setdefault(i, []).append(j)
    seen, stack = {s}, [s]
    while stack:
        for nxt in adj.get(stack.pop(), []):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return t in seen


def select_waypoints(terrain: Terrain, start: Cell, goal: Cell, n_waypoints: int,
                     corridor: float = 0.4) -> list[Cell]:
    """Greedy max-min-distance sampling of low-hazard cells in a corridor around start->goal."""
    s, g = np.array(start, float), np.array(goal, float)
    axis = g - s
    length = float(np.linalg.norm(axis))
    if length == 0:
        raise ValueError("start and goal must differ")
    rr, cc = np.mgrid[0:terrain.rows, 0:terrain.cols]
    vr, vc = rr - s[0], cc - s[1]
    t = (vr * axis[0] + vc * axis[1]) / length ** 2               # progress along the axis
    perp = np.abs(axis[0] * vc - axis[1] * vr) / length            # distance from the axis
    ok = (t >= 0.1) & (t <= 0.9) & (perp <= corridor * length) & ~terrain.crater_mask
    cands = [(int(r), int(c)) for r, c in zip(rr[ok], cc[ok]) if (r, c) not in (start, goal)]

    chosen: list[Cell] = [start, goal]
    inner: list[Cell] = []
    while len(chosen) < n_waypoints and cands:
        pick = max(cands, key=lambda c: min(math.dist(c, w) for w in chosen)
                   * (1.0 - 0.5 * terrain.hazard[c]))             # spread out, prefer safe cells
        chosen.append(pick)
        inner.append(pick)
        cands.remove(pick)
    inner.sort(key=lambda c: (c[0] - s[0]) * axis[0] + (c[1] - s[1]) * axis[1])
    return [start] + inner + [goal]


def build_waypoint_graph(terrain: Terrain, start: Cell, goal: Cell, cfg: QuantumConfig,
                         connectivity: int = 8) -> WaypointGraph:
    nodes = select_waypoints(terrain, start, goal, cfg.n_waypoints)
    n = len(nodes)
    if n < 3:
        raise RuntimeError("Not enough open cells to form a waypoint graph; use a larger grid.")
    s, t = 0, n - 1
    dmat = np.array([[math.dist(a, b) for b in nodes] for a in nodes])
    cache: dict[tuple[int, int], Optional[AStarResult]] = {}

    def leg(i: int, j: int) -> Optional[AStarResult]:
        if (i, j) not in cache:
            cache[(i, j)] = astar(terrain, nodes[i], nodes[j], connectivity)
        return cache[(i, j)]

    k = max(1, cfg.k_nearest)
    while True:
        pairs = {tuple(sorted((i, int(j)))) for i in range(n) for j in np.argsort(dmat[i])[1:k + 1]}
        arcs: dict[tuple[int, int], float] = {}
        legs: dict[tuple[int, int], list[Cell]] = {}
        for i, j in pairs:
            for a, b in ((i, j), (j, i)):
                # Never enter the source or leave the target (cannot help a simple s->t path),
                # and forbid a direct s->t arc so the route must actually use waypoints
                # (otherwise the "subgraph" is just the global A* answer in one hop).
                if b == s or a == t or (a, b) == (s, t):
                    continue
                res = leg(a, b)
                if res is None:
                    continue
                # A leg that physically runs through another waypoint is just the
                # concatenation of two shorter arcs; keeping it would create exact
                # cost ties (several optimal QUBO ground states) for no benefit.
                others = {w for k, w in enumerate(nodes) if k not in (a, b)}
                if others.intersection(res.path[1:-1]):
                    continue
                arcs[(a, b)], legs[(a, b)] = res.cost, res.path
        if _arcs_connected(arcs, s, t) or k >= n - 1:
            break
        k += 1                                            # densify until start can reach goal

    # Keep the QUBO small: drop the most expensive arcs while s->t stays connected.
    for arc in sorted(arcs, key=arcs.get, reverse=True):
        if len(arcs) <= cfg.max_qubits:
            break
        rest = {a for a in arcs if a != arc}
        if _arcs_connected(rest, s, t):
            del arcs[arc], legs[arc]
    if not _arcs_connected(arcs, s, t):
        raise RuntimeError("Waypoint graph is disconnected; try a different seed or more waypoints.")
    return WaypointGraph(nodes, arcs, legs)


def dijkstra_graph(graph: WaypointGraph) -> Optional[tuple[list[int], float]]:
    """Exact shortest s->t node path on the waypoint graph (reference for the quantum answer)."""
    adj: dict[int, list[tuple[int, float]]] = {}
    for (i, j), w in graph.arcs.items():
        adj.setdefault(i, []).append((j, w))
    dist, parent, heap = {graph.source: 0.0}, {}, [(0.0, graph.source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, math.inf):
            continue
        if u == graph.target:
            path = [u]
            while path[-1] in parent:
                path.append(parent[path[-1]])
            return path[::-1], d
        for v, w in adj.get(u, []):
            if d + w < dist.get(v, math.inf):
                dist[v], parent[v] = d + w, u
                heapq.heappush(heap, (d + w, v))
    return None


# =============================================================================
# 5. QUBO shortest path (flow conservation) + QAOA
# =============================================================================
# Variables : x_a in {0,1} for every directed arc a=(i->j); one qubit each.
# Objective : minimise  sum_a c_a * x_a                      (route cost)
# Constraint: for every node v,  out(v) - in(v) = b_v        (flow conservation)
#             with b_source = +1, b_target = -1, b_other = 0.
#             A set of arcs satisfying all of these is a source->target path
#             (possibly plus disjoint cycles, which only add cost, so the
#             minimiser never keeps them: all arc costs are > 0).
#
# QUBO    :  E(x) = sum_a c_a x_a  +  P * sum_v ( out_v(x) - in_v(x) - b_v )^2
# Because x^2 = x for binary variables the square expands to linear + pairwise
# terms, i.e. a quadratic unconstrained binary problem. qiskit_optimization's
# QuadraticProgramToQubo performs exactly this expansion for "==" constraints.
def normalise_costs(arcs: dict[tuple[int, int], float]) -> dict[tuple[int, int], float]:
    """Scale arc costs into (0, 1]. QAOA phase angles gamma*c_a are periodic, so a
    well-scaled Hamiltonian keeps the optimiser's search range meaningful."""
    top = max(arcs.values())
    return {a: c / top for a, c in arcs.items()}


def flow_penalty(norm_costs: dict[tuple[int, int], float], n_nodes: int, factor: float) -> float:
    """Penalty weight P for the flow-conservation constraints.

    Derivation (this is why the number is not arbitrary):
      * Net flow always sums to zero, so ANY infeasible x violates the
        conservation equation at >= 2 nodes, each by an integer >= 1.
        => penalty term >= 2P for every infeasible state, and the objective
        term is >= 0, so E_infeasible >= 2P.
      * Every feasible optimum is a simple path with <= n_nodes-1 arcs, so
        E_optimum <= L = (sum of the n_nodes-1 largest normalised arc costs).
      * Choosing 2P > L, i.e.  P = factor * L / 2  with factor > 1,
        guarantees that no infeasible bitstring can ever beat the optimum.
    Don't inflate P much beyond that: a huge P makes constraint terms dominate
    the Hamiltonian, flattens the cost landscape the QAOA angles can "see", and
    drops the probability of sampling the cheapest path. factor=1.25 is a
    safety margin of 25%.
    """
    if factor <= 1.0:
        raise ValueError("penalty_factor must be > 1 for the QUBO ground state to be a valid path")
    bound = sum(sorted(norm_costs.values(), reverse=True)[: n_nodes - 1])
    return factor * bound / 2.0


def _flow_matrices(graph: WaypointGraph, arc_list: list[tuple[int, int]]):
    """Node-arc incidence matrix M (+1 tail, -1 head) and demand vector b."""
    n = len(graph.nodes)
    M = np.zeros((n, len(arc_list)))
    for k, (i, j) in enumerate(arc_list):
        M[i, k], M[j, k] = 1.0, -1.0
    b = np.zeros(n)
    b[graph.source], b[graph.target] = 1.0, -1.0
    return M, b


def exhaustive_qubo_check(graph: WaypointGraph, norm_costs: dict, penalty: float,
                          max_qubits: int = 18) -> dict:
    """Brute-force every bitstring of the QUBO energy E(x) and confirm that the
    ground state is the Dijkstra-optimal path. Validates the *formulation*
    independently of QAOA (which is only a heuristic solver for it)."""
    arc_list = list(graph.arcs)
    n = len(arc_list)
    if n > max_qubits:
        return {"skipped": f"{n} qubits > {max_qubits}"}
    M, b = _flow_matrices(graph, arc_list)
    c = np.array([norm_costs[a] for a in arc_list])
    X = ((np.arange(2 ** n)[:, None] >> np.arange(n)) & 1).astype(float)
    imbalance = X @ M.T - b                                   # (2^n, nodes)
    violated = np.any(imbalance != 0, axis=1)
    energy = X @ c + penalty * np.sum(imbalance ** 2, axis=1)
    best = int(np.argmin(energy))
    chosen = [arc_list[k] for k in range(n) if X[best, k]]
    decoded = decode_arcs(chosen, graph)
    ref = dijkstra_graph(graph)
    return {
        "ground_state_arcs": chosen,
        "ground_state_energy": round(float(energy[best]), 6),
        # compare by cost: equal-cost alternative paths are equally correct
        "ground_state_matches_dijkstra": bool(
            decoded is not None and ref is not None
            and abs(_node_path_cost(graph, decoded) - ref[1]) < 1e-9),
        # how far the cheapest constraint-violating bitstring sits above the optimum
        "penalty_margin": round(float(energy[violated].min() - energy[best]), 6) if violated.any() else None,
    }


def decode_arcs(selected: list[tuple[int, int]], graph: WaypointGraph) -> Optional[list[int]]:
    """Follow selected arcs from source to target. None if no valid simple path."""
    out: dict[int, int] = {}
    incoming = set()
    for i, j in selected:
        if (i, j) not in graph.arcs or i in out or j in incoming:
            return None
        out[i] = j
        incoming.add(j)
    path, seen = [graph.source], {graph.source}
    while path[-1] != graph.target:
        j = out.get(path[-1])
        if j is None or j in seen:
            return None
        path.append(j)
        seen.add(j)
    return path if len(path) == len(selected) + 1 else None


def _node_path_cost(graph: WaypointGraph, node_path: list[int]) -> float:
    return sum(graph.arcs[(a, b)] for a, b in zip(node_path, node_path[1:]))


def build_flow_quadratic_program(graph: WaypointGraph, norm_costs: dict):
    """Declare the shortest-path problem with qiskit_optimization (constraints kept
    explicit; the penalty is applied later by QuadraticProgramToQubo)."""
    from qiskit_optimization import QuadraticProgram

    qp = QuadraticProgram("mars_waypoint_shortest_path")
    name = {a: f"x_{a[0]}_{a[1]}" for a in graph.arcs}
    for a in graph.arcs:
        qp.binary_var(name[a])
    qp.minimize(linear={name[a]: norm_costs[a] for a in graph.arcs})
    for v in range(len(graph.nodes)):
        lin = {name[a]: (1 if a[0] == v else -1) for a in graph.arcs if v in a}
        if lin:
            rhs = 1 if v == graph.source else -1 if v == graph.target else 0
            qp.linear_constraint(linear=lin, sense="==", rhs=rhs, name=f"flow_{v}")
    return qp, name


def _make_sampler(backend: str, shots: int, seed: int):
    if backend == "aer":
        from qiskit_aer.primitives import SamplerV2 as AerSampler
        return AerSampler(default_shots=shots, seed=seed), "aer"
    from qiskit.primitives import StatevectorSampler
    return StatevectorSampler(default_shots=shots, seed=seed), "statevector"


def _run_qaoa(qp, penalty: float, cfg: QuantumConfig, backend: str):
    from qiskit_algorithms.minimum_eigensolvers import QAOA
    from qiskit_algorithms.optimizers import COBYLA
    from qiskit_optimization.algorithms import MinimumEigenOptimizer

    sampler, used = _make_sampler(backend, cfg.shots, cfg.seed)
    rng = np.random.default_rng(cfg.seed)
    qaoa = QAOA(
        sampler=sampler,
        optimizer=COBYLA(maxiter=cfg.maxiter),
        reps=cfg.reps,
        initial_point=rng.uniform(0.1, 1.0, 2 * cfg.reps),    # [betas..., gammas...]
        aggregation=cfg.cvar_alpha,                           # CVaR: focus on the best samples
    )
    # penalty=P is the flow-conservation weight from flow_penalty(); the optimizer
    # converts the constrained QuadraticProgram -> QUBO -> Ising Hamiltonian for QAOA.
    return MinimumEigenOptimizer(qaoa, penalty=penalty).solve(qp), used


def run_quantum(terrain: Terrain, start: Cell, goal: Cell, cfg: QuantumConfig,
                connectivity: int = 8) -> dict:
    """Build the waypoint graph, solve the QUBO with QAOA, return a result dict."""
    t_pre = time.perf_counter()
    graph = build_waypoint_graph(terrain, start, goal, cfg, connectivity)
    norm = normalise_costs(graph.arcs)
    penalty = flow_penalty(norm, len(graph.nodes), cfg.penalty_factor)
    ref = dijkstra_graph(graph)
    pre_ms = (time.perf_counter() - t_pre) * 1e3

    out: dict = {
        "path": None, "metrics": None, "execution_time_ms": None, "status": "",
        "details": {
            "waypoints": [list(c) for c in graph.nodes],
            "n_qubits": len(graph.arcs),
            "arcs": [{"from": i, "to": j, "cost": round(c, 4)} for (i, j), c in graph.arcs.items()],
            "penalty_P": round(penalty, 4),
            "qaoa_reps": cfg.reps, "optimizer": f"COBYLA(maxiter={cfg.maxiter})",
            "shots": cfg.shots, "cvar_alpha": cfg.cvar_alpha,
            "preprocessing_ms": round(pre_ms, 3),
            "exact_waypoint_graph_cost": round(ref[1], 4) if ref else None,
        },
    }
    if cfg.verify:
        out["details"]["formulation_check"] = exhaustive_qubo_check(graph, norm, penalty)

    try:
        import qiskit_optimization  # noqa: F401  (fail early with a clear message)
        import qiskit_algorithms    # noqa: F401
    except ImportError as exc:
        out["status"] = f"unavailable: {exc}. pip install qiskit qiskit-algorithms qiskit-optimization"
        return out

    t0 = time.perf_counter()
    qp, name = build_flow_quadratic_program(graph, norm)
    backends = ["aer", "statevector"] if cfg.backend == "aer" else ["statevector"]
    result, used, note = None, None, None
    for be in backends:
        try:
            result, used = _run_qaoa(qp, penalty, cfg, be)
            break
        except Exception as exc:  # noqa: BLE001 - surface any backend failure, then fall back
            note = f"{be} backend failed ({type(exc).__name__}: {exc})"
            if be == backends[-1]:
                out["status"] = f"error: {note}"
                out["execution_time_ms"] = round((time.perf_counter() - t0) * 1e3, 3)
                return out
    if note:
        out["details"]["backend_note"] = note + "; fell back to statevector"
    out["details"]["backend"] = used
    post_start = time.perf_counter()
    out["details"]["optimization_sampling_ms"] = round((post_start - t0) * 1e3, 3)

    # Post-process: among all sampled bitstrings, keep the cheapest valid s->t path.
    arc_by_var = {v: a for a, v in name.items()}
    var_order = [v.name for v in qp.variables]
    best_path, best_cost, valid_prob = None, math.inf, 0.0
    for s in result.samples:
        chosen = [arc_by_var[var_order[k]] for k, bit in enumerate(s.x) if round(bit) == 1]
        node_path = decode_arcs(chosen, graph)
        if node_path is None:
            continue
        valid_prob += float(s.probability)
        cost = _node_path_cost(graph, node_path)
        if cost < best_cost:
            best_path, best_cost = node_path, cost
    out["execution_time_ms"] = round((time.perf_counter() - t0) * 1e3, 3)
    out["details"]["valid_path_probability"] = round(valid_prob, 4)

    if best_path is None:
        # QAOA is heuristic: even a correctly weighted QUBO can produce only
        # infeasible samples. The exact waypoint-graph reference is a valid,
        # deterministic fallback, and is explicitly labeled as classical.
        if ref is None:
            out["status"] = "no_valid_path_sampled_no_waypoint_fallback"
            return out
        best_path = ref[0]
        out["status"] = "fallback_exact_waypoint_graph"
        out["details"]["fallback_reason"] = "QAOA samples contained no valid flow-conserving path"
    cells = graph.stitch(best_path)
    out["path"] = cells
    out["metrics"] = evaluate_path(terrain, cells)
    out["details"]["waypoint_node_path"] = best_path
    if out["status"] != "fallback_exact_waypoint_graph":
        optimal = ref is not None and abs(best_cost - ref[1]) < 1e-9
        out["status"] = "optimal_on_waypoint_graph" if optimal else "feasible_suboptimal"
    out["details"]["postprocessing_ms"] = round((time.perf_counter() - post_start) * 1e3, 3)
    out["details"]["total_ms"] = round((time.perf_counter() - t_pre) * 1e3, 3)
    out["details"]["waypoint_gap_percent"] = round(100 * (out["metrics"].total_cost / ref[1] - 1), 5) if ref else None
    return out


# =============================================================================
# 6. Orchestration -> unified JSON
# =============================================================================
def _r(x: Optional[float], nd: int = 4) -> Optional[float]:
    return None if x is None else round(float(x), nd)


def _cells(path: Optional[list[Cell]]) -> Optional[list[list[int]]]:
    return None if path is None else [[int(r), int(c)] for r, c in path]


def solve(size: int = 10, seed: int = 7, start: Optional[Cell] = None, goal: Optional[Cell] = None,
          run_quantum_solver: bool = True, include_terrain: bool = False,
          model: CostModel = CostModel(), qcfg: QuantumConfig = QuantumConfig(),
          connectivity: int = 8) -> dict:
    start = start or (0, 0)
    goal = goal or (size - 1, size - 1)
    terrain = generate_terrain(size, seed, start, goal, model)

    t0 = time.perf_counter()
    res = astar(terrain, start, goal, connectivity)
    classical_ms = (time.perf_counter() - t0) * 1e3
    if res is None:
        raise RuntimeError("A* found no route")
    cm = evaluate_path(terrain, res.path)

    q = (run_quantum(terrain, start, goal, qcfg, connectivity) if run_quantum_solver else
         {"path": None, "metrics": None, "execution_time_ms": None, "status": "skipped", "details": {}})
    qm: Optional[PathMetrics] = q["metrics"]

    out = {
        "classical_path": _cells(res.path),
        "quantum_path": _cells(q["path"]),
        "total_cost": {"classical": _r(cm.total_cost), "quantum": _r(qm.total_cost) if qm else None},
        "hazard_score": {"classical": _r(cm.hazard_score), "quantum": _r(qm.hazard_score) if qm else None},
        "execution_time_ms": {"classical": _r(classical_ms, 3), "quantum": q["execution_time_ms"]},
        "details": {
            "classical": {"algorithm": "weighted A*", "connectivity": connectivity,
                          "nodes_expanded": res.expanded, "energy": _r(cm.energy), "steps": cm.steps},
            "quantum": {
                "algorithm": "QAOA/COBYLA on waypoint-graph QUBO (flow conservation)",
                "status": q["status"],
                "energy": _r(qm.energy) if qm else None,
                "steps": qm.steps if qm else None,
                "cost_vs_classical_pct": _r(100.0 * (qm.total_cost / cm.total_cost - 1.0), 2) if qm else None,
                **q["details"],
            },
        },
        "meta": {"grid_size": size, "seed": seed, "start": list(start), "goal": list(goal),
                 "cost_model": model.__dict__},
    }
    if include_terrain:
        out["terrain"] = terrain.to_dict()
    return out


def _cell_arg(text: str) -> Cell:
    r, c = text.split(",")
    return int(r), int(c)


def main() -> None:
    ap = argparse.ArgumentParser(description="Quantumions Mars router (classical A* + QAOA prototype)")
    ap.add_argument("--size", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--start", type=_cell_arg, help="row,col (default 0,0)")
    ap.add_argument("--goal", type=_cell_arg, help="row,col (default size-1,size-1)")
    ap.add_argument("--connectivity", type=int, choices=(4, 8), default=8)
    ap.add_argument("--classical-only", action="store_true")
    ap.add_argument("--include-terrain", action="store_true", help="embed cost matrix etc. for the map UI")
    ap.add_argument("--waypoints", type=int, default=QuantumConfig.n_waypoints)
    ap.add_argument("--max-qubits", type=int, default=QuantumConfig.max_qubits)
    ap.add_argument("--reps", type=int, default=QuantumConfig.reps)
    ap.add_argument("--maxiter", type=int, default=QuantumConfig.maxiter)
    ap.add_argument("--shots", type=int, default=QuantumConfig.shots)
    ap.add_argument("--penalty-factor", type=float, default=QuantumConfig.penalty_factor)
    ap.add_argument("--backend", choices=("statevector", "aer"), default="statevector")
    ap.add_argument("--no-verify", action="store_true", help="skip brute-force QUBO check")
    ap.add_argument("--pretty", action="store_true")
    ap.add_argument("--out", help="write JSON to this file instead of stdout")
    a = ap.parse_args()

    qcfg = QuantumConfig(n_waypoints=a.waypoints, max_qubits=a.max_qubits, reps=a.reps,
                         maxiter=a.maxiter, shots=a.shots, penalty_factor=a.penalty_factor,
                         backend=a.backend, seed=a.seed, verify=not a.no_verify)
    result = solve(a.size, a.seed, a.start, a.goal, not a.classical_only, a.include_terrain,
                   qcfg=qcfg, connectivity=a.connectivity)
    text = json.dumps(result, indent=2 if a.pretty else None)
    if a.out:
        with open(a.out, "w") as fh:
            fh.write(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
