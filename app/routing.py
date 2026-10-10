"""Distance and duration matrices from straight-line geometry or public OSRM."""
import json
import math
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


OSRM_TABLE_URL = "https://router.project-osrm.org/table/v1/driving/"


class RoutingError(ValueError):
    pass


def matrix_for(points, mode="straight_line", speed_kph=30):
    """Return (distance matrix in km/units, duration matrix in minutes, source)."""
    n = len(points)
    if mode == "straight_line":
        distances = [[math.dist(a, b) for b in points] for a in points]
        durations = [[(d / speed_kph * 60) if speed_kph else 0 for d in row] for row in distances]
        return distances, durations, "Straight-line distance with configured average speed"
    if mode != "osrm":
        raise RoutingError("Routing mode must be straight_line or osrm")
    if any(not (-180 <= lon <= 180 and -90 <= lat <= 90) for lon, lat in points):
        raise RoutingError("OSRM mode requires coordinates as longitude, latitude")
    coord_text = ";".join(f"{lon},{lat}" for lon, lat in points)
    url = OSRM_TABLE_URL + coord_text + "?annotations=distance,duration"
    try:
        with urlopen(url, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RoutingError(f"OSRM road routing failed: {exc}") from exc
    if payload.get("code") != "Ok" or not payload.get("distances") or not payload.get("durations"):
        code = payload.get("code", "unknown response")
        message = payload.get("message", "")
        raise RoutingError(f"OSRM could not build a road matrix ({code}). {message} Check coordinates are [longitude, latitude] and lie near drivable roads.")
    distances = [[value / 1000 if value is not None else math.inf for value in row] for row in payload["distances"]]
    durations = [[value / 60 if value is not None else math.inf for value in row] for row in payload["durations"]]
    if any(not math.isfinite(v) for row in distances + durations for v in row):
        raise RoutingError("OSRM returned unreachable route segments. Check that every point is in the same routable road network, close to a drivable road, and entered as [longitude, latitude]. Try the Berlin road demo for a known working example.")
    return distances, durations, "OSRM driving road distance and duration (OpenStreetMap data)"


def simulate(order, distances, durations, priorities, windows, service_minutes, departure_minute,
             priority_weight=1.0, late_penalty=10.0, closed=True, return_node=None):
    """Evaluate a closed route; windows are [start,end] minutes after midnight."""
    now = float(departure_minute)
    total_distance = 0.0
    current = 0
    stops = []
    total_late = 0.0
    total_wait = 0.0
    for index in order:
        node = index + 1
        total_distance += distances[current][node]
        arrival = now + durations[current][node]
        start, end = windows[index]
        wait = max(0.0, start - arrival)
        service_start = arrival + wait
        late = max(0.0, service_start - end)
        total_wait += wait
        total_late += late
        stops.append({"id": index, "arrival_minute": round(arrival, 1),
                      "service_start_minute": round(service_start, 1),
                      "window_end_minute": end, "wait_minutes": round(wait, 1),
                      "late_minutes": round(late, 1), "priority": priorities[index]})
        now = service_start + service_minutes[index]
        current = node
    home_node = return_node if return_node is not None else 0
    return_distance = distances[current][home_node] if (closed or return_node is not None) else 0
    return_minutes = durations[current][home_node] if (closed or return_node is not None) else 0
    total_distance += return_distance
    elapsed = now + return_minutes - departure_minute
    priority_delay = sum(position * (priority - 1) for position, i in enumerate(order)
                         for priority in [priorities[i]])
    score = total_distance + priority_weight * priority_delay + late_penalty * total_late
    return {"distance": round(total_distance, 2), "duration_minutes": round(elapsed, 1),
            "late_minutes": round(total_late, 1), "wait_minutes": round(total_wait, 1),
            "score": round(score, 2), "stops": stops}


def optimize_order(n, distances, durations, priorities, windows, service_minutes,
                   departure_minute, priority_weight=1.0, late_penalty=10.0):
    def score(order):
        return simulate(order, distances, durations, priorities, windows, service_minutes,
                        departure_minute, priority_weight, late_penalty)["score"]
    if n <= 8:
        # Exact permutation search for small, time-window constrained jobs.
        from itertools import permutations
        return min(permutations(range(n)), key=lambda order: (score(order), order)) if n else ()
    # Greedy seed, then best-improvement 2-opt and relocation.
    remaining, route, current = set(range(n)), [], 0
    while remaining:
        nxt = min(remaining, key=lambda i: (durations[current][i + 1], windows[i][1], priorities[i], i))
        route.append(nxt)
        remaining.remove(nxt)
        current = nxt + 1
    improved = True
    while improved:
        improved, best, best_route = False, score(route), route
        candidates = []
        for i in range(n - 1):
            for j in range(i + 1, n):
                candidates.append(route[:i] + route[i:j + 1][::-1] + route[j + 1:])
        for i in range(n):
            for j in range(n):
                if i != j:
                    candidate = route[:]
                    candidate.insert(j, candidate.pop(i))
                    candidates.append(candidate)
        for candidate in candidates:
            value = score(candidate)
            if value < best - 1e-9:
                improved, best, best_route = True, value, candidate
        route = best_route
    return tuple(route)


def compare_live_modification(current_location, active_order, new_index, points, priorities,
                              windows, service_minutes, departure_minute, mode,
                              priority_weight=1.0, late_penalty=10.0, speed_kph=30):
    """Compare immediate intercept (before next stop) with least-cost insertion."""
    # Node order: driver, active stops, emergency, warehouse.
    all_points = [current_location, *(points[i + 1] for i in active_order), points[new_index + 1], points[0]]
    distances, durations, source = matrix_for(all_points, mode, speed_kph)
    # Matrix nodes are driver=0, active=1..k, emergency=k+1, warehouse=k+2.
    k = len(active_order)
    warehouse_node = k + 2
    local_pr = [priorities[i] for i in active_order] + [priorities[new_index]]
    local_windows = [windows[i] for i in active_order] + [windows[new_index]]
    local_service = [service_minutes[i] for i in active_order] + [service_minutes[new_index]]
    baseline = simulate(tuple(range(k)), distances, durations, local_pr[:k],
                        local_windows[:k], local_service[:k], departure_minute,
                        priority_weight, late_penalty, closed=False, return_node=warehouse_node)
    baseline_order = list(range(k))
    # Baseline and candidates are compared from the driver now through the return to the warehouse.
    candidates = []
    for position in range(k + 1):
        order = baseline_order[:position] + [k] + baseline_order[position:]
        evaluation = simulate(order, distances, durations, local_pr, local_windows,
                              local_service, departure_minute, priority_weight, late_penalty,
                              closed=False, return_node=warehouse_node)
        candidates.append((evaluation["score"], position, order, evaluation))
    intercept = next(candidate for candidate in candidates if candidate[1] == 0)
    later_insertions = [candidate for candidate in candidates if candidate[1] > 0]
    inserted = min(later_insertions or candidates, key=lambda item: (item[0], item[1]))
    def describe(candidate, kind):
        _, position, order, evaluation = candidate
        names = [f"D{active_order[i] + 1}" if i < k else f"D{new_index + 1}" for i in order]
        for stop in evaluation["stops"]:
            stop["name"] = f"D{active_order[stop['id']] + 1}" if stop["id"] < k else f"D{new_index + 1}"
        late_stops = [f"{stop['name']} is {stop['late_minutes']} min late" for stop in evaluation["stops"] if stop["late_minutes"] > 0]
        path = [0, *(i + 1 for i in order), warehouse_node]
        route_names = ["Driver", *names, "Warehouse"]
        legs = [{"from": route_names[position], "to": route_names[position + 1],
                 "distance": round(distances[a][b], 2), "duration_minutes": round(durations[a][b], 1)}
                for position, (a, b) in enumerate(zip(path, path[1:]))]
        return {"strategy": kind, "sequence": names, "insert_before_stop": position,
                "route": route_names, "legs": legs,
                "distance": evaluation["distance"], "duration_minutes": evaluation["duration_minutes"],
                "late_minutes": evaluation["late_minutes"], "score": evaluation["score"],
                "distance_change": round(evaluation["distance"] - baseline["distance"], 2),
                "late_change": round(evaluation["late_minutes"] - baseline["late_minutes"], 1),
                "reason": "; ".join(late_stops) if late_stops else "No stop misses its time window",
                "stops": evaluation["stops"]}
    return {"baseline": baseline,
            "intercept": describe(intercept, "Immediate intercept"),
            "minimal_disruption": describe(inserted, "Lowest-cost insertion"),
            "recommended": "intercept" if intercept[0] <= inserted[0] else "minimal_disruption",
            "routing_source": source,
            "message": "The selected live route replaces the remaining route from the driver's current location and returns to the warehouse. Completed deliveries remain untouched."}
