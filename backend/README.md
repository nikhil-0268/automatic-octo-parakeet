# tringgg backend

## Integrated website

This folder implements the supplied backend specification. From the project root,
run `npm start` (or `.venv\Scripts\python.exe backend\run.py`) and open
http://localhost:3000. This serves both dashboards and the API. The integrated
database is `data/backend.sqlite`; the standalone `app.py`/`seed.py` commands below
use `backend/tringgg.db` unless `TRINGGG_DB` is set. They are separate databases.
Do not use `seed.py --reset` expecting it to reset the integrated database.

The original 25 checks are retained, with additional integration/regression tests.
From the project root run `.venv\Scripts\python.exe -m unittest discover -s backend -v`.
Expired tickets are retired on API access, including resident dashboard polling;
there is no background expiry scheduler. Registration uses the next number after
the highest existing gate number in that ward.

The standalone API keeps its cross-port CORS support. The integrated website uses
same-origin requests and server-side collector sessions. It also adds persistent
collector locations and monthly streak summaries while retaining the supplied
pickup, ledger, QR validation and missed-call rules. Unknown valid phone numbers
are logged as unregistered; malformed phone numbers are rejected by validation.

Backend & Automation part of the tringgg project: database, pickup request APIs, a simulated
missed-call webhook, active ticket locking, collection events and verified Green Points.

Flask + SQLite. No database server to install: the data lives in one file, `tringgg.db`.

## Run it (Windows, VS Code terminal)

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python seed.py          # adds sample households and collectors
python app.py           # server on http://localhost:5000
```

Check it works: open http://localhost:5000/api/health in the browser.

Run the tests any time with `python -m unittest -v`.
To try the API, install the **REST Client** extension in VS Code and open `requests.http`.

## How it works

1. A resident gives a **missed call** (or taps the website/app form). That makes a **ticket**.
2. A household can only have **one active ticket** (requested or assigned). Calling again returns the same ticket. The database enforces this, so spam or double taps cannot create duplicates.
3. A ticket that nobody handles expires after 24 hours (`TRINGGG_TICKET_TTL_HOURS`), so a household is never locked out for good.
4. The collector is **assigned** the ticket, scans the gate QR, and sends the scan with a segregation check.
5. The QR must match the ticket's household. The ticket closes, a **collection event** is saved, and **Green Points** are added to the household's ledger.

### Green Points rules

| Waste type | Verified segregation | Not verified |
|------------|---------------------|--------------|
| green      | 10                  | 0            |
| red        | 10                  | 0            |
| both       | 20                  | 0            |

Change the numbers in `POINTS_PER_VERIFIED` at the top of `services.py`.

## Made for Kathmandu

- **Wards:** Kathmandu has 32 wards. Anything outside 1 to 32 is rejected.
- **Gate IDs:** `KTM-W<ward>-<number>`, e.g. `KTM-W10-0042` (New Baneshwor). `POST /api/households` registers a new household and hands out the next gate ID for its ward.
- **Phone numbers:** Nepali mobiles only (start with 96, 97 or 98). `+977`, `00977` and dashes or spaces are all accepted.
- **Nepali messages:** responses carry `message` (English) and `message_ne` (नेपाली), ready to show on screen or send as an SMS.
- **Nepal time:** every timestamp is stored in UTC and also comes back as `..._npt` in Nepal time (UTC+05:45), e.g. `created_at_npt: "2026-11-23 18:04 NPT"`.

## Endpoints

All under `/api`. Bodies are JSON. Errors look like `{"error": {"code": "...", "message": "..."}}`.

| Method | Path | What it does |
|--------|------|--------------|
| GET | `/health` | Server check |
| POST | `/webhooks/missed-call` | Body `{"from": "9841234567"}`. Creates a ticket (waste type `both`) |
| POST | `/requests` | Body `{"gate_id": "KTM-W10-0042", "waste_type": "green\|red\|both"}` |
| GET | `/requests` | Filters: `status`, `ward`, `collector_id` |
| GET | `/requests/<id>` | One ticket |
| POST | `/requests/<id>/assign` | Body `{"collector_id": 1}` |
| POST | `/requests/<id>/cancel` | Cancel an active ticket |
| POST | `/requests/<id>/collect` | Body `{"scanned_gate_id": "...", "collector_id": 1, "segregation_verified": true, "notes": "optional"}` |
| GET | `/collections` | All collection events |
| POST | `/households` | Register a household. Body `{"name": "...", "phone": "984...", "ward": 10, "address": "..."}` |
| GET | `/households/<gate_id>` | Green Points balance and active ticket |
| GET | `/households/<gate_id>/points` | Points history |
| GET | `/collectors` | List collectors |
| GET | `/collectors/<id>/queue` | Tickets assigned to a collector |

Ticket statuses: `requested`, `assigned`, `completed`, `cancelled`, `expired`.

Outcomes from the missed-call webhook: `created` (HTTP 201), `duplicate` (200), `unregistered` (200).

## For the frontend

- CORS is open, so the website can call the API from another port.
- The "Request a pickup" form in the demo maps to `POST /api/requests`. Its waste options already use the same values: `green`, `red`, `both`.
- Show the `message` field from responses to the resident.

## Files

| File | Purpose |
|------|---------|
| `app.py` | The API routes |
| `services.py` | All the rules (locking, QR check, points) |
| `schema.sql` | Database tables |
| `db.py` | Database connection |
| `seed.py` | Sample data |
| `test_api.py` | Automated tests |
| `requests.http` | Click-to-send example requests |

## Not built yet (ideas for later)

- Login for collectors and admins. Right now anyone who can reach the server can call any endpoint.
- Real telephony provider hookup. The webhook accepts `from`, `From` or `caller`, as JSON or form data, so wiring one up should be small.
- Live truck GPS and route grouping.
