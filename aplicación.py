from flask import Flask, request, jsonify
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

_token = None
def renovar_token():
    global _token
    url = f"{HGI_BASE}/Autenticar?usuario={HGI_USUARIO}&clave={HGI_CLAVE}&cod_compania={HGI_COMPANIA}&cod_empresa={HGI_EMPRESA}"
    while True:
        try:
            r = requests.get(url, timeout=15, verify=False)
            data = r.json()
            jwt = data.get("JwtToken")
            if jwt:
                _token = jwt
                print(f"[MILO] ✅ Token renovado!")
                return True
            codigo = data.get("Error", {}).get("Codigo")
            if codigo == 3:
                print("[MILO] Token vigente en HGI - esperando 60s...")
                time.sleep(60)
                continue
        except Exception as e:
            print(f"[MILO] Error: {e}")
            time.sleep(10)

def hilo_renovador():
    while True:
        time.sleep(18 * 60)
        print("[MILO] Renovando token automatico...")
        renovar_token()

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
    return jsonify({"status": "OK", "token": bool(_token), "preview": _token[:25]+"..." if _token else "SIN TOKEN"})

@app.route("/api/<path:ruta>", methods=["GET","POST","OPTIONS"])
def proxy(ruta):
    global _token
    if request.method == "OPTIONS":
        return jsonify({}), 200
    if not _token:
        return jsonify({"error": "Sin token - espera renovacion"}), 401

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_token}"
    }
    url = f"{HGI_BASE}/{ruta}"

    try:
        if request.method == "POST":
            body = request.get_json()
            print(f"[MILO] POST {ruta}")
            r = requests.post(url, json=body, headers=headers, params=request.args.to_dict(), timeout=30, verify=False)
        else:
            r = requests.get(url, headers=headers, params=request.args.to_dict(), timeout=30, verify=False)

        print(f"[HGI] {r.status_code} | {r.text[:150]}")

        if r.status_code in [400, 401, 403]:
            print("[MILO] Token rechazado - renovando en hilo...")
            t = threading.Thread(target=renovar_token, daemon=True)
            t.start()

        try:
            return jsonify(r.json()), r.status_code
        except Exception:
            return r.text, r.status_code

    except Exception as e:
        print(f"[MILO] Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("[MILO] Iniciando - obteniendo token...")
    t = threading.Thread(target=renovar_token, daemon=False)
    t.start()
    t.join()  # Esperar token antes de arrancar
    tr = threading.Thread(target=hilo_renovador, daemon=True)
    tr.start()
    print("[MILO] Proxy en http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
