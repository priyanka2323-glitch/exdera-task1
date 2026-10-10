
const deliveries = document.getElementById("deliveries");
const form = document.getElementById("routeForm");
const message = document.getElementById("message");
const button = document.getElementById("optimizeButton");
const addButton = document.getElementById("addDelivery");
const liveForm = document.getElementById("liveForm");
const routingMode = document.getElementById("routingMode");
const osrmDemoButton = document.getElementById("loadOsrmDemo");
let lastPayload = null;

let deliveryCount = 0;

function addDelivery(x = "", y = "", priority = 2) {
    deliveryCount++;

    const row = document.createElement("div");
    row.className = "delivery-row";

    const title = document.createElement("div");
    title.className = "delivery-title";

    const heading = document.createElement("h4");
    heading.textContent = `Delivery D${deliveryCount}`;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-button";
    remove.textContent = "Remove";
    remove.onclick = () => row.remove();

    title.append(heading, remove);

    const fields = document.createElement("div");
    fields.className = "delivery-fields";

    fields.innerHTML = `
        <label>X / Longitude
            <input type="number" step="any" class="delivery-x"
                   required placeholder="X" value="${x}">
        </label>
        <label>Y / Latitude
            <input type="number" step="any" class="delivery-y"
                   required placeholder="Y" value="${y}">
        </label>
        <label>Priority
            <select class="delivery-priority">
                <option value="1" ${priority === 1 ? "selected" : ""}>1 - High</option>
                <option value="2" ${priority === 2 ? "selected" : ""}>2 - Medium</option>
                <option value="3" ${priority === 3 ? "selected" : ""}>3 - Low</option>
            </select>
        </label>
        <label>Window opens<input type="time" class="delivery-start" value="08:00" required></label>
        <label>Window closes<input type="time" class="delivery-end" value="18:00" required></label>
        <label>Service (min)<input type="number" min="0" max="1440" class="delivery-service" value="10" required></label>
    `;
    fields.querySelector(".delivery-x").value = x;
    fields.querySelector(".delivery-y").value = y;

    row.append(title, fields);
    deliveries.appendChild(row);
}

if (addButton && deliveries) {
    addButton.addEventListener("click", () => {
        console.log("Add Stop clicked");
        addDelivery();
    });
} else {
    console.error("Add Stop button or deliveries container not found");
}

routingMode.addEventListener("change", () => {
    osrmDemoButton.hidden = routingMode.value !== "osrm";
});

osrmDemoButton.addEventListener("click", () => {
    document.getElementById("warehouseX").value = "13.388860";
    document.getElementById("warehouseY").value = "52.517037";
    deliveries.replaceChildren();
    deliveryCount = 0;
    addDelivery("13.397634", "52.529407", 1);
    addDelivery("13.428555", "52.523219", 2);
    document.getElementById("departureTime").value = "09:00";
    message.style.color = "#315841";
    message.textContent = "Berlin OSRM example loaded. These are the official sample coordinates from OSRM's documentation.";
});

