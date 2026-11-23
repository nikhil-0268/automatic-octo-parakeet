/* Resident dashboard behavior. All data comes from window.tringggApi (../js/api.js). */
"use strict";

const api = window.tringggApi;
const GATE_KEY = "tringgg_gate_id";
const STEPS = ["REQUESTED", "ASSIGNED", "COLLECTED"];
const BAG_NAMES = { GREEN: "Green bag", RED: "Red bag", BOTH: "Both bags" };
const REFRESH_MS = 5000;

let currentGate = null;
let refreshTimer = null;

const el = (id) => document.getElementById(id);

initializeMenu();
initializeGateForm();
initializeActions();
start();

/* ---------- Startup: Gate ID from ?gate=, then saved, else ask ---------- */
function start() {
  const fromUrl = new URLSearchParams(window.location.search).get("gate");
  let saved = null;
  try { saved = localStorage.getItem(GATE_KEY); } catch (error) { /* storage blocked */ }
  const gate = fromUrl || saved;
  if (gate) openDashboard(gate);
  else showGateForm();
}

async function openDashboard(gateId) {
  try {
    const house = await api.getHousehold(gateId);
    currentGate = house.gate_id;
    try { localStorage.setItem(GATE_KEY, currentGate); } catch (error) { /* storage blocked */ }
    const url = new URL(window.location.href);
    url.searchParams.set("gate", currentGate);
    window.history.replaceState(null, "", url);
    el("gateSection").hidden = true;
    el("dashboard").hidden = false;
    el("switchGate").hidden = false;
    render(house);
    highlightScannedBag(house);
    startRefresh();
  } catch (error) {
    showGateForm(error.message);
  }
}

function showGateForm(message = "") {
  stopRefresh();
  currentGate = null;
  el("dashboard").hidden = true;
  el("switchGate").hidden = true;
  el("gateSection").hidden = false;
  el("gateError").textContent = message;
}

/* ---------- Bag QR: ?gate=...&bag=GREEN|RED|BOTH highlights that button ---------- */
function highlightScannedBag(house) {
  const bag = (new URLSearchParams(window.location.search).get("bag") || "").toUpperCase();
  const button = document.querySelector(`[data-bag="${BAG_NAMES[bag] ? bag : "none"}"]`);
  document.querySelectorAll("[data-bag]").forEach((b) => b.classList.remove("suggested"));
  if (!button) return;
  const open = house.active_request && house.active_request.status !== "COLLECTED";
  if (open) return; // the status card already explains what is happening
  button.classList.add("suggested");
  showMessage(`You scanned your ${BAG_NAMES[bag]}. Tap the glowing button to request a pickup.`, "ok");
  button.scrollIntoView({ block: "center", behavior: "smooth" });
}

/* ---------- Rendering ---------- */
function render(house) {
  el("ownerName").textContent = house.owner_name;
  el("wardLabel").textContent = house.ward || "";
  el("gateLabel").textContent = house.gate_id;
  el("pointsValue").textContent = house.green_points;

  renderStatus(house.active_request);
  renderStreak(house.streak_count, house.monthly_bill_npr);

  // Lock the bag buttons while a pickup is open (matches the backend's anti-spam lock).
  const open = house.active_request && house.active_request.status !== "COLLECTED";
  document.querySelectorAll("[data-bag]").forEach((button) => { button.disabled = Boolean(open); });
}

