"""tringgg business logic. No Flask in here, so it is easy to test.

Rules in one place:
  * A household can have only ONE active ticket (status requested/assigned).
  * A missed call from a registered number creates a ticket (waste type = both).
  * Collector scans the gate QR -> must match the ticket's household.
  * Green Points are only given when segregation is verified.
"""
import os
import re
import sqlite3  # noqa: F401  (kept for callers catching sqlite3 errors)
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

WASTE_TYPES = ("green", "red", "both")
ACTIVE_STATUSES = ("requested", "assigned")
TICKET_STATUSES = ("requested", "assigned", "completed", "cancelled", "expired")

# Kathmandu Metropolitan City has 32 wards.
KMC_WARDS = range(1, 33)
NPT = timezone(timedelta(hours=5, minutes=45))  # Nepal Standard Time, UTC+05:45

# Nepali mobile numbers start with 96, 97 or 98 (Ncell, NTC, Smart Cell, UTL).
NEPAL_MOBILE_PREFIXES = ("96", "97", "98")

# Green Points for a VERIFIED pickup. Change these numbers to change the rewards.
POINTS_PER_VERIFIED = {"green": 10, "red": 10, "both": 20}


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


# ---------- small helpers ----------

def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def to_npt(iso_str):
    """'2026-11-23T12:19:00Z' -> '2026-11-23 18:04 NPT' (Kathmandu time)."""
    if not iso_str:
        return None
    dt = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.astimezone(NPT).strftime("%Y-%m-%d %H:%M NPT")


def add_npt(row, keys):
    """Adds a Kathmandu-time copy of each timestamp, e.g. created_at -> created_at_npt."""
    for key in keys:
        if key in row:
            row[key + "_npt"] = to_npt(row[key])
    return row


def ticket_ttl_hours():
    """An untouched ticket expires after this long so a household is never locked out forever."""
    try:
        return float(os.environ.get("TRINGGG_TICKET_TTL_HOURS", "24"))
    except ValueError:
        return 24.0


def normalize_phone(raw):
    """'+977 984-1234567', '009779841234567', '9841234567' -> '9841234567'."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("977") and len(digits) > 10:
        digits = digits[3:]
    if len(digits) != 10 or not digits.startswith(NEPAL_MOBILE_PREFIXES):
        raise ApiError(400, "invalid_phone", "Phone number must be a 10-digit Nepali mobile number (starts with 96, 97 or 98).")
    return digits


def normalize_ward(raw):
    try:
        ward = int(raw)
    except (TypeError, ValueError):
        raise ApiError(400, "invalid_ward", "Ward must be a number from 1 to 32 (Kathmandu has 32 wards).")
    if ward not in KMC_WARDS:
        raise ApiError(400, "invalid_ward", "Ward must be a number from 1 to 32 (Kathmandu has 32 wards).")
    return ward


def normalize_gate_id(raw):
    gate = str(raw or "").strip().upper()
    if not gate:
        raise ApiError(400, "missing_field", "gate_id is required.")
    return gate


def points_for(waste_type, segregation_verified):
    return POINTS_PER_VERIFIED[waste_type] if segregation_verified else 0


def expire_old_requests(conn):
    """Retire stale tickets on API access, including ordinary dashboard polling."""
    now = utcnow()
    cutoff = iso(now - timedelta(hours=ticket_ttl_hours()))
    conn.execute(
        """UPDATE pickup_requests SET status='expired',closed_at=?,updated_at=?
           WHERE status IN ('requested','assigned') AND created_at < ?""",
        (iso(now), iso(now), cutoff),
    )


@contextmanager
def tx(conn):
    """Write transaction. BEGIN IMMEDIATE takes the write lock up front, which is what
    makes 'check for an active ticket, then insert' safe against simultaneous calls."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


# ---------- lookups ----------

