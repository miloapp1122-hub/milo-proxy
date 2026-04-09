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

def renovar_token():
    global _token
    url = f"{HGI_BASE}/Autenticar?usuario={HGI_USUARIO}&clave={HGI_CLAVE}&cod_compania={HGI_COMPANIA}&cod_empresa={HGI_EMPRESA}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        jwt = data.get("JwtToken")
        if jwt:
            _token = jwt
            print("Token renovado OK")
            return _token
        if data.get("Error", {}).get("Codigo") == 3:
            print("Token aun vigente")
            return _token
    except Exception as e:
        print(f"Error renovando token: {e}")
    return _token

def renovador_automatico():
    """Renueva el token cada 15 minutos en segundo plano"""
    while True:
        threading.Event().wait(15 * 60)  # esperar 15 min
        print("Renovando token automaticamente...")
        renovar_token()

def get_token():
    global _token
    if not _token:
        with _token_lock:
            if not _token:
                renovar_token()
    return _token

@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

@app.route("/", methods=["GET"])
def health():
    tk = get_token()
    return jsonify({
        "status": "Milo Proxy activo",
        "hgi": HGI_BASE,
        "token_ok": bool(tk),
        "renovacion": "cada 15 minutos automatico"
    })

@app.route("/api/<path:ruta>", methods=["GET", "POST", "OPTIONS"])
def proxy(ruta):
    global _token
    if request.method == "OPTIONS":
        return jsonify({}), 200

    token = get_token()
    if not token:
        return jsonify({"error": "Sin token HGI"}), 401

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    url = f"{HGI_BASE}/{ruta}"
    params = request.args.to_dict()

    try:
        if request.method == "POST":
            r = requests.post(url, json=request.get_json(), headers=headers, params=params, timeout=30)
        else:
            r = requests.get(url, headers=headers, params=params, timeout=30)

        # Si token expiró renovar y reintentar una vez
        if r.status_code in [401, 403]:
            print("Token expirado en peticion, renovando...")
            _token = None
            renovar_token()
            headers["Authorization"] = f"Bearer {_token}"
            if request.method == "POST":
                r = requests.post(url, json=request.get_json(), headers=headers, params=params, timeout=30)
            else:
                r = requests.get(url, headers=headers, params=params, timeout=30)

        try:
            return jsonify(r.json()), r.status_code
        except Exception:
            return r.text, r.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Autenticar al arrancar y lanzar renovador en segundo plano
renovar_token()
hilo = threading.Thread(target=renovador_automatico, daemon=True)
hilo.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
