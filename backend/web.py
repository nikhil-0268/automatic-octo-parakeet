"""Local website integration for the supplied Flask API."""
import math
import os
import re
import secrets
from pathlib import Path
from flask import request, session, send_from_directory, redirect, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import db
import seed
import services
from services import ApiError

ROOT = Path(__file__).resolve().parent.parent
DEPOT = {"lat":27.7010,"lng":85.3350,"at_depot":True,"updated_at":None}
GATES = [
 ("KTM-W10-0042",27.6893,85.3436), ("KTM-W10-0043",27.6921,85.3398),
 ("KTM-W6-0007",27.7215,85.3620), ("KTM-W26-0120",27.7154,85.3123),
 ("KTM-W32-0015",27.6787,85.3487), ("KTM-W10-0104",27.6921,85.3398),
 ("KTM-W10-0105",27.6948,85.3451), ("KTM-W01-0007",27.7142,85.3268),
 ("KTM-W01-0012",27.7165,85.3305)]

def seed_website(conn):
    seed.seed(conn)
    for gate,phone,name,ward in [
        ("KTM-W10-0104","9800000104","Ram Thapa",10),
        ("KTM-W10-0105","9800000105","Gita Karki",10),
        ("KTM-W01-0007","9800000007","Maya Gurung",1),
        ("KTM-W01-0012","9800000012","Bikash Shrestha",1)]:
        conn.execute("INSERT OR IGNORE INTO households(gate_id,phone,name,ward,address,created_at) VALUES(?,?,?,?,?,?)",(gate,phone,name,ward,f"Demo gate in Ward {ward}",services.iso(services.utcnow())))
    for gate,lat,lng in GATES:
        conn.execute("INSERT OR IGNORE INTO gate_locations VALUES(?,?,?)",(gate,lat,lng))
    for cid,pin in [(1,"1234"),(2,"5678")]:
        if conn.execute("SELECT id FROM collectors WHERE id=?",(cid,)).fetchone():
            conn.execute("INSERT OR IGNORE INTO collector_credentials VALUES(?,?)",(cid,generate_password_hash(pin)))

def attach(app):
    app.config['WEB_INTEGRATION']=True
    key = Path(app.config["DB_PATH"]).with_suffix(".session-key")
    if not key.exists(): key.write_text(secrets.token_hex(32),encoding="utf8")
    app.secret_key = key.read_text(encoding="utf8")
    app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Strict",SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE")=="1")
    con=db.connect(app.config["DB_PATH"])
    seed_website(con)
    con.close()

    def collector():
        cid=session.get("collector_id")
        if not cid: raise ApiError(401,"login_required","Please log in as a collector.")
        return cid

    @app.before_request
    def protect_operations():
        p=request.path
        if request.method == "OPTIONS": return None
        if request.method == "POST" and request.headers.get("Origin") and request.headers["Origin"] != request.host_url.rstrip("/"):
            raise ApiError(403,"cross_site","Use the website address shown by the server.")
        if p in ("/api/collections","/api/collectors") or (p=="/api/requests" and request.method=="GET") or re.fullmatch(r"/api/requests/\d+(?:/(assign|collect|cancel))?",p) or re.fullmatch(r"/api/collectors/\d+/queue",p):
            cid=collector()
            if request.method=="POST" and p.endswith(("/assign","/collect")):
                data=request.get_json(silent=True) or {}
                if data.get("collector_id") != cid: raise ApiError(403,"wrong_collector","Use your own collector account.")
            if p.endswith("/queue") and int(p.split('/')[-2])!=cid:
                raise ApiError(403,"wrong_collector","Only your own queue is available.")

    @app.post('/api/collector-login')
    def login():
        data=request.get_json(silent=True) or {}
        match=re.fullmatch(r"COL-(\d+)",str(data.get('collector_id','')).strip().upper())
        con=db.connect(app.config['DB_PATH'])
        try:
            row=con.execute('SELECT c.id,c.name,k.pin_hash FROM collectors c JOIN collector_credentials k ON k.collector_id=c.id WHERE c.id=?',(int(match[1]) if match else -1,)).fetchone()
            if not row or not check_password_hash(row['pin_hash'],str(data.get('pin',''))):
                raise ApiError(401,'invalid_login','Wrong Collector ID or PIN.')
            session.clear(); session['collector_id']=row['id']
            return {'collector_id':f"COL-{row['id']:02d}",'name':row['name']}
        finally: con.close()

    @app.post('/api/collector-logout')
    def logout():
        session.clear(); return {'ok':True}

    @app.get('/api/collector-session')
    def current():
        cid=collector(); con=db.connect(app.config['DB_PATH'])
        try:
            row=con.execute('SELECT name FROM collectors WHERE id=?',(cid,)).fetchone()
            return {'collector_id':f'COL-{cid:02d}','name':row['name']}
        finally: con.close()

    @app.route('/api/collectors/<int:cid>/location',methods=['GET','POST'])
    def location(cid):
        if collector()!=cid: raise ApiError(403,'wrong_collector','Only your own location is available.')
        con=db.connect(app.config['DB_PATH'])
        try:
            if request.method=='POST':
                data=request.get_json(silent=True) or {}
                lat,lng=data.get('lat'),data.get('lng')
                if not all(type(v) in (int,float) and math.isfinite(v) for v in (lat,lng)) or abs(lat)>90 or abs(lng)>180:
                    raise ApiError(400,'invalid_location','Invalid collector coordinates.')
                con.execute('INSERT OR REPLACE INTO collector_locations VALUES(?,?,?,?,?)',(cid,lat,lng,'simulation' if data.get('source')=='simulation' else 'gps',services.iso(services.utcnow())))
            row=con.execute('SELECT lat,lng,source,updated_at FROM collector_locations WHERE collector_id=?',(cid,)).fetchone()
            return dict(row) if row else DEPOT
        finally: con.close()

    # Serve only public assets; never expose backend source, databases or secrets.
    app.view_functions['index']=lambda:send_from_directory(ROOT,'index.html')
    @app.get('/<path:name>')
    def website(name):
        aliases={'resident':'resident/dashboard.html','collector':'collector/index.html','qr':'qr/print.html','login':'collector/index.html','command-center':'collector/index.html'}
        if name.rstrip('/') in aliases: return redirect('/'+aliases[name.rstrip('/')]+('?' + request.query_string.decode() if request.query_string else ''))
        if name in ['index.html','styles.css','app.js'] or (re.fullmatch(r'(?:assets|js|collector|resident|qr)/[\w/.-]+\.(?:html|js|css|png|jpg|svg)',name) and '..' not in name):
            return send_from_directory(ROOT,name)
        raise ApiError(404,'not_found','Not found.')

    @app.after_request
    def local_headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers.pop('Access-Control-Allow-Origin',None)
        return response
