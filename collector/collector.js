/* Collector dashboard behavior. All data comes from window.tringggApi (../js/api.js),
   maps come from window.tringggMap (../js/map.js, Leaflet + OpenStreetMap). */
"use strict";

const api = window.tringggApi;
const mapApi = window.tringggMap;
const SESSION_KEY = "tringgg_collector";
const BAG_NAMES = { GREEN: "Green", RED: "Red", BOTH: "Both" };
const REFRESH_MS = 3000;
const SIM_STEP_KM = 0.12;   // how far the simulated truck moves per second
const ARRIVED_KM = 0.03;    // within 30 m counts as "at the gate"

let me = null;            // { collector_id, name }
let myLocation = null;    // { lat, lng, at_depot? }
let refreshTimer = null;
let flashGate = null;     // gate to highlight after a lookup
let gpsWatch = null;
let simTimer = null;
let lastRoute = [];
const latestOpen = new Map(); // latest open requests by gate, for map popups
const mapState = { map: null, markers: new Map(), truck: null, line: null, fitted: false };

const el = (id) => document.getElementById(id);

initializeLogin();
initializeLookup();
initializeLists();
initializeLocation();
restoreSession();

/* ---------- Login / session ---------- */
async function restoreSession() {
  try { showDashboard(await api.collectorSession()); } catch { showLogin(); }
}

function initializeLogin() {
  el("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const collector = await api.collectorLogin(el("collectorId").value, el("collectorPin").value);
      try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(collector)); } catch (error) { /* blocked */ }
      el("collectorPin").value = "";
      showDashboard(collector);
    } catch (error) {
      el("loginError").textContent = error.message;
    }
  });
  el("logoutBtn").addEventListener("click", async () => {
    try { await api.collectorLogout(); } catch (error) { showMessage(error.message,"error"); return; }
    try { sessionStorage.removeItem(SESSION_KEY); } catch (error) { /* blocked */ }
    stopGps();
    stopSim();
    showLogin();
  });
}

function showLogin() {
  me = null;
  window.clearInterval(refreshTimer);
  el("dashboard").hidden = true;
  el("userBox").hidden = true;
  el("loginSection").hidden = false;
  el("loginError").textContent = "";
}

function showDashboard(collector) {
  me = collector;
  el("loginSection").hidden = true;
  el("dashboard").hidden = false;
  el("userBox").hidden = false;
  el("userName").textContent = `${collector.name} · ${collector.collector_id}`;
  if (!mapState.map && mapApi) mapState.map = mapApi.createMap("collectorMap", { zoom: 14 });
  mapState.fitted = false;
  refresh();
  window.clearInterval(refreshTimer);
  refreshTimer = window.setInterval(() => { if (!document.hidden) refresh(); }, REFRESH_MS);
}

/* ---------- Rendering ---------- */
async function refresh() {
  if (!me) return;
  try {
  const open = await api.listOpenRequests();
  latestOpen.clear();
  open.forEach((r) => latestOpen.set(r.gate_id, r));
  const logs = await api.listLogs(me.collector_id);
  myLocation = await api.getCollectorLocation(me.collector_id);
  const fresh = open.filter((r) => r.status === "REQUESTED");
  const mine = open.filter((r) => r.status === "ASSIGNED" && r.collector_id === me.collector_id);
  lastRoute = planRoute(myLocation, mine);

  el("statNew").textContent = fresh.length;
  el("statMine").textContent = mine.length;
  el("statDone").textContent = logs.length;
  el("locText").textContent = myLocation.at_depot
    ? "Your location: depot (tap Use my GPS on your phone)"
    : `${myLocation.source === "simulation" ? "Demo simulated position" : "Last GPS position"}: updated ${timeAgo(myLocation.updated_at)}`;

  renderGroups(el("newList"), fresh, "new");
  renderGroups(el("mineList"), lastRoute, "mine");
  renderLog(logs);
  renderRoute(lastRoute);
  renderMap(open, lastRoute);
  } catch (error) {
    if (error.status === 401) { stopGps(); stopSim(); showLogin(); }
    showMessage(error.message,"error");
  }
}

