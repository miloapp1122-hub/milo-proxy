from flask import Flask, request, jsonify
import requests
import urllib3
urllib3.disable_warnings()

app = Flask(__name__)

HGI_BASE = "https://900405097.hginet.com.co/Api"
HGI_USUARIO = "98711025"
HGI_CLAVE = "C9871"
HGI_COMPANIA = "1"
HGI_EMPRESA = "1"
TOKEN_FILE = "/tmp/milo_token.txt"

def guardar_token(token):
    try:
        with open(TOKEN_FILE, "w") as f:
            f.write(token)
    except:
        pass

def leer_token():
    try:
        with open(TOKEN_FILE, "r") as f:
            t = f.read().strip()
            return t if t else None
    except:
        return None

def autenticar_hgi():
    """Intenta obtener token. Si dice vigente, espera y reintenta hasta conseguirlo."""
    url = f"{HGI_BASE}/Autenticar?usuario={HGI_USUARIO}&clave={HGI_CLAVE}&cod_compania={HGI_COMPANIA}&cod_empresa={HGI_EMPRESA}"
    for _ in range(60):  # intentar hasta 60 veces (60 min)
        try:
            r = requests.get(url, timeout=15, verify=False)
            data = r.json()
            jwt = data.get("JwtToken")
            if jwt:
                guardar_token(jwt)
                print(f"[MILO] Token obtenido y guardado!")
                return jwt
            codigo = data.get("Error", {}).get("Codigo")
            if codigo == 3:
                print("[MILO] Token vigente en HGI - esperando 60s...")
                import time; time.sleep(60)
        except Exception as e:
            print(f"[MILO] Error: {e}")
            import time; time.sleep(10)
    return None

@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, ngrok-skip-browser-warning, User-Agent"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        from flask import Response
        res = Response()
        res.headers["Access-Control-Allow-Origin"] = "*"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, ngrok-skip-browser-warning, User-Agent"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        res.headers["ngrok-skip-browser-warning"] = "true"
        return res, 200

@app.route("/", methods=["GET"])
def health():
    token = leer_token()
    return jsonify({
        "status": "OK",
        "token": bool(token),
        "preview": token[:25]+"..." if token else "SIN TOKEN"
    })

@app.route("/login", methods=["GET","POST"])
def login():
    url = f"{HGI_BASE}/Autenticar?usuario={HGI_USUARIO}&clave={HGI_CLAVE}&cod_compania={HGI_COMPANIA}&cod_empresa={HGI_EMPRESA}"
    try:
        r = requests.get(url, timeout=15, verify=False)
        data = r.json()
        jwt = data.get("JwtToken")
        if jwt:
            guardar_token(jwt)
            print("[MILO] Token guardado via /login")
            return jsonify({"token": True})
        codigo = data.get("Error", {}).get("Codigo")
        if codigo == 3:
            # Token vigente — arrancar hilo para obtenerlo cuando expire
            import threading
            t = threading.Thread(target=autenticar_hgi, daemon=True)
            t.start()
            # Igual dejar entrar — el token se obtendrá pronto
            return jsonify({"token": True, "msg": "token vigente - renovando en background"})
        return jsonify({"token": False, "error": str(data)}), 400
    except Exception as e:
        return jsonify({"token": False, "error": str(e)}), 500

@app.route("/api/<path:ruta>", methods=["GET","POST","OPTIONS"])
def proxy(ruta):
    if request.method == "OPTIONS":
        return jsonify({}), 200

    token = leer_token()
    if not token:
        # Intentar obtener token en el momento
        token = autenticar_hgi()
    if not token:
        return jsonify({"error": "Sin token"}), 401

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    url = f"{HGI_BASE}/{ruta}"

    try:
        if request.method == "POST":
            body = request.get_json()
            r = requests.post(url, json=body, headers=headers, params=request.args.to_dict(), timeout=30, verify=False)
        else:
            r = requests.get(url, headers=headers, params=request.args.to_dict(), timeout=30, verify=False)

        print(f"[HGI] {r.status_code} | {r.text[:100]}")

        if r.status_code in [400, 401, 403]:
            print("[MILO] Token rechazado - renovando...")
            import threading
            threading.Thread(target=autenticar_hgi, daemon=True).start()

        try:
            return jsonify(r.json()), r.status_code
        except Exception:
            return r.text, r.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
