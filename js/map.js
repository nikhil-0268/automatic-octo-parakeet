/* tringgg shared map helpers (Leaflet + OpenStreetMap). Used by the citizen and collector dashboards.
   Leaflet itself is in js/vendor/leaflet/ so the page does not depend on a CDN.
   The street tiles still come from OpenStreetMap, so the background needs internet;
   pins, lines and distances keep working without it. */
"use strict";

(function () {
  const KATHMANDU = [27.7030, 85.3360];

  function leafletReady() {
    return typeof window.L !== "undefined";
  }

  // Makes a map inside the element with this id. Returns null if Leaflet failed to load.
  function createMap(elementId, options = {}) {
    const element = document.getElementById(elementId);
    if (!element) return null;
    if (!leafletReady()) {
      element.classList.add("map-unavailable");
      element.textContent = "Map could not load. Distances below still work.";
      return null;
    }
    const map = window.L.map(element, {
      center: options.center || KATHMANDU,
      zoom: options.zoom || 14,
      scrollWheelZoom: false, // page scrolling on phones should not zoom the map
      zoomControl: true
    });
    // OpenStreetMap's free tiles require this credit line to stay visible.
    window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    // Leaflet needs a size refresh when the map starts hidden or the layout changes.
    const resize = new ResizeObserver(() => map.invalidateSize());
    resize.observe(element);
    return map;
  }

  // Coloured pin made with CSS (no image files needed).
  function pinIcon(kind, label) {
    return window.L.divIcon({
      className: "",
      html: `<span class="map-pin map-pin-${kind}"><span>${label || ""}</span></span>`,
      iconSize: [34, 42],
      iconAnchor: [17, 40],
      popupAnchor: [0, -36]
    });
  }

  function truckIcon() {
    return window.L.divIcon({
      className: "",
      html: '<span class="map-truck" aria-label="Collector">🚛</span>',
      iconSize: [40, 40],
      iconAnchor: [20, 20],
      popupAnchor: [0, -18]
    });
  }

  // Zoom so every point is visible (points are {lat, lng}).
  function fitTo(map, points, maxZoom = 16) {
    const valid = points.filter((p) => p && Number.isFinite(p.lat) && Number.isFinite(p.lng));
    if (!map || !valid.length) return;
    if (valid.length === 1) {
      map.setView([valid[0].lat, valid[0].lng], maxZoom);
      return;
    }
    map.fitBounds(valid.map((p) => [p.lat, p.lng]), { padding: [40, 40], maxZoom });
  }

  // Opens turn-by-turn directions in Google Maps (app on phones, website on laptops).
  function directionsUrl(lat, lng) {
    return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}&travelmode=driving`;
  }

  function formatKm(km) {
    return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`;
  }

  window.tringggMap = { createMap, pinIcon, truckIcon, fitTo, directionsUrl, formatKm, leafletReady };
})();