// Visit order: always go to the nearest remaining gate next (simple, explainable).
function planRoute(start, requests) {
  const left = requests.filter((r) => r.household);
  const route = [];
  let from = start;
  while (left.length) {
    let best = 0;
    left.forEach((r, i) => {
      if (api.distanceKm(from, r.household) < api.distanceKm(from, left[best].household)) best = i;
    });
    const next = left.splice(best, 1)[0];
    route.push(next);
    from = next.household;
  }
  return route;
}

// Group requests by ward so the collector clears one area at a time.
function renderGroups(container, requests, kind) {
  container.replaceChildren();
  if (!requests.length) {
    const empty = document.createElement("p");
    empty.className = "col-empty";
    empty.textContent = kind === "new" ? "No new requests right now." : "Nothing accepted yet. Accept requests above.";
    container.append(empty);
    return;
  }
  const byWard = new Map();
  requests.forEach((r) => {
    const ward = r.household ? r.household.ward : "Unknown ward";
    if (!byWard.has(ward)) byWard.set(ward, []);
    byWard.get(ward).push(r);
  });

  byWard.forEach((items, ward) => {
    const group = document.createElement("article");
    group.className = "col-group";

    const head = document.createElement("div");
    head.className = "col-group-head";
    const title = document.createElement("h3");
    title.textContent = `${ward} · ${items.length} ${items.length === 1 ? "house" : "houses"}`;
    head.append(title);
    if (items.length > 1 && kind === "new") {
      head.append(kind === "new"
        ? makeButton("Accept all", "accept", () => runAll(items, (r) => api.acceptRequest(r.gate_id, me.collector_id), "accepted"))
        : makeButton("✅ All clean", "clean", () => runAll(items, (r) => api.completeRequest(r.gate_id, me.collector_id, true), "collected as clean")));
    }
    group.append(head);

    items.forEach((r) => group.append(makeItem(r, kind)));
    container.append(group);
  });
}

function makeItem(request, kind) {
  const row = document.createElement("div");
  row.className = "col-item" + (request.gate_id === flashGate ? " flash" : "");
  row.dataset.gate = request.gate_id;

  const info = document.createElement("div");
  const gate = document.createElement("span");
  gate.className = "col-gate";
  gate.textContent = request.gate_id;
  const chip = document.createElement("span");
  chip.className = `bag-chip ${request.bag_color}`;
  chip.textContent = BAG_NAMES[request.bag_color] || request.bag_color;
  const owner = document.createElement("div");
  owner.className = "col-owner";
  owner.textContent = request.household ? request.household.owner_name : "";
  const time = document.createElement("div");
  time.className = "col-time";
  time.textContent = kind === "new"
    ? `Requested ${timeAgo(request.created_at)}`
    : `Accepted ${timeAgo(request.accepted_at)}`;
  info.append(gate, chip, owner, time);
  if (request.household && myLocation) {
    const dist = document.createElement("div");
    dist.className = "col-dist";
    const km = api.distanceKm(myLocation, request.household);
    dist.textContent = `${formatKm(km)} away · ~${api.etaMinutes(km)} min`;
    info.append(dist);
  }

  const actions = document.createElement("div");
  actions.className = "col-actions";
  const showOnMap = makeButton("🗺 Map", "ghost", () => focusGate(request.gate_id), true);
  if (kind === "new") {
    actions.append(showOnMap, makeButton("Accept", "accept", () => runOne(() => api.acceptRequest(request.gate_id, me.collector_id), `${request.gate_id} accepted. It is now on your route.`)));
  } else {
    actions.append(
      makeGoLink(request),
      makeButton("✅ Clean", "clean", () => runOne(() => api.completeRequest(request.gate_id, me.collector_id, true), `${request.gate_id} collected. Household got +${request.bag_color === "BOTH" ? 20 : 10} points.`)),
      makeButton("⚠️ Mixed", "mixed", () => runOne(() => api.completeRequest(request.gate_id, me.collector_id, false), `${request.gate_id} collected as MIXED. Their streak was reset.`))
    );
  }
  row.append(info, actions);
  return row;
}