function renderStatus(request) {
  const items = [...el("statusSteps").querySelectorAll("li")];
  if (!request) {
    el("statusSummary").textContent = "No active pickup.";
    el("statusTime").textContent = "";
    items.forEach((item) => item.classList.remove("done", "current"));
    return;
  }
  const index = STEPS.indexOf(request.status);
  items.forEach((item, i) => {
    item.classList.toggle("done", i < index || request.status === "COLLECTED");
    item.classList.toggle("current", i === index && request.status !== "COLLECTED");
  });
  const bag = BAG_NAMES[request.bag_color] || request.bag_color;
  if (request.status === "COLLECTED") {
    el("statusSummary").textContent = request.verified_clean === false
      ? `${bag} collected, but the collector marked it as MIXED waste. Your streak went back to 0.`
      : `${bag} collected and verified clean (+${request.points_awarded ?? (request.bag_color === "BOTH" ? 20 : 10)} points). You can request again.`;
  } else if (request.status === "ASSIGNED") {
    el("statusSummary").textContent = `${bag} — ${request.collector_name || "a collector"} accepted your request and is on the way.`;
  } else {
    el("statusSummary").textContent = `${bag} — waiting for a collector to accept.`;
  }
  el("statusTime").textContent = "Requested at " +
    new Date(request.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function renderStreak(streak, bill) {
  const target = api.STREAK_FOR_DISCOUNT;
  const bar = el("streakBar");
  bar.replaceChildren(...Array.from({ length: target }, (_, i) => {
    const seg = document.createElement("span");
    seg.className = "streak-seg" + (i < streak ? " filled" : "");
    return seg;
  }));
  const shown = Math.min(streak, target);
  bar.setAttribute("aria-label", `${shown} of ${target} clean pickups`);
  el("streakText").textContent = streak >= target
    ? `${shown}/${target} clean pickups — discount unlocked!`
    : `${shown}/${target} clean pickups. ${target - shown} more to cut your bill to NPR ${api.DISCOUNT_BILL_NPR}.`;

  const discounted = bill < api.NORMAL_BILL_NPR;
  el("billOld").hidden = !discounted;
  el("billOld").textContent = `NPR ${api.NORMAL_BILL_NPR}`;
  el("billNow").textContent = `NPR ${bill}`;
}

/* ---------- Actions ---------- */
function initializeGateForm() {
  el("gateForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const gate = el("gateInput").value.trim();
    if (gate) openDashboard(gate);
  });
  el("switchGate").addEventListener("click", () => {
    try { localStorage.removeItem(GATE_KEY); } catch (error) { /* storage blocked */ }
    const url = new URL(window.location.href);
    url.searchParams.delete("gate");
    window.history.replaceState(null, "", url);
    showGateForm();
    el("gateInput").focus();
  });
}

function initializeActions() {
  document.querySelectorAll("[data-bag]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!currentGate) return;
      try {
        await api.requestPickup(currentGate, button.dataset.bag);
        document.querySelectorAll("[data-bag]").forEach((b) => b.classList.remove("suggested"));
        showMessage(`${BAG_NAMES[button.dataset.bag]} pickup requested. A collector will be assigned.`, "ok");
      } catch (error) {
        showMessage(error.message, "error");
      }
      refresh();
    });
  });
}

function showMessage(text, kind) {
  const box = el("requestMessage");
  box.textContent = text;
  box.className = "dash-message " + kind;
}

/* ---------- Live refresh (picks up changes made by the collector) ---------- */
async function refresh() {
  if (!currentGate) return;
  try {
    render(await api.getHousehold(currentGate));
  } catch (error) {
    showGateForm(error.message);
  }
}

// Instant update when the collector dashboard (another tab, same browser) changes data.
window.addEventListener("storage", (event) => {
  if (event.key === api.STORE_KEY) refresh();
});

function startRefresh() {
  stopRefresh();
  refreshTimer = window.setInterval(() => { if (!document.hidden) refresh(); }, REFRESH_MS);
}

function stopRefresh() {
  window.clearInterval(refreshTimer);
}

/* ---------- Mobile menu ---------- */
function initializeMenu() {
  const toggle = el("dashMenuToggle");
  const menu = el("dashMenu");
  const setOpen = (open) => {
    menu.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
  };
  toggle.addEventListener("click", () => setOpen(toggle.getAttribute("aria-expanded") !== "true"));
  menu.addEventListener("click", (event) => { if (event.target.closest("a, button")) setOpen(false); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") setOpen(false); });
  window.matchMedia("(min-width: 741px)").addEventListener("change", (event) => { if (event.matches) setOpen(false); });
}
