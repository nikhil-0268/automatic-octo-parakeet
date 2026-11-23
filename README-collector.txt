TRINGGG: COLLECTOR DASHBOARD (staff only)

HOW TO ADD: unzip into the repo ROOT. js/api.js is the same file as in the citizen zip;
replacing it is fine.
NEW: collector/index.html / collector.css / collector.js
Open: collector/index.html  (no link from the citizen pages, needs Collector ID + PIN)
Demo logins: COL-01 / 1234 (Hari Bahadur), COL-02 / 5678 (Sunita Tamang)

What a collector can do:
- See new requests grouped by ward, "Accept" one or "Accept all" in a ward
- Scan/type a Gate ID at the gate to find its request
- Confirm "Clean" (+10 points, +1 streak) or "Mixed" (streak reset to 0, bill back to NPR 400)
- "All clean" confirms a whole ward at once
- A request accepted by one collector cannot be taken or completed by another
- See their own collection log

WARNING: the login is a DEMO lock. The PINs are inside js/api.js, which anyone can read
in the browser. Real protection needs the backend to check logins (e.g. Supabase Auth).
Until the backend exists, citizen and collector only share data in the SAME browser.

MAP (Leaflet + OpenStreetMap)
Same shared files as the citizen zip: js/map.js, js/map.css, js/vendor/leaflet/, js/api.js.
- Pickup map: orange = new request, green numbered = my pickups in visiting order,
  grey = another collector's, truck = me. Tap a pin: Accept / Directions / Clean / Mixed.
- My route: nearest-gate-first order with distance and rough ETA per stop.
- "Directions" opens Google Maps turn-by-turn to that gate (app on phones).
- "Use my GPS": the phone shares live location (needs https + permission, e.g. GitHub Pages);
  citizens see it on their tracking map.
- "Simulate drive": DEMO ONLY, moves the truck toward the next stop for stage demos.
Distances are straight lines; the dashed line is not a road route. Turn-by-turn comes from Google Maps.