TICKET_SQL = """
SELECT r.id, r.household_id, h.gate_id, h.name AS household_name, h.ward,
       r.waste_type, r.source, r.status, r.collector_id, c.name AS collector_name,
       r.created_at, r.assigned_at, r.closed_at,
       (SELECT lat FROM gate_locations WHERE gate_id=h.gate_id) AS lat,
       (SELECT lng FROM gate_locations WHERE gate_id=h.gate_id) AS lng
FROM pickup_requests r
JOIN households h ON h.id = r.household_id
LEFT JOIN collectors c ON c.id = r.collector_id
"""


TICKET_TIME_KEYS = ("created_at", "assigned_at", "closed_at")


def get_ticket(conn, ticket_id):
    row = conn.execute(TICKET_SQL + " WHERE r.id = ?", (ticket_id,)).fetchone()
    if row is None:
        raise ApiError(404, "ticket_not_found", f"No pickup request with id {ticket_id}.")
    return add_npt(dict(row), TICKET_TIME_KEYS)


def get_household_by_gate(conn, gate_id):
    gate = normalize_gate_id(gate_id)
    row = conn.execute("SELECT * FROM households WHERE gate_id = ?", (gate,)).fetchone()
    if row is None:
        raise ApiError(404, "household_not_found", f"No household with gate id {gate}.")
    return row


def register_household(conn, name, phone, ward, address=None):
    """Registers a household and gives it the next gate ID for its ward, e.g. KTM-W10-0044."""
    name = str(name or "").strip()
    if not name:
        raise ApiError(400, "missing_field", "'name' is required.")
    phone = normalize_phone(phone)
    ward = normalize_ward(ward)
    with tx(conn):
        if conn.execute("SELECT 1 FROM households WHERE phone = ?", (phone,)).fetchone():
            raise ApiError(409, "phone_already_registered", "This phone number is already registered.")
        existing = conn.execute("SELECT gate_id FROM households WHERE ward = ?", (ward,)).fetchall()
        suffixes = [int(row["gate_id"].rsplit("-", 1)[-1]) for row in existing
                    if row["gate_id"].rsplit("-", 1)[-1].isdigit()]
        seq = max(suffixes, default=0) + 1
        while conn.execute("SELECT 1 FROM households WHERE gate_id = ?", (f"KTM-W{ward}-{seq:04d}",)).fetchone():
            seq += 1
        gate = f"KTM-W{ward}-{seq:04d}"
        conn.execute(
            "INSERT INTO households (gate_id, phone, name, ward, address, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (gate, phone, name, ward, (address or "").strip() or None, iso(utcnow())),
        )
    return {"gate_id": gate, "name": name, "phone": phone, "ward": ward, "address": address}


def points_balance(conn, household_id):
    row = conn.execute(
        "SELECT COALESCE(SUM(points), 0) AS total FROM green_points_ledger WHERE household_id = ?",
        (household_id,),
    ).fetchone()
    return row["total"]


# ---------- pickup requests ----------

def create_request(conn, household_id, waste_type, source):
    """Create a ticket unless the household already has an active one.
    Returns (ticket_dict, created_bool)."""
    if waste_type not in WASTE_TYPES:
        raise ApiError(400, "invalid_waste_type", f"waste_type must be one of {', '.join(WASTE_TYPES)}.")
    now = utcnow()
    cutoff = iso(now - timedelta(hours=ticket_ttl_hours()))
    with tx(conn):
        # 1. retire stale tickets so they cannot lock the household forever
        conn.execute(
            """UPDATE pickup_requests SET status = 'expired', closed_at = ?, updated_at = ?
               WHERE household_id = ? AND status IN ('requested', 'assigned') AND created_at < ?""",
            (iso(now), iso(now), household_id, cutoff),
        )
        # 2. the lock: an active ticket already exists -> return it instead of making another
        active = conn.execute(
            "SELECT id FROM pickup_requests WHERE household_id = ? AND status IN ('requested', 'assigned')",
            (household_id,),
        ).fetchone()
        if active:
            return get_ticket(conn, active["id"]), False
        # 3. otherwise create a new ticket
        cur = conn.execute(
            """INSERT INTO pickup_requests (household_id, waste_type, source, status, created_at, updated_at)
               VALUES (?, ?, ?, 'requested', ?, ?)""",
            (household_id, waste_type, source, iso(now), iso(now)),
        )
        return get_ticket(conn, cur.lastrowid), True


