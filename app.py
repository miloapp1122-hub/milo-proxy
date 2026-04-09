from flask import Flask, request, jsonify
import requests
import threading
import time

app = Flask(__name__)

HGI_BASE = "https://900405097.hginet.com.co/Api"
HGI_USUARIO = "98711025"
HGI_CLAVE = "C9871"
HGI_COMPANIA = "1"
HGI_EMPRESA = "1"

_token = None

def renovar_token():
    global _token
    url = f"{HGI_BASE}/Autenticar?usuario={HGI_USUARIO}&clave={HGI_CLAVE}&cod_compania={HGI_COMPANIA}&cod_empresa={HGI_EMPRESA}"
    try:
        r = requests.get(url, timeout=15, verify=False)
        data = r.json()
        if data.get("JwtToken"):
            _token = data["JwtToken"]
            print(f"[MILO] Token renovado OK")
            return True
        if data.get("Error", {}).get("Codigo") == 3:
            print("[MILO] Token vigente")
            return True
    except Exception as e:
        print(f"[MILO] Error: {e}")
    return False

def hilo_renovador():
    while True:
        time.sleep(15 * 60)
        renovar_token()

@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "Milo Proxy local activo", "token_ok": bool(_token)})

@app.route("/api/<path:ruta>", methods=["GET", "POST", "OPTIONS"])
def proxy(ruta):
    global _token
    if request.method == "OPTIONS":
        return jsonify({}), 200
    if not _token:
        renovar_token()
    if not _token:
        return jsonify({"error": "Sin token"}), 401

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_token}"
    }
    url = f"{HGI_BASE}/{ruta}"
    params = request.args.to_dict()

    try:
        if request.method == "POST":
            r = requests.post(url, json=request.get_json(), headers=headers, params=params, timeout=30, verify=False)
        else:
            r = requests.get(url, headers=headers, params=params, timeout=30, verify=False)

        if r.status_code in [401, 403]:
            _token = None
            renovar_token()
            headers["Authorization"] = f"Bearer {_token}"
            r = requests.get(url, headers=headers, params=params, timeout=30, verify=False)

        try:
            return jsonify(r.json()), r.status_code
        except:
            return r.text, r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("[MILO] Iniciando proxy local...")
    renovar_token()
    t = threading.Thread(target=hilo_renovador, daemon=True)
    t.start()
    print("[MILO] Proxy corriendo en http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
