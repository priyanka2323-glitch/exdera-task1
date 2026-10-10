# Delivery route optimization

## Road and time model

Planning can use straight-line distance or the OSRM driving table service. OSRM supplies a road distance and estimated drive duration for each pair; it uses longitude/latitude and OpenStreetMap road data. The public demo endpoint is not a real-time traffic feed. Straight-line mode uses a dispatcher-set average speed to estimate travel minutes.

Each delivery has a same-day time window and service duration. The scheduler accumulates drive time and service time, waits when early, and records late minutes when service starts after the window closes. The score is distance + priority weight × order delay + late penalty × late minutes. Priority 1 is most urgent. A late penalty affects ordering but does not make a delivery impossible; the UI flags each late stop.

For up to 8 stops, all permutations are evaluated exactly against this objective. Longer tours start with nearest-neighbour and are improved through 2-opt reversal and relocate moves. Thus exactness is limited to small instances and the configured score, not a guarantee of minimum distance by itself.

## Mid-route emergency updates

The live modification endpoint receives a driver's current location and an ordered list of uncompleted stops. Completed deliveries are excluded. It evaluates the emergency delivery immediately before the next active stop and at each later insertion position, simulating road distance/time, service, priorities, waiting, and time-window lateness for each candidate. It recommends the lower objective score and explains distance and lateness changes. The UI marks the recommended option and any affected late deliveries.

## Edge cases

Zero stops return a zero-distance warehouse round trip. Duplicate coordinates are supported. Inputs reject non-finite coordinates, mismatched priorities/windows/service durations, malformed times, invalid priority levels, and invalid OSRM longitude/latitude. A route is limited to 30 stops. Same-day windows cannot cross midnight. If OSRM cannot reach a point or is unavailable, the endpoint reports the failure rather than silently substituting another distance model.