def request_pickup_for_gate(conn, gate_id, waste_type):
    """App / website path (the 'Request a pickup' form)."""
    household = get_household_by_gate(conn, gate_id)
    return create_request(conn, household["id"], waste_type, "app")


def handle_missed_call(conn, raw_phone, waste_type="both"):
    """Simulated telephony webhook. A missed call carries no input, so waste type defaults to both."""
    phone = normalize_phone(raw_phone)
    household = conn.execute("SELECT * FROM households WHERE phone = ?", (phone,)).fetchone()

    if household is None:
        _log_call(conn, phone, None, "unregistered", None)
        return {
            "outcome": "unregistered",
            "ticket": None,
            "message": "This number is not registered with tringgg. Please register your gate ID first.",
            "message_ne": "यो नम्बर tringgg मा दर्ता गरिएको छैन। कृपया पहिले आफ्नो गेट आईडी दर्ता गर्नुहोस्।",
        }

    ticket, created = create_request(conn, household["id"], waste_type, "missed_call")
    outcome = "created" if created else "duplicate"
    _log_call(conn, phone, household["id"], outcome, ticket["id"])
    msg = ticket_messages(ticket, created)
    return {"outcome": outcome, "ticket": ticket, **msg}


def ticket_messages(ticket, created):
    """English + Nepali text to show (or SMS) to the resident."""
    tid, gate = ticket["id"], ticket["gate_id"]
    if created:
        return {
            "message": f"Pickup request #{tid} received for gate {gate}. A collector will be assigned soon.",
            "message_ne": f"तपाईंको फोहोर उठाउने अनुरोध #{tid} दर्ता भयो (गेट {gate})। सङ्कलक छिट्टै खटिनेछ।",
        }
    return {
        "message": f"You already have an active pickup request (#{tid}). No need to call again.",
        "message_ne": f"तपाईंको अनुरोध #{tid} पहिले नै सक्रिय छ। फेरि फोन गर्नुपर्दैन।",
    }


def _log_call(conn, phone, household_id, outcome, ticket_id):
    conn.execute(
        "INSERT INTO missed_calls (caller_phone, household_id, outcome, ticket_id, received_at) VALUES (?, ?, ?, ?, ?)",
        (phone, household_id, outcome, ticket_id, iso(utcnow())),
    )


