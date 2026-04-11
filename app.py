from flask import Flask, request, jsonify
import requests
import urllib3
urllib3.disable_warnings()

app = Flask(__name__)

HGI_BASE = "https://900405097.hginet.com.co/Api"
TOKEN_FILE = "/tmp/milo_token.txt"

def guardar_token(token):
    with open(TOKEN_FILE, "w") as f:
        f.write(token)

def leer_token():
    try:
        with open(TOKEN_FILE, "r") as f:
            t = f.read().strip()
            return t if t else None
    except:
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
    """Milo llama este endpoint para obtener/renovar el token"""
    usuario = request.args.get("usuario", "98711025")
    clave = request.args.get("clave", "C9871")
    compania = request.args.get("cod_compania", "1")
    empresa = request.args.get("cod_empresa", "1")
    url = f"{HGI_BASE}/Autenticar?usuario={usuario}&clave={clave}&cod_compania={compania}&cod_empresa={empresa}"
    try:
        r = requests.get(url, timeout=15, verify=False)
        data = r.json()
        jwt = data.get("JwtToken")
        if jwt:
            guardar_token(jwt)
            print(f"[MILO] Token guardado via /login")
            return jsonify({"token": True, "preview": jwt[:25]+"..."})
        codigo = data.get("Error", {}).get("Codigo")
        if codigo == 3:
            # Token vigente - usar el que ya tenemos o el que viene en la respuesta
            token_actual = leer_token()
            if token_actual:
                return jsonify({"token": True, "preview": token_actual[:25]+"...", "msg": "usando token vigente"})
            return jsonify({"token": False, "msg": "Token vigente en HGI pero no tenemos copia local"}), 202
        return jsonify({"token": False, "error": str(data)}), 400
    except Exception as e:
        return jsonify({"token": False, "error": str(e)}), 500

@app.route("/api/<path:ruta>", methods=["GET","POST","OPTIONS"])
def proxy(ruta):
    if request.method == "OPTIONS":
        return jsonify({}), 200

    token = leer_token()
    if not token:
        return jsonify({"error": "Sin token - llama /login primero"}), 401

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    url = f"{HGI_BASE}/{ruta}"

    try:
        if request.method == "POST":
            body = request.get_json()
            print(f"[MILO] POST {ruta}")
            r = requests.post(url, json=body, headers=headers, params=request.args.to_dict(), timeout=30, verify=False)
        else:
            r = requests.get(url, headers=headers, params=request.args.to_dict(), timeout=30, verify=False)

        print(f"[HGI] {r.status_code} | {r.text[:100]}")

        if r.status_code in [400, 401, 403]:
            print("[MILO] Token rechazado")

        try:
            return jsonify(r.json()), r.status_code
        except Exception:
            return r.text, r.status_code

    except Exception as e:
        print(f"[MILO] Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
