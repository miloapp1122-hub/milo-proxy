from flask import Flask, request, jsonify, Response
import requests
import urllib3
import threading
import time
urllib3.disable_warnings()

app = Flask(__name__)

HGI_BASE = "https://900405097.hginet.com.co/Api"
HGI_USUARIO = "98711025"
HGI_CLAVE = "C9871"
HGI_COMPANIA = "1"
HGI_EMPRESA = "1"
TOKEN_FILE = "/tmp/milo_token.txt"
_renovando = False

def guardar_token(t):
    try:
        open(TOKEN_FILE,"w").write(t)
    except: pass

def leer_token():
    try:
        t = open(TOKEN_FILE).read().strip()
        return t or None
    except: return None

def renovar_en_background():
    global _renovando
    if _renovando: return
    _renovando = True
    url = f"{HGI_BASE}/Autenticar?usuario={HGI_USUARIO}&clave={HGI_CLAVE}&cod_compania={HGI_COMPANIA}&cod_empresa={HGI_EMPRESA}"
    while True:
        try:
            r = requests.get(url, timeout=15, verify=False)
            data = r.json()
            jwt = data.get("JwtToken")
            if jwt:
                guardar_token(jwt)
                print("[MILO] Token renovado!")
                _renovando = False
                return
            if data.get("Error",{}).get("Codigo") == 3:
                print("[MILO] Token vigente - esperando 60s...")
                time.sleep(60)
                continue
        except Exception as e:
            print(f"[MILO] Error: {e}")
            time.sleep(10)
    _renovando = False

# Arrancar renovacion al iniciar
threading.Thread(target=renovar_en_background, daemon=True).start()

@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,ngrok-skip-browser-warning,User-Agent"
    r.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return r

@app.route("/", methods=["GET","OPTIONS"])
def health():
    if request.method == "OPTIONS": return jsonify({}), 200
    t = leer_token()
    return jsonify({"status":"OK","token":bool(t),"preview":t[:25]+"..." if t else "SIN TOKEN"})

@app.route("/login", methods=["GET","POST","OPTIONS"])
def login():
    if request.method == "OPTIONS": return jsonify({}), 200
    t = leer_token()
    if t:
        return jsonify({"token": True})
    # Arrancar renovacion si no está corriendo
    threading.Thread(target=renovar_en_background, daemon=True).start()
    return jsonify({"token": True, "msg": "obteniendo token, intenta en 60s"})

@app.route("/api/<path:ruta>", methods=["GET","POST","OPTIONS"])
def proxy(ruta):
    if request.method == "OPTIONS": return jsonify({}), 200
    token = leer_token()
    if not token:
        threading.Thread(target=renovar_en_background, daemon=True).start()
        return jsonify({"error":"Sin token - espera 60s y recarga"}), 401
    headers = {"Content-Type":"application/json","Authorization":f"Bearer {token}"}
    url = f"{HGI_BASE}/{ruta}"
    try:
        if request.method == "POST":
            r = requests.post(url, json=request.get_json(), headers=headers, params=request.args.to_dict(), timeout=30, verify=False)
        else:
            r = requests.get(url, headers=headers, params=request.args.to_dict(), timeout=30, verify=False)
        print(f"[HGI] {r.status_code} {ruta[:50]}")
        if r.status_code in [400,401,403]:
            threading.Thread(target=renovar_en_background, daemon=True).start()
        try: return jsonify(r.json()), r.status_code
        except: return r.text, r.status_code
    except Exception as e:
        return jsonify({"error":str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