def list_requests(conn, status=None, ward=None, collector_id=None, limit=100):
    sql, params, where = TICKET_SQL, [], []
    if status:
        if status not in TICKET_STATUSES:
            raise ApiError(400, "invalid_status", f"status must be one of {', '.join(TICKET_STATUSES)}.")
        where.append("r.status = ?")
        params.append(status)
    if ward is not None:
        where.append("h.ward = ?")
        params.append(normalize_ward(ward))
    if collector_id is not None:
        where.append("r.collector_id = ?")
        params.append(collector_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.created_at, r.id LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    return [add_npt(dict(r), TICKET_TIME_KEYS) for r in conn.execute(sql, params).fetchall()]


def assign_request(conn, ticket_id, collector_id):
    now = iso(utcnow())
    with tx(conn):
        ticket = conn.execute("SELECT status, collector_id FROM pickup_requests WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            raise ApiError(404, "ticket_not_found", f"No pickup request with id {ticket_id}.")
        if ticket["status"] not in ACTIVE_STATUSES:
            raise ApiError(409, "ticket_not_active", f"Ticket is already {ticket['status']}.")
        if conn.execute("SELECT 1 FROM collectors WHERE id = ?", (collector_id,)).fetchone() is None:
            raise ApiError(404, "collector_not_found", f"No collector with id {collector_id}.")
        if ticket["collector_id"] is not None and ticket["collector_id"] != collector_id:
            raise ApiError(409, "assigned_to_other_collector", "This pickup was already accepted by another collector.")
        conn.execute(
            "UPDATE pickup_requests SET status = 'assigned', collector_id = ?, assigned_at = ?, updated_at = ? WHERE id = ?",
            (collector_id, now, now, ticket_id),
        )
    return get_ticket(conn, ticket_id)


def cancel_request(conn, ticket_id):
    now = iso(utcnow())
    with tx(conn):
        ticket = conn.execute("SELECT status FROM pickup_requests WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            raise ApiError(404, "ticket_not_found", f"No pickup request with id {ticket_id}.")
        if ticket["status"] not in ACTIVE_STATUSES:
            raise ApiError(409, "ticket_not_active", f"Ticket is already {ticket['status']}.")
        conn.execute(
            "UPDATE pickup_requests SET status = 'cancelled', closed_at = ?, updated_at = ? WHERE id = ?",
            (now, now, ticket_id),
        )
    return get_ticket(conn, ticket_id)


# ---------- collection + Green Points ----------

def complete_collection(conn, ticket_id, scanned_gate_id, collector_id, segregation_verified, notes=None):
    """Collector scanned the gate QR and checked segregation. Saves the collection event,
    closes the ticket and awards Green Points, all in ONE transaction."""
    if not isinstance(segregation_verified, bool):
        raise ApiError(400, "invalid_field", "segregation_verified must be true or false.")
    scanned = normalize_gate_id(scanned_gate_id)
    now = iso(utcnow())

    with tx(conn):
        ticket = conn.execute("SELECT * FROM pickup_requests WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            raise ApiError(404, "ticket_not_found", f"No pickup request with id {ticket_id}.")
        if ticket["status"] == "completed":
            raise ApiError(409, "already_collected", "This pickup was already completed.")
        if ticket["status"] not in ACTIVE_STATUSES:
            raise ApiError(409, "ticket_not_active", f"Ticket is {ticket['status']}.")

        household = conn.execute("SELECT * FROM households WHERE id = ?", (ticket["household_id"],)).fetchone()
        if scanned != household["gate_id"]:
            raise ApiError(422, "gate_mismatch", "Scanned QR does not match this ticket's household.")

        if conn.execute("SELECT 1 FROM collectors WHERE id = ?", (collector_id,)).fetchone() is None:
            raise ApiError(404, "collector_not_found", f"No collector with id {collector_id}.")
        if ticket["collector_id"] not in (None, collector_id):
            raise ApiError(409, "assigned_to_other_collector", "This ticket is assigned to a different collector.")

        points = points_for(ticket["waste_type"], segregation_verified)

        conn.execute(
            "UPDATE pickup_requests SET status = 'completed', collector_id = ?, closed_at = ?, updated_at = ? WHERE id = ?",
            (collector_id, now, now, ticket_id),
        )
        cur = conn.execute(
            """INSERT INTO collection_events
               (ticket_id, household_id, collector_id, scanned_gate_id, segregation_verified,
                points_awarded, notes, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticket_id, household["id"], collector_id, scanned, int(segregation_verified), points, notes, now),
        )
        event_id = cur.lastrowid
        if points:
            conn.execute(
                "INSERT INTO green_points_ledger (household_id, event_id, points, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                (household["id"], event_id, points, f"Verified {ticket['waste_type']} pickup (ticket #{ticket_id})", now),
            )
        balance = points_balance(conn, household["id"])

    if points:
        message = f"Pickup completed. You earned {points} Green Points!"
        message_ne = f"फोहोर सङ्कलन सम्पन्न भयो। तपाईंले {points} हरित अंक पाउनुभयो।"
    else:
        message = "Pickup completed. Segregation was not verified, so no Green Points this time."
        message_ne = "फोहोर सङ्कलन सम्पन्न भयो। फोहोर छुट्याएको प्रमाणित नभएकाले यस पटक अंक दिइएन।"
    return {
        "message": message,
        "message_ne": message_ne,
        "event_id": event_id,
        "ticket": get_ticket(conn, ticket_id),
        "segregation_verified": segregation_verified,
        "points_awarded": points,
        "green_points_balance": balance,
    }


def household_summary(conn, gate_id):
    household = get_household_by_gate(conn, gate_id)
    active = conn.execute(
        "SELECT id FROM pickup_requests WHERE household_id = ? AND status IN ('requested', 'assigned')",
        (household["id"],),
    ).fetchone()
    pickups = conn.execute(
        "SELECT COUNT(*) AS n FROM collection_events WHERE household_id = ?", (household["id"],)
    ).fetchone()["n"]
    latest = conn.execute("SELECT id FROM pickup_requests WHERE household_id=? ORDER BY id DESC LIMIT 1", (household["id"],)).fetchone()
    last_ticket = get_ticket(conn, latest["id"]) if latest else None
    if last_ticket and last_ticket["status"] == "completed":
        event = conn.execute("SELECT segregation_verified,points_awarded FROM collection_events WHERE ticket_id=?", (last_ticket["id"],)).fetchone()
        last_ticket["verified_clean"] = bool(event["segregation_verified"])
        last_ticket["points_awarded"] = event["points_awarded"]
    events = conn.execute("SELECT segregation_verified FROM collection_events WHERE household_id=? AND collected_at>=? ORDER BY id DESC", (household["id"],iso(utcnow().astimezone(NPT).replace(day=1,hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)))).fetchall()
    streak = 0
    for event in events:
        if not event["segregation_verified"]: break
        streak += 1
    location = conn.execute("SELECT lat,lng FROM gate_locations WHERE gate_id=?", (household["gate_id"],)).fetchone()
    return {
        "lat": location["lat"] if location else None,
        "lng": location["lng"] if location else None,
        "latest_ticket": last_ticket,
        "streak_count": streak,
        "monthly_bill_npr": 320 if streak >= 8 else 400,
        "gate_id": household["gate_id"],
        "name": household["name"],
        "ward": household["ward"],
        "address": household["address"],
        "green_points_balance": points_balance(conn, household["id"]),
        "pickups_completed": pickups,
        "active_ticket": get_ticket(conn, active["id"]) if active else None,
    }


def points_history(conn, gate_id):
    household = get_household_by_gate(conn, gate_id)
    rows = conn.execute(
        "SELECT id, event_id, points, reason, created_at FROM green_points_ledger WHERE household_id = ? ORDER BY id DESC",
        (household["id"],),
    ).fetchall()
    return {
        "gate_id": household["gate_id"],
        "green_points_balance": points_balance(conn, household["id"]),
        "history": [add_npt(dict(r), ("created_at",)) for r in rows],
    }


def list_collections(conn, limit=100):
    rows = conn.execute(
        """SELECT e.id, e.ticket_id, h.gate_id, h.name AS household_name, r.waste_type, e.collector_id, c.name AS collector_name,
                  e.segregation_verified, e.points_awarded, e.notes, e.collected_at
           FROM collection_events e
           JOIN households h ON h.id = e.household_id
           JOIN collectors c ON c.id = e.collector_id
           JOIN pickup_requests r ON r.id = e.ticket_id
           ORDER BY e.id DESC LIMIT ?""",
        (max(1, min(int(limit), 500)),),
    ).fetchall()
    out = [add_npt(dict(r), ("collected_at",)) for r in rows]
    for r in out:
        r["segregation_verified"] = bool(r["segregation_verified"])
    return out


def list_collectors(conn):
    return [dict(r) for r in conn.execute("SELECT id, name, phone, vehicle_no FROM collectors ORDER BY id").fetchall()]


def collector_queue(conn, collector_id):
    if conn.execute("SELECT 1 FROM collectors WHERE id = ?", (collector_id,)).fetchone() is None:
        raise ApiError(404, "collector_not_found", f"No collector with id {collector_id}.")
    return list_requests(conn, status="assigned", collector_id=collector_id)
