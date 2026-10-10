# Delivery Route Optimizer

FastAPI web application for round-trip delivery planning, time windows, road routing, and mid-route emergency stop insertion.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. Add delivery points, priorities, same-day time windows, and service duration. Select straight-line estimates or OSRM road routing. For OSRM, enter longitude/latitude coordinates close to drivable roads. Click **Load Berlin road demo** to populate a known sample from the OSRM documentation. Straight-line mode accepts planar coordinates and estimates travel time using the configured average speed.

## Deploy to Render

The root `render.yaml` defines a Singapore-region Python web service, health check, Python version, and production Uvicorn command. Push the project to a GitHub repository, then in Render choose **New → Blueprint**, connect that repository, and apply the blueprint. Render builds with `pip install -r requirements.txt`; after deployment, open the generated `onrender.com` URL. The health endpoint is `/health` and the API documentation is available at `/docs`.

## Route API

`POST /optimize-route`

```json
{
  "warehouse": [-73.9857, 40.7484],
  "locations": [[-73.98, 40.75], [-73.97, 40.76]],
  "priorities": [1, 2],
  "windows": [["10:00", "10:30"], ["11:00", "12:00"]],
  "service_minutes": [8, 10],
  "departure_time": "09:30",
  "routing_mode": "osrm",
  "priority_weight": 1,
  "late_penalty": 10
}
```

Times use local 24-hour `HH:MM` values and same-day windows. Waiting is allowed if a driver arrives early. Late arrivals are allowed and add the configured penalty per minute to the objective; the result includes the lateness and schedule for each stop. The service duration is added after delivery. A zero-stop route is valid.

OSRM mode calls the public OSRM Table service for driving distance and duration using OpenStreetMap data. Public OSRM provides route estimates, not live traffic. If the service is unavailable, returns unreachable segments, or coordinates are not valid longitude/latitude, the request returns a clear error instead of silently using straight-line distance. For reliable production use, configure a self-hosted OSRM endpoint or routing provider.

## Suggested company acceptance cases

| Case | Example | Expected result |
| --- | --- | --- |
| Typical route | Berlin demo or 3–5 local stops | Closed route, leg distance/time, and schedule are returned |
| No stops | Empty `locations` and `priorities` | Warehouse-to-warehouse, zero distance |
| One stop / coincident stops | One delivery, or two with equal coordinates | Valid route; zero-length legs are allowed |
| Valid time window | Arrival before opening | Wait time is reported; stop is on time |
| Missed window | Arrival after close | Lateness and penalty are shown; stop is visually flagged |
| Emergency insertion | Driver location, uncompleted stop sequence, urgent new stop | Intercept and later insertion are scored; completed stops stay excluded |
| Input validation | Mismatched list lengths, invalid priority, malformed time, non-finite coordinate | Request is rejected with a validation message |
| OSRM coordinate/network failure | Use toy grid coordinates such as `[0,0]`, swapped latitude/longitude, or a point far from a road | Clear routing error; no silent straight-line fallback |
| Larger workload | 9–30 deliveries | Heuristic plan is returned and marked as not guaranteed globally optimal |

Current limits: at most 30 deliveries, priorities 1–3, 24-hour same-day windows that cannot cross midnight. OSRM must be able to snap every point to a connected drivable road network. The public demo server can be unavailable or restrict requests, so it is suitable for development/demo rather than an availability guarantee.

## Live route modification

`POST /modify-active-route` accepts the current driver location, the still-active stop indices, an emergency stop and window, and the same routing/schedule configuration. The completed deliveries are omitted from `active_order` and remain untouched. The planner compares:

- Immediate interception: serve the emergency order before the next active stop.
- Lowest-cost insertion: insert it later in the active sequence where the combined distance, priority, and time-window score is lowest.

It recommends the lower-score option and reports distance change, lateness change, affected stops, and the resulting active sequence. The page immediately applies the recommended route to the main route-intelligence panel, including its sequence, legs, distance, and schedule; either strategy can be applied manually afterward. The dispatcher can edit the active uncompleted sequence before comparing.

## Optimization method

The score is `distance + priority_weight × priority_delay + late_penalty × late_minutes`. Priority 1 is highest; delaying a lower-urgency delivery has a smaller order penalty. Early arrivals wait until the time window opens. For up to 8 stops, the planner evaluates all permutations and chooses the exact minimum for this objective. Larger routes use a nearest-neighbour seed followed by 2-opt and relocation improvements; this is a heuristic. Live modification evaluates every possible insertion position in the active sequence.

OSRM duration estimates are used to simulate arrival times. Straight-line mode derives approximate travel minutes from distance and average speed. Traffic varies in reality and is not modeled by the public OSRM demo server. Time windows cannot cross midnight in this version.
