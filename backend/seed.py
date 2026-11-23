"""Add sample households and collectors.

    python seed.py            add the sample data (safe to run again)
    python seed.py --reset    delete the database first, then add the sample data
"""
import sys
from pathlib import Path

import db
import services

HOUSEHOLDS = [
    # gate_id,        phone,        name,            ward, address
    ("KTM-W10-0042", "9800000001", "Sita Sharma",    10, "New Baneshwor, Ward 10"),
    ("KTM-W10-0043", "9800000002", "Ram Thapa",      10, "New Baneshwor, Ward 10"),
    ("KTM-W6-0007",  "9800000003", "Pema Sherpa",     6, "Boudha, Ward 6"),
    ("KTM-W26-0120", "9800000004", "Anita Gurung",   26, "Thamel, Ward 26"),
    ("KTM-W32-0015", "9800000005", "Bikash Rai",     32, "Koteshwor, Ward 32"),
]

COLLECTORS = [
    # name,           phone,        vehicle
    ("Hari Prasad",   "9811111111", "Ba 1 Kha 2345"),
    ("Maya Tamang",   "9822222222", "Ba 2 Cha 6789"),
]


def seed(conn):
    now = services.iso(services.utcnow())
    for gate_id, phone, name, ward, address in HOUSEHOLDS:
        conn.execute(
            "INSERT OR IGNORE INTO households (gate_id, phone, name, ward, address, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (gate_id, phone, name, ward, address, now),
        )
    for name, phone, vehicle in COLLECTORS:
        conn.execute(
            "INSERT OR IGNORE INTO collectors (name, phone, vehicle_no, created_at) VALUES (?, ?, ?, ?)",
            (name, phone, vehicle, now),
        )


if __name__ == "__main__":
    if "--reset" in sys.argv:
        for suffix in ("", "-wal", "-shm"):
            Path(db.DEFAULT_DB + suffix).unlink(missing_ok=True)
        print("Old database deleted.")
    connection = db.connect()
    db.init_db(connection)
    seed(connection)
    connection.close()
    print(f"Seeded {len(HOUSEHOLDS)} households and {len(COLLECTORS)} collectors into {db.DEFAULT_DB}")
