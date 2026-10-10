"""Priority-aware closed-tour optimizer using deterministic local search.

For up to 11 stops, Held–Karp dynamic programming finds the exact minimum of
the documented distance-plus-priority objective. Larger routes use a
nearest-neighbour seed followed by best-improvement 2-opt and relocate moves.
"""
from math import dist, isfinite


class RouteOptimizer:
    def __init__(self, warehouse, locations, priorities, priority_weight=1.0):
        if len(locations) != len(priorities):
            raise ValueError("Each location needs a priority")
        if len(warehouse) != 2 or any(len(point) != 2 for point in locations):
            raise ValueError("Every location must have exactly two coordinates")
        points = [warehouse, *locations]
        if any(not isfinite(float(value)) for point in points for value in point):
            raise ValueError("Coordinates must be finite numbers")
        if any(type(p) is not int or p not in (1, 2, 3) for p in priorities):
            raise ValueError("Priority must be 1 (high), 2 (medium), or 3 (low)")
        if not isfinite(float(priority_weight)) or priority_weight < 0:
            raise ValueError("Priority weight must be a finite, non-negative number")
        self.warehouse = tuple(map(float, warehouse))
        self.locations = [tuple(map(float, point)) for point in locations]
        self.priorities = list(priorities)
        self.priority_weight = float(priority_weight)
        self.n = len(locations)
        self.points = [self.warehouse, *self.locations]
        self.distances = [[dist(a, b) for b in self.points] for a in self.points]

    def distance(self, a, b):
        return dist(a, b)

    def route_distance(self, route):
        if not route:
            return 0.0
        path = [0, *(i + 1 for i in route), 0]
        return sum(self.distances[a][b] for a, b in zip(path, path[1:]))

    def route_cost(self, route):
        """Distance plus weighted lateness: earlier positions favor higher priority."""
        lateness = sum(position * (priority - 1)
                       for position, i in enumerate(route)
                       for priority in [self.priorities[i]])
        return self.route_distance(route) + self.priority_weight * lateness

    def _exact(self):
        # dp[(visited mask, last)] = (cost to reach last, delivery-index path)
        dp = {}
        for i in range(self.n):
            dp[(1 << i, i)] = (self.distances[0][i + 1], (i,))
        for mask in range(1, 1 << self.n):
            for last in range(self.n):
                entry = dp.get((mask, last))
                if entry is None:
                    continue
                cost, route = entry
                for nxt in range(self.n):
                    if mask & (1 << nxt):
                        continue
                    next_mask = mask | (1 << nxt)
                    next_cost = cost + self.distances[last + 1][nxt + 1] + self.priority_weight * len(route) * (self.priorities[nxt] - 1)
                    key = (next_mask, nxt)
                    if key not in dp or next_cost < dp[key][0]:
                        dp[key] = (next_cost, route + (nxt,))
        full = (1 << self.n) - 1
        _, route = min((dp[(full, last)][0] + self.distances[last + 1][0], dp[(full, last)][1])
                       for last in range(self.n))
        return list(route)

    def _heuristic(self):
        # Nearest-neighbour route, tie-broken by priority, then improve locally.
        remaining = set(range(self.n))
        route, current = [], 0
        while remaining:
            nxt = min(remaining, key=lambda i: (self.distances[current][i + 1], self.priorities[i], i))
            route.append(nxt)
            remaining.remove(nxt)
            current = nxt + 1
        improved = True
        while improved:
            improved, best = False, self.route_cost(route)
            candidate_route = route
            for i in range(self.n - 1):
                for j in range(i + 1, self.n):
                    candidate = route[:i] + route[i:j + 1][::-1] + route[j + 1:]
                    score = self.route_cost(candidate)
                    if score < best - 1e-12:
                        best, candidate_route, improved = score, candidate, True
            for i in range(self.n):
                for j in range(self.n):
                    if i == j:
                        continue
                    candidate = route[:]
                    stop = candidate.pop(i)
                    candidate.insert(j, stop)
                    score = self.route_cost(candidate)
                    if score < best - 1e-12:
                        best, candidate_route, improved = score, candidate, True
            route = candidate_route
        return route

    def optimize(self, population_size=50, generations=100):
        # Preserve old call signature; deterministic DP/local search supersedes GA.
        if self.n == 0:
            return self.result([])
        route = self._exact() if self.n <= 11 else self._heuristic()
        return self.result(route)

    def result(self, route):
        names = ["Warehouse", *(f"D{i + 1}" for i in route), "Warehouse"]
        return {"route": names, "order": route,
                "distance": round(self.route_distance(route), 2),
                "cost": round(self.route_cost(route), 2)}
