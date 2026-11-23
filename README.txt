TRINGGG — WORKING FLASK + SQLITE WEBSITE

START (from this project folder)
  npm.cmd start
or:
  .venv\Scripts\python.exe backend\run.py
Open http://localhost:3000. Leave the terminal running.
Use this app server, not VS Code Live Server: all screens now call /api.

FIRST SETUP ON ANOTHER COMPUTER (Python 3.10+ and Node.js for npm commands)
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
  npm.cmd start
You can also run backend/run.py directly without Node.

PAGES
Homepage: http://localhost:3000
Citizen: http://localhost:3000/resident/dashboard.html
Collector: http://localhost:3000/collector/index.html
QR print sheet: http://localhost:3000/qr/print.html
Health: http://localhost:3000/api/health

YOUR LOGO
assets/tringgg-logo.png is the original supplied transparent image, used on the
homepage, resident and collector headers and as their browser icon.

TRY THE COMPLETE FLOW
1. Open the citizen dashboard with Gate ID KTM-W10-0042.
2. Select Green, Red or Both bags. The backend saves one active pickup per gate.
3. Open the collector dashboard in any browser using this same server.
4. Log in with COL-01 / 1234 (Hari Prasad), or COL-02 / 5678 (Maya Tamang).
5. Accept the request. View its map pin, suggested stop order and Directions link.
6. Mark Clean or Mixed and enter the Gate ID from the gate sticker when prompted.
7. The backend checks the gate, records collection and updates the citizen screen.
   Green/Red verified pickup: 10 points. Both verified: 20. Unverified: 0.
   Eight consecutive verified pickups in the current Nepal calendar month unlock
   the demo NPR 320 bill; Mixed resets the streak and returns the demo bill to 400.

SHARED DATA
Requests, collection events, Green Points and collector locations persist in
SQLite at data/backend.sqlite. Polling updates pages every 4–5 seconds, including
across different browsers. LocalStorage is no longer the request database.
Old browser demo history and earlier data/tringgg.sqlite remain untouched but are
not imported into verified collection records. The new database starts with zero
points and no invented pickup history. Startup seeds households/collectors safely
without resetting existing records. Reset-demo controls have been removed.

Original backend files and API documentation are in backend/. Use backend/run.py
for the combined website, server-side collector sessions and location endpoints.
backend/app.py alone is the supplied API-oriented entry point and does not attach
website sessions/routes; use run.py for this application.

LIMITS OF THIS LOCAL PROTOTYPE
Collector PINs are checked on the server with hashed credentials and cookie
sessions. Accepting another collector's assigned request is rejected. Resident
access still uses a Gate ID, not verified identity; demo PINs are publicly known.
The server binds to localhost. Do not expose this prototype publicly without real
resident authentication, production credentials/rate limits and a verified webhook.
The missed-call webhook is simulated, not connected to a phone provider.
Gate verification is typed input, not a camera QR scanner.

Gate/map coordinates are fictional seed locations. GPS and simulated positions
are stored separately by source. Dashed lines and ETA are straight-line estimates;
use the external Google Maps directions link for road navigation. OSM tiles need
internet. Collector GPS requires browser permission. The citizen screen shows
status/points and has no fleet map.

The supplied printed QR images still target the original GitHub Pages address.
GitHub Pages alone cannot run this Flask backend. Deploy the app to a Python host
and regenerate stickers for that address before scanning them as an end-to-end app.

TESTS
  npm.cmd test
  .venv\Scripts\python.exe -m unittest discover -s backend -v
The supplied backend tests are retained, with additional website, session,
location, shared-database, reward/streak, file access and frontend adapter tests.
