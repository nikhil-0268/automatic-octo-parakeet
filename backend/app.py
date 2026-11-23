"""tringgg backend API (Flask).

Run:   python app.py        (then open http://localhost:5000/api/health)
"""
from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

import db
import services
from services import ApiError


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or db.DEFAULT_DB
    app.json.sort_keys = False
    app.json.ensure_ascii = False  # show Nepali text as-is

    boot = db.connect(app.config["DB_PATH"])
    db.init_db(boot)
    boot.close()

    # ---------- per-request database connection ----------

    def conn():
        if "conn" not in g:
            g.conn = db.connect(app.config["DB_PATH"])
            services.expire_old_requests(g.conn)
        return g.conn

    @app.teardown_appcontext
    def _close(_exc):
        c = g.pop("conn", None)
        if c is not None:
            c.close()

    # ---------- request parsing helpers ----------

    def body():
        """JSON body, or form fields (many phone/SMS gateways post forms)."""
        data = request.get_json(silent=True)
        if isinstance(data, dict):
            return data
        return request.form.to_dict()

    def need(data, key):
        value = data.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ApiError(400, "missing_field", f"'{key}' is required.")
        return value

    def as_int(value, name):
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ApiError(400, "invalid_field", f"'{name}' must be a number.")

    def as_bool(value, name):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "1", "yes"):
            return True
        if isinstance(value, str) and value.strip().lower() in ("false", "0", "no"):
            return False
        raise ApiError(400, "invalid_field", f"'{name}' must be true or false.")

    # ---------- routes ----------

    @app.get("/")
    def index():
        return {"service": "tringgg backend", "health": "/api/health"}

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # Simulated telephony webhook: POST {"from": "9841234567"}
    @app.post("/api/webhooks/missed-call")
    def missed_call():
        data = body()
        caller = data.get("from") or data.get("From") or data.get("caller")
        if not caller:
            raise ApiError(400, "missing_field", "'from' (caller phone number) is required.")
        result = services.handle_missed_call(conn(), caller)
        return jsonify(result), (201 if result["outcome"] == "created" else 200)

    # App / website: POST {"gate_id": "KTM-W10-0042", "waste_type": "both"}
    @app.post("/api/requests")
    def create_request():
        data = body()
        gate_id = need(data, "gate_id")
        waste_type = str(data.get("waste_type") or "both").strip().lower()
        ticket, created = services.request_pickup_for_gate(conn(), gate_id, waste_type)
        return jsonify({"created": created, "duplicate": not created, "ticket": ticket,
                        **services.ticket_messages(ticket, created)}), (201 if created else 200)

    @app.get("/api/requests")
    def list_requests():
        ward = request.args.get("ward")
        collector = request.args.get("collector_id")
        rows = services.list_requests(
            conn(),
            status=request.args.get("status"),
            ward=as_int(ward, "ward") if ward else None,
            collector_id=as_int(collector, "collector_id") if collector else None,
            limit=as_int(request.args.get("limit", 100), "limit"),
        )
        return jsonify({"count": len(rows), "requests": rows})

    @app.get("/api/requests/<int:ticket_id>")
    def get_request(ticket_id):
        return jsonify(services.get_ticket(conn(), ticket_id))

    @app.post("/api/requests/<int:ticket_id>/assign")
    def assign(ticket_id):
        data = body()
        collector_id = as_int(need(data, "collector_id"), "collector_id")
        return jsonify(services.assign_request(conn(), ticket_id, collector_id))

    @app.post("/api/requests/<int:ticket_id>/cancel")
    def cancel(ticket_id):
        return jsonify(services.cancel_request(conn(), ticket_id))

    # Collector scans the gate QR, checks segregation, finishes the pickup
    @app.post("/api/requests/<int:ticket_id>/collect")
    def collect(ticket_id):
        data = body()
        result = services.complete_collection(
            conn(),
            ticket_id,
            need(data, "scanned_gate_id"),
            as_int(need(data, "collector_id"), "collector_id"),
            as_bool(need(data, "segregation_verified"), "segregation_verified"),
            data.get("notes"),
        )
        return jsonify(result), 201

    @app.get("/api/collections")
    def collections():
        rows = services.list_collections(conn(), limit=as_int(request.args.get("limit", 100), "limit"))
        return jsonify({"count": len(rows), "collections": rows})

    # Register a household: POST {"name": "...", "phone": "98...", "ward": 10, "address": "..."}
    @app.post("/api/households")
    def register_household():
        data = body()
        result = services.register_household(
            conn(), need(data, "name"), need(data, "phone"), need(data, "ward"), data.get("address")
        )
        return jsonify(result), 201

    @app.get("/api/households/<gate_id>")
    def household(gate_id):
        return jsonify(services.household_summary(conn(), gate_id))

    @app.get("/api/households/<gate_id>/points")
    def household_points(gate_id):
        return jsonify(services.points_history(conn(), gate_id))

    @app.get("/api/collectors")
    def collectors():
        return jsonify({"collectors": services.list_collectors(conn())})

    @app.get("/api/collectors/<int:collector_id>/queue")
    def collector_queue(collector_id):
        rows = services.collector_queue(conn(), collector_id)
        return jsonify({"count": len(rows), "requests": rows})

    # ---------- errors + CORS (so the website on another port can call us) ----------

    @app.errorhandler(Exception)
    def on_error(err):
        if isinstance(err, ApiError):
            return jsonify({"error": {"code": err.code, "message": err.message}}), err.status
        if isinstance(err, HTTPException):
            code = err.name.lower().replace(" ", "_")
            return jsonify({"error": {"code": code, "message": err.description}}), err.code
        app.logger.exception("Unexpected error")
        return jsonify({"error": {"code": "server_error", "message": "Something went wrong on the server."}}), 500

    @app.after_request
    def cors(resp):
        if app.config.get('WEB_INTEGRATION'):
            return resp
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=True)
