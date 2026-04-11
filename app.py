from flask import Flask, request, jsonify
import requests
import urllib3
import threading
import time
import os
import json
urllib3.disable_warnings()

app = Flask(__name__)

HGI_BASE = "https://900405097.hginet.com.co/Api"
HGI_USUARIO = "98711025"
HGI_CLAVE = "C9871"
HGI_COMPANIA = "1"
HGI_EMPRESA = "1"
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

def obtener_token_hgi():
    """Obtiene token de HGI. Si dice vigente, fuerza invalidacion y reintenta."""
    url = f"{HGI_BASE}/Autenticar?usuario={HGI_USUARIO}&clave={HGI_CLAVE}&cod_compania={HGI_COMPANIA}&cod_empresa={HGI_EMPRESA}"
    intentos = 0
    while True:
        try:
            r = requests.get(url, timeout=15, verify=False)
            data = r.json()
            jwt = data.get("JwtToken")
            if jwt:
                guardar_token(jwt)
                print(f"[MILO] Token renovado y guardado!")
                return jwt
            codigo = data.get("Error", {}).get("Codigo")
            if codigo == 3:
                intentos += 1
                print(f"[MILO] Token vigente en HGI - esperando 60s... (intento {intentos})")
                # Despues de muchos intentos, forzar con usuario diferente no es opcion
                # Solo esperar a que expire el token anterior
                time.sleep(60)
                continue
        except Exception as e:
            print(f"[MILO] Error autenticando: {e}")
            time.sleep(10)

def hilo_renovador():
    while True:
        time.sleep(18 * 60)
        print("[MILO] Renovando token automatico...")
        obtener_token_hgi()

def hilo_inicio():
    token = obtener_token_hgi()
    # Iniciar renovacion automatica
    tr = threading.Thread(target=hilo_renovador, daemon=True)
    tr.start()

# Iniciar al cargar el modulo
print("[MILO] Iniciando - obteniendo token...")
_t = threading.Thread(target=hilo_inicio, daemon=True)
_t.start()

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

@app.route("/api/<path:ruta>", methods=["GET","POST","OPTIONS"])
def proxy(ruta):
    if request.method == "OPTIONS":
        return jsonify({}), 200

    token = leer_token()
    if not token:
        return jsonify({"error": "Sin token - espera renovacion"}), 401

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

        print(f"[HGI] {r.status_code} | {r.text[:150]}")

        if r.status_code in [400, 401, 403]:
            print("[MILO] Token rechazado - renovando...")
            t = threading.Thread(target=obtener_token_hgi, daemon=True)
            t.start()

        try:
            return jsonify(r.json()), r.status_code
        except Exception:
            return r.text, r.status_code

    except Exception as e:
        print(f"[MILO] Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("[MILO] Proxy en http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