function makeGoLink(request) {
  const link = document.createElement("a");
  link.className = "col-go";
  link.textContent = "Directions ↗";
  link.target = "_blank";
  link.rel = "noopener";
  if (request.household && mapApi) link.href = mapApi.directionsUrl(request.household.lat, request.household.lng);
  return link;
}

function renderRoute(route) {
  const list = el("routeList");
  list.replaceChildren();
  if (!route.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No stops yet. Accept requests to see a suggested nearest-gate visiting order.";
    list.append(li);
    return;
  }
  let from = myLocation;
  route.forEach((r, i) => {
    const km = api.distanceKm(from, r.household);
    from = r.household;
    const li = document.createElement("li");
    const num = document.createElement("span");
    num.className = "stop-num";
    num.textContent = i + 1;
    const text = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = `${r.gate_id} · ${r.household.owner_name}`;
    const meta = document.createElement("div");
    meta.className = "stop-meta";
    meta.textContent = `${i === 0 ? "From you" : "From stop " + i}: ${formatKm(km)} · ~${api.etaMinutes(km)} min · ${BAG_NAMES[r.bag_color]} bag`;
    text.append(name, meta);
    li.append(num, text, makeGoLink(r));
    list.append(li);
  });
}

/* ---------- Map ---------- */
function renderMap(open, route) {
  const map = mapState.map;
  if (!map) return;
  const L = window.L;
  const order = new Map(route.map((r, i) => [r.gate_id, i + 1]));
  const seen = new Set();

  open.forEach((r) => {
    if (!r.household) return;
    seen.add(r.gate_id);
    const kind = r.status === "REQUESTED" ? "new" : r.collector_id === me.collector_id ? "mine" : "other";
    const label = kind === "mine" ? String(order.get(r.gate_id) || "") : kind === "new" ? "!" : "";
    const signature = `${kind}:${label}:${r.status}`;
    let entry = mapState.markers.get(r.gate_id);
    if (!entry) {
      const marker = L.marker([r.household.lat, r.household.lng]).addTo(map);
      entry = { marker, signature: "" };
      mapState.markers.set(r.gate_id, entry);
    }
    if (entry.signature !== signature) {
      entry.marker.setIcon(mapApi.pinIcon(kind, label));
      entry.marker.bindPopup(() => popupFor(r.gate_id));
      entry.signature = signature;
    }
  });
  // Remove pins for finished requests.
  mapState.markers.forEach((entry, gateId) => {
    if (!seen.has(gateId)) { entry.marker.remove(); mapState.markers.delete(gateId); }
  });

  // Truck + dashed route line through my stops in visiting order.
  if (!mapState.truck) {
    mapState.truck = L.marker([myLocation.lat, myLocation.lng], { icon: mapApi.truckIcon(), zIndexOffset: 1000 }).addTo(map);
    mapState.truck.bindPopup("<strong>You</strong>");
  }
  mapState.truck.setLatLng([myLocation.lat, myLocation.lng]);
  const path = [[myLocation.lat, myLocation.lng], ...route.map((r) => [r.household.lat, r.household.lng])];
  if (!mapState.line) mapState.line = L.polyline(path, { color: "#15803d", weight: 4, dashArray: "8 8" }).addTo(map);
  else mapState.line.setLatLngs(path);

  if (!mapState.fitted) {
    mapApi.fitTo(map, [myLocation, ...open.filter((r) => r.household).map((r) => r.household)], 15);
    mapState.fitted = true;
  }
}