// Add sample stops initially
addDelivery(2, 3, 1);
addDelivery(5, 1, 3);
addDelivery(1, 6, 2);

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = "";
    button.disabled = true;
    button.textContent = "Optimizing...";

    try {
        const rows = [...deliveries.querySelectorAll(".delivery-row")];

        const payload = {
            warehouse: [
            Number(document.getElementById("warehouseX").value),
            Number(document.getElementById("warehouseY").value)
            ],
            locations: rows.map(row => [
                Number(row.querySelector(".delivery-x").value),
                Number(row.querySelector(".delivery-y").value)
            ]),
            priorities: rows.map(row =>
                Number(row.querySelector(".delivery-priority").value)
            ),
            priority_weight: Number(document.getElementById("priorityWeight").value),
            windows: rows.map(row => [row.querySelector(".delivery-start").value, row.querySelector(".delivery-end").value]),
            service_minutes: rows.map(row => Number(row.querySelector(".delivery-service").value)),
            departure_time: document.getElementById("departureTime").value,
            routing_mode: document.getElementById("routingMode").value,
            speed_kph: Number(document.getElementById("speedKph").value),
            late_penalty: Number(document.getElementById("latePenalty").value)
        };

        const response = await fetch("/optimize-route", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.detail
                    ? (typeof result.detail === "string" ? result.detail : JSON.stringify(result.detail))
                    : "Unable to optimize route"
            );
        }

        document.getElementById("totalDistance").textContent =
            result.total_distance;
        document.getElementById("totalCost").textContent =
            result.total_cost;
        document.getElementById("algorithmInfo").textContent =
            `${result.algorithm} · ${result.optimality} · priority weight ${result.priority_weight}`;
        lastPayload = payload;
        document.getElementById("routingSource").textContent = `${result.routing_source} · ${result.total_duration_minutes} min travel and service · ${result.wait_minutes} min waiting · ${result.late_minutes} min late`;
        document.querySelector("#totalDistance + small").textContent = payload.routing_mode === "osrm" ? "road km" : "coordinate units";

        const routeSequence = document.getElementById("routeSequence");
        routeSequence.replaceChildren();
        result.route.forEach((stop, index) => {
            if (index) {
                const arrow = document.createElement("span");
                arrow.className = "route-arrow";
                arrow.textContent = "→";
                routeSequence.appendChild(arrow);
            }
            const step = document.createElement("span");
            step.className = `route-step${stop === "Warehouse" ? " is-warehouse" : ""}`;
            step.textContent = stop;
            routeSequence.appendChild(step);
        });

        const legsBody = document.getElementById("legsBody");
        legsBody.replaceChildren();

        result.legs.forEach(leg => {
            const tr = document.createElement("tr");

            [leg.from, leg.to, leg.distance, `${leg.duration_minutes} min`].forEach(value => {
                const td = document.createElement("td");
                td.textContent = value;
                tr.appendChild(td);
            });

            legsBody.appendChild(tr);
        });

        const schedule = document.getElementById("scheduleList");
        schedule.replaceChildren();
        result.schedule.forEach(stop => {
            const item = document.createElement("div");
            item.className = `schedule-item${stop.late_minutes > 0 ? " is-late" : ""}`;
            item.textContent = `${stop.name} · ${stop.window} · arrival ${formatMinute(stop.arrival_minute)}${stop.wait_minutes ? ` · wait ${stop.wait_minutes} min` : ""}${stop.late_minutes ? ` · LATE by ${stop.late_minutes} min` : " · on time"}`;
            schedule.appendChild(item);
        });
        document.getElementById("activeOrder").value = result.order.map(i => `D${i + 1}`).join(", ");
        document.getElementById("driverX").value = payload.warehouse[0];
        document.getElementById("driverY").value = payload.warehouse[1];
        document.getElementById("liveResults").textContent = "Route loaded. Update the driver's current location and compare an emergency order.";

        message.style.color = "#15803d";
        message.textContent = `Route optimized successfully across ${rows.length} delivery stop${rows.length === 1 ? "" : "s"}.`;
    } catch (error) {
        message.style.color = "#b91c1c";
        message.textContent = error.message;
    } finally {
        button.disabled = false;
        button.textContent = "Optimize Route";
    }
});

function formatMinute(value) {
    const total = Math.round(value);
    const day = Math.floor(total / 1440);
    const minutes = ((total % 1440) + 1440) % 1440;
    return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}${day ? ` (+${day}d)` : ""}`;
}

function applyLivePlan(option, result, requestPayload) {
    if (!result.emergencyName) result.emergencyName = `D${requestPayload.locations.length + 1}`;
    if (!result.emergencyCommitted) {
        lastPayload = {
            ...lastPayload,
            locations: [...lastPayload.locations, requestPayload.emergency_location],
            priorities: [...lastPayload.priorities, requestPayload.emergency_priority],
            windows: [...lastPayload.windows, requestPayload.emergency_window],
            service_minutes: [...lastPayload.service_minutes, requestPayload.emergency_service_minutes]
        };
        result.emergencyCommitted = true;
    }

    const sequence = document.getElementById("routeSequence");
    sequence.replaceChildren();
    option.route.forEach((stop, index) => {
        if (index) {
            const arrow = document.createElement("span");
            arrow.className = "route-arrow";
            arrow.textContent = "→";
            sequence.appendChild(arrow);
        }
        const step = document.createElement("span");
        step.className = `route-step${stop === "Warehouse" ? " is-warehouse" : ""}${stop === result.emergencyName ? " is-emergency" : ""}`;
        step.textContent = stop;
        sequence.appendChild(step);
    });

    document.getElementById("totalDistance").textContent = option.distance;
    document.getElementById("totalCost").textContent = option.score;
    document.querySelector("#totalDistance + small").textContent = lastPayload.routing_mode === "osrm" ? "road km" : "coordinate units";
    document.getElementById("algorithmInfo").textContent = `Live reroute applied · ${option.strategy} · remaining stops from the driver's current location`;

    const legsBody = document.getElementById("legsBody");
    legsBody.replaceChildren();
    option.legs.forEach(leg => {
        const tr = document.createElement("tr");
        [leg.from, leg.to, leg.distance, `${leg.duration_minutes} min`].forEach(value => {
            const td = document.createElement("td");
            td.textContent = value;
            tr.appendChild(td);
        });
        legsBody.appendChild(tr);
    });

    const schedule = document.getElementById("scheduleList");
    schedule.replaceChildren();
    option.stops.forEach(stop => {
        const item = document.createElement("div");
        item.className = `schedule-item${stop.late_minutes > 0 ? " is-late" : ""}`;
        const stopNumber = Number(stop.name.replace(/\D/g, "")) - 1;
        const window = stop.name === result.emergencyName
            ? requestPayload.emergency_window
            : requestPayload.windows[stopNumber];
        const windowText = window ? `${window[0]}–${window[1]}` : "Any time";
        item.textContent = `${stop.name} · ${windowText} · arrival ${formatMinute(stop.arrival_minute)}${stop.wait_minutes ? ` · wait ${stop.wait_minutes} min` : ""}${stop.late_minutes ? ` · LATE by ${stop.late_minutes} min` : " · on time"}`;
        schedule.appendChild(item);
    });
    document.getElementById("routingSource").textContent = `Live route from current driver location · ${option.duration_minutes} min to return · ${option.distance} distance · ${option.late_minutes} min late · ${option.reason}`;
    document.getElementById("activeOrder").value = option.sequence.join(", ");
    document.getElementById("driverX").value = requestPayload.current_location[0];
    document.getElementById("driverY").value = requestPayload.current_location[1];
    document.getElementById("driverTime").value = requestPayload.driver_time;
    message.style.color = "#315841";
    message.textContent = `${result.emergencyName} added. Route intelligence now reflects the recommended live route.`;
}

liveForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (!lastPayload) {
        document.getElementById("liveResults").textContent = "Optimize a route before evaluating a live order.";
        return;
    }
    const button = document.getElementById("liveButton");
    button.disabled = true;
    button.textContent = "Comparing...";
    try {
        const activeOrder = document.getElementById("activeOrder").value.match(/D\s*\d+/gi)?.map(s => Number(s.replace(/\D/g, "")) - 1) || [];
        const payload = {
            ...lastPayload,
            current_location: [Number(document.getElementById("driverX").value), Number(document.getElementById("driverY").value)],
            driver_time: document.getElementById("driverTime").value,
            active_order: activeOrder,
            emergency_location: [Number(document.getElementById("emergencyX").value), Number(document.getElementById("emergencyY").value)],
            emergency_priority: Number(document.getElementById("emergencyPriority").value),
            emergency_window: [document.getElementById("emergencyStart").value, document.getElementById("emergencyEnd").value],
            emergency_service_minutes: Number(document.getElementById("emergencyService").value)
        };
        const response = await fetch("/modify-active-route", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : JSON.stringify(result.detail));
        const root = document.getElementById("liveResults");
        root.replaceChildren();
        const summary = document.createElement("p");
        summary.className = "recommendation";
        summary.textContent = `Recommended: ${result.recommended === "intercept" ? "intercept immediately" : "insert later in the active route"}. Applying this recommendation to route intelligence now.`;
        root.appendChild(summary);
        for (const key of ["intercept", "minimal_disruption"]) {
            const option = result[key];
            const card = document.createElement("article");
            card.className = `option-card${result.recommended === key ? " is-recommended" : ""}`;
            const title = document.createElement("h4");
            title.textContent = `${option.strategy}${result.recommended === key ? " · Recommended" : ""}`;
            const detail = document.createElement("p");
            detail.textContent = `${option.sequence.join(" → ") || "No remaining stops"} · ${option.distance_change >= 0 ? "+" : ""}${option.distance_change} distance vs current · ${option.duration_minutes} min · ${option.late_minutes} min late (${option.late_change >= 0 ? "+" : ""}${option.late_change}) · score ${option.score}. ${option.reason}`;
            const applyButton = document.createElement("button");
            applyButton.type = "button";
            applyButton.className = "apply-live-button";
            applyButton.textContent = `Apply ${result.recommended === key ? "recommended route" : "this route"}`;
            applyButton.addEventListener("click", () => applyLivePlan(option, result, payload));
            card.append(title, detail, applyButton);
            root.appendChild(card);
        }
        applyLivePlan(result[result.recommended], result, payload);
        summary.textContent = `Recommended: ${result.recommended === "intercept" ? "intercept immediately" : "insert later in the active route"}. The updated route intelligence now includes the emergency stop. ${result.message}`;
    } catch (error) {
        document.getElementById("liveResults").textContent = error.message;
    } finally {
        button.disabled = false;
        button.textContent = "Compare live options";
    }
});
