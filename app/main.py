from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import math

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, model_validator

from app.routing import RoutingError, compare_live_modification, matrix_for, optimize_order, simulate

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Delivery Route Optimizer", description="Time-window and live route planning", version="2.0.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def minute_of_day(value: str) -> int:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError) as exc:
        raise ValueError("Times must use 24-hour HH:MM format") from exc
    return parsed.hour * 60 + parsed.minute


class RouteRequest(BaseModel):
    warehouse: Tuple[float, float]
    locations: List[Tuple[float, float]]
    priorities: List[int]
    windows: List[Tuple[str, str]] = Field(default_factory=list)
    service_minutes: List[float] = Field(default_factory=list)
    departure_time: str = "09:00"
    routing_mode: str = "straight_line"
    speed_kph: float = Field(default=30, gt=0, le=160)
    priority_weight: float = Field(default=1.0, ge=0, le=10000)
    late_penalty: float = Field(default=10.0, ge=0, le=10000)

    @model_validator(mode="after")
    def validate_request(self):
        n = len(self.locations)
        if n > 30:
            raise ValueError("A route can contain at most 30 deliveries")
        if len(self.priorities) != n:
            raise ValueError("Each delivery location must have one priority")
        if self.windows and len(self.windows) != n:
            raise ValueError("Each delivery needs a time window")
        if self.service_minutes and len(self.service_minutes) != n:
            raise ValueError("Each delivery needs a service duration")
        if any(type(p) is not int or p not in (1, 2, 3) for p in self.priorities):
            raise ValueError("Priorities must be 1 (high), 2 (medium), or 3 (low)")
        if any(not math.isfinite(float(v)) for point in [self.warehouse, *self.locations] for v in point):
            raise ValueError("Coordinates must be finite numbers")
        minute_of_day(self.departure_time)
        if self.routing_mode not in ("straight_line", "osrm"):
            raise ValueError("Routing mode must be straight_line or osrm")
        service = self.service_minutes or [0.0] * n
        if any(not math.isfinite(v) or v < 0 or v > 1440 for v in service):
            raise ValueError("Service durations must be between 0 and 1440 minutes")
        for window in self.windows:
            if len(window) != 2 or minute_of_day(window[0]) > minute_of_day(window[1]):
                raise ValueError("Time windows must be same-day intervals with start no later than end")
        return self


class LiveRequest(RouteRequest):
    current_location: Tuple[float, float]
    driver_time: str = "09:00"
    active_order: List[int]
    emergency_location: Tuple[float, float]
    emergency_priority: int = Field(default=1, ge=1, le=3)
    emergency_window: Tuple[str, str] = ("00:00", "23:59")
    emergency_service_minutes: float = Field(default=0, ge=0, le=1440)

    @model_validator(mode="after")
    def validate_live(self):
        minute_of_day(self.driver_time)
        minute_of_day(self.emergency_window[0])
        minute_of_day(self.emergency_window[1])
        if minute_of_day(self.emergency_window[0]) > minute_of_day(self.emergency_window[1]):
            raise ValueError("Emergency time window start must be no later than its end")
        if len(set(self.active_order)) != len(self.active_order) or any(i < 0 or i >= len(self.locations) for i in self.active_order):
            raise ValueError("Active order must contain unique, valid delivery numbers (zero-based indices)")
        if not all(math.isfinite(v) for v in (*self.current_location, *self.emergency_location)):
            raise ValueError("Current and emergency coordinates must be finite")
        return self


def get_windows(data):
    return [(minute_of_day(a), minute_of_day(b)) for a, b in data.windows] if data.windows else [(0, 1439)] * len(data.locations)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/optimize-route")
def optimize_route(data: RouteRequest):
    try:
        points = [data.warehouse, *data.locations]
        distances, durations, source = matrix_for(points, data.routing_mode, data.speed_kph)
        service = data.service_minutes or [0.0] * len(data.locations)
        order = list(optimize_order(len(data.locations), distances, durations, data.priorities,
                                    get_windows(data), service, minute_of_day(data.departure_time),
                                    data.priority_weight, data.late_penalty))
    except RoutingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    schedule = simulate(order, distances, durations, data.priorities, get_windows(data), service,
                        minute_of_day(data.departure_time), data.priority_weight, data.late_penalty)
    names = ["Warehouse", *(f"D{i+1}" for i in order), "Warehouse"]
    legs = []
    path = [0, *(i + 1 for i in order), 0] if order else [0, 0]
    for a, b in zip(path, path[1:]):
        legs.append({"from": "Warehouse" if a == 0 else f"D{a}",
                     "to": "Warehouse" if b == 0 else f"D{b}",
                     "distance": round(distances[a][b], 2), "duration_minutes": round(durations[a][b], 1)})
    stop_schedule = []
    schedule_by_id = {s["id"]: s for s in schedule["stops"]}
    for i in order:
        item = schedule_by_id[i]
        item.update({"name": f"D{i+1}", "window": f"{data.windows[i][0]}–{data.windows[i][1]}" if data.windows else "Any time"})
        stop_schedule.append(item)
    return {"route": names, "order": order, "total_distance": schedule["distance"],
            "total_duration_minutes": schedule["duration_minutes"], "total_cost": schedule["score"],
            "late_minutes": schedule["late_minutes"], "wait_minutes": schedule["wait_minutes"],
            "algorithm": "Exact time-window permutation search" if len(order) <= 8 else "Nearest-neighbour with 2-opt and relocate search",
            "optimality": "Exact for the configured objective" if len(order) <= 8 else "Heuristic; global optimum is not guaranteed",
            "routing_source": source, "routing_mode": data.routing_mode,
            "priority_weight": data.priority_weight, "late_penalty": data.late_penalty,
            "legs": legs, "schedule": stop_schedule}


@app.post("/modify-active-route")
def modify_active_route(data: LiveRequest):
    try:
        result = compare_live_modification(data.current_location, data.active_order,
                                           len(data.locations), [data.warehouse, *data.locations, data.emergency_location],
                                           [*data.priorities, data.emergency_priority],
                                           [*get_windows(data), (minute_of_day(data.emergency_window[0]), minute_of_day(data.emergency_window[1]))],
                                           [*(data.service_minutes or [0.0] * len(data.locations)), data.emergency_service_minutes],
                                           minute_of_day(data.driver_time), data.routing_mode,
                                           data.priority_weight, data.late_penalty, data.speed_kph)
    except RoutingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result