// Popup is built fresh each time it opens, so it always shows the latest status.
function popupFor(gateId) {
  const box = document.createElement("div");
  box.className = "map-popup";
  const entry = latestOpen.get(gateId);
  if (!entry) {
    box.textContent = `${gateId}: no open request.`;
    return box;
  }
  const r = entry;
  const title = document.createElement("strong");
  title.textContent = `${r.gate_id} · ${BAG_NAMES[r.bag_color]} bag`;
  const who = document.createElement("div");
  who.textContent = r.household.owner_name;
  const meta = document.createElement("div");
  meta.className = "muted";
  const km = api.distanceKm(myLocation, r.household);
  meta.textContent = `${formatKm(km)} away · ~${api.etaMinutes(km)} min`;
  const row = document.createElement("div");
  row.className = "row";
  if (r.status === "REQUESTED") {
    row.append(popupButton("Accept", "accept", () => runOne(() => api.acceptRequest(r.gate_id, me.collector_id), `${r.gate_id} accepted.`)));
  } else if (r.collector_id === me.collector_id) {
    const go = makeGoLink(r);
    go.className = "go";
    row.append(
      go,
      popupButton("✅ Clean", "clean", () => runOne(() => api.completeRequest(r.gate_id, me.collector_id, true), `${r.gate_id} collected. +${r.bag_color === "BOTH" ? 20 : 10} points.`)),
      popupButton("⚠️ Mixed", "mixed", () => runOne(() => api.completeRequest(r.gate_id, me.collector_id, false), `${r.gate_id} collected as MIXED.`))
    );
  } else {
    meta.textContent += ` · taken by ${r.collector_name}`;
  }
  box.append(title, who, meta, row);
  return box;
}

function popupButton(label, kind, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = kind;
  button.textContent = label;
  button.addEventListener("click", async () => {
    button.disabled = true;
    if (mapState.map) mapState.map.closePopup();
    await onClick();
  });
  return button;
}

function focusGate(gateId) {
  const entry = mapState.markers.get(gateId);
  if (!entry || !mapState.map) return;
  el("collectorMap").scrollIntoView({ block: "center", behavior: "smooth" });
  mapState.map.setView(entry.marker.getLatLng(), 17);
  entry.marker.openPopup();
}

/* ---------- Location: real GPS or demo simulator ---------- */
function initializeLocation() {
  el("gpsBtn").addEventListener("click", () => (gpsWatch === null ? startGps() : stopGps()));
  el("simBtn").addEventListener("click", () => (simTimer === null ? startSim() : stopSim()));
}

function startGps() {
  if (!("geolocation" in navigator)) {
    showMessage("This device has no GPS access. Use Simulate drive for the demo.", "error");
    return;
  }
  stopSim();
  showMessage("Asking for location permission…", "ok");
  gpsWatch = navigator.geolocation.watchPosition(async (pos) => {
    if (!me || gpsWatch === null) return;
    await api.updateCollectorLocation(me.collector_id, pos.coords.latitude, pos.coords.longitude);
    el("gpsBtn").classList.add("active");
    el("gpsBtn").textContent = "📍 GPS on";
    refresh();
  }, (error) => {
    stopGps();
    showMessage(`GPS not available (${error.message}). It needs https and permission. Use Simulate drive for the demo.`, "error");
  }, { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 });
}

function stopGps() {
  if (gpsWatch !== null && "geolocation" in navigator) navigator.geolocation.clearWatch(gpsWatch);
  gpsWatch = null;
  el("gpsBtn").classList.remove("active");
  el("gpsBtn").textContent = "📍 Use my GPS";
}

// Demo only: moves the truck toward the next stop on the route, one step per second.
function startSim() {
  if (!lastRoute.length) {
    showMessage("Accept a request first, then simulate the drive.", "error");
    return;
  }
  stopGps();
  el("simBtn").classList.add("active");
  el("simBtn").textContent = "⏸ Stop drive";
  simTimer = window.setInterval(async () => {
    const next = lastRoute[0];
    if (!next || !myLocation) { stopSim(); return; }
    const target = next.household;
    const km = api.distanceKm(myLocation, target);
    if (km <= ARRIVED_KM) {
      stopSim();
      showMessage(`Arrived at ${next.gate_id}. Check the bags and confirm Clean or Mixed.`, "ok");
      focusGate(next.gate_id);
      return;
    }
    const t = Math.min(1, SIM_STEP_KM / km);
    const lat = myLocation.lat + (target.lat - myLocation.lat) * t;
    const lng = myLocation.lng + (target.lng - myLocation.lng) * t;
    await api.updateCollectorLocation(me.collector_id, lat, lng, "simulation");
    refresh();
  }, 1000);
}

