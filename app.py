from flask import Flask, request, jsonify
import requests
import threading

app = Flask(__name__)

HGI_BASE = "https://900405097.hginet.com.co/Api"
HGI_USUARIO = "98711025"
HGI_CLAVE = "C9871"
HGI_COMPANIA = "1"
HGI_EMPRESA = "1"

_token = None
_token_lock = threading.Lock()

def obtener_token():
    global _token
    with _token_lock:
        url = f"{HGI_BASE}/Autenticar?usuario={HGI_USUARIO}&clave={HGI_CLAVE}&cod_compania={HGI_COMPANIA}&cod_empresa={HGI_EMPRESA}"
        try:
            r = requests.get(url, timeout=15)
            data = r.json()
            if data.get("JwtToken"):
                _token = data["JwtToken"]
                return _token
            if data.get("Error", {}).get("Codigo") == 3:
                return _token
        except Exception as e:
            print(f"Error autenticando: {e}")
        return _token

def get_token():
    global _token
    if not _token:
        return obtener_token()
    return _token

@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

@app.route("/", methods=["GET"])
def health():
    token = get_token()
    return jsonify({"status": "Milo Proxy activo", "hgi": HGI_BASE, "autenticado": bool(token)})

@app.route("/api/<path:ruta>", methods=["GET", "POST", "OPTIONS"])
def proxy(ruta):
    global _token
    if request.method == "OPTIONS":
        return jsonify({}), 200
    token = get_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{HGI_BASE}/{ruta}"
    try:
        if request.method == "POST":
            r = requests.post(url, json=request.get_json(), headers=headers, params=request.args, timeout=20)
        else:
            r = requests.get(url, headers=headers, params=request.args, timeout=20)
        if r.status_code == 401:
            _token = None
            obtener_token()
            headers["Authorization"] = f"Bearer {_token}"
            if request.method == "POST":
                r = requests.post(url, json=request.get_json(), headers=headers, params=request.args, timeout=20)
            else:
                r = requests.get(url, headers=headers, params=request.args, timeout=20)
        try:
            return jsonify(r.json()), r.status_code
        except Exception:
            return r.text, r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    obtener_token()
    app.run(host="0.0.0.0", port=5000)