function stopSim() {
  window.clearInterval(simTimer);
  simTimer = null;
  el("simBtn").classList.remove("active");
  el("simBtn").textContent = "▶ Simulate drive";
}

/* ---------- Log ---------- */
function renderLog(logs) {
  const list = el("logList");
  list.replaceChildren();
  if (!logs.length) {
    const li = document.createElement("li");
    li.textContent = "No pickups completed yet.";
    li.className = "col-muted";
    list.append(li);
    return;
  }
  logs.slice(0, 10).forEach((log) => {
    const li = document.createElement("li");
    const left = document.createElement("span");
    left.textContent = `${log.gate_id} · ${log.owner_name} · ${BAG_NAMES[log.bag_color]}`;
    const right = document.createElement("span");
    right.className = log.clean ? "ok" : "bad";
    right.textContent = `${log.clean ? "Clean +" + log.points_added : "Mixed"} · ${clock(log.collected_at)}`;
    li.append(left, right);
    list.append(li);
  });
}

/* ---------- Actions ---------- */
function makeButton(label, kind, onClick, keepEnabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `col-btn ${kind}`;
  button.textContent = label;
  button.addEventListener("click", async () => {
    if (!keepEnabled) button.disabled = true;
    await onClick();
  });
  return button;
}

async function runOne(action, successText) {
  try {
    await action();
    showMessage(successText, "ok");
  } catch (error) {
    showMessage(error.message, "error");
  }
  refresh();
}

async function runAll(items, action, verb) {
  let done = 0;
  const problems = [];
  for (const r of items) {
    try { await action(r); done += 1; } catch (error) { problems.push(error.message); }
  }
  showMessage(problems.length ? `${done} ${verb}. ${problems.join(" ")}` : `${done} houses ${verb}.`, problems.length ? "error" : "ok");
  refresh();
}

function initializeLookup() {
  el("lookupForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const gateId = el("lookupInput").value.trim().toUpperCase();
    if (!gateId) return;
    const open = await api.listOpenRequests();
    const request = open.find((r) => r.gate_id === gateId);
    if (!request) {
      showMessage(`${gateId} has no open pickup request.`, "error");
      return;
    }
    flashGate = gateId;
    if (request.status === "ASSIGNED" && request.collector_id !== me.collector_id) {
      showMessage(`${gateId} was accepted by ${request.collector_name}.`, "error");
    } else {
      showMessage(request.status === "REQUESTED"
        ? `${gateId} found under New requests. Tap Accept.`
        : `${gateId} found under My pickups. Check the bags and confirm.`, "ok");
    }
    await refresh();
    const row = document.querySelector(`.col-item[data-gate="${gateId}"]`);
    if (row) row.scrollIntoView({ block: "center", behavior: "smooth" });
    el("lookupInput").value = "";
    flashGate = null;
  });
}

function initializeLists() {
  el("resetDemo").addEventListener("click", async () => {
    stopGps();
    stopSim();
    await api.resetDemo();
    mapState.fitted = false;
    showMessage("Demo data reset.", "ok");
    refresh();
  });
  // Instant update when a citizen requests a pickup in another tab of the same browser.
  window.addEventListener("storage", (event) => {
    if (event.key === api.STORE_KEY) refresh();
  });
}

function showMessage(text, kind) {
  const box = el("message");
  box.textContent = text;
  box.className = "col-message " + kind;
}

/* ---------- Helpers ---------- */
function formatKm(km) {
  return mapApi ? mapApi.formatKm(km) : `${km.toFixed(1)} km`;
}

function timeAgo(iso) {
  if (!iso) return "";
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.round(minutes / 60)} h ago`;
}

function clock(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
