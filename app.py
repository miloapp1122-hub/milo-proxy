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

_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c3VhcmlvIjoiOTg3MTEwMjUiLCJjbGF2ZSI6IkM5ODcxIiwiY29kX2NvbXBhbmlhIjoiMSIsImNvZF9lbXByZXNhIjoiMSIsImVzdGFkbyI6IjEiLCJpZF9hcGxpY2F0aXZvIjoiMTEiLCJpZF9hcGxpY2F0aXZvX3BldGljaW9uIjoiMTEiLCJuYmYiOjE3NzU3Njg3MjMsImV4cCI6MTc3NTc4OTcyMywiaWF0IjoxNzc1NzY4NzIzfQ.jFyHy4eMgU-M0ZsuV9rfHz-sSD5IaIikjf9BZVJ2_FA"
def auth():
    global _token
    url = f"{HGI_BASE}/Autenticar?usuario={HGI_USUARIO}&clave={HGI_CLAVE}&cod_compania={HGI_COMPANIA}&cod_empresa={HGI_EMPRESA}"
    r = requests.get(url, timeout=15, verify=False)
    data = r.json()
    jwt = data.get("JwtToken")
    if jwt:
        _token = jwt
        print(f"[MILO] Token OK: {jwt[:20]}...")
    else:
        print(f"[MILO] Respuesta auth: {data.get('Error',{}).get('Mensaje','?')}")

@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "OK", "token": bool(_token), "preview": _token[:20]+"..." if _token else None})

@app.route("/api/<path:ruta>", methods=["GET","POST","OPTIONS"])
def proxy(ruta):
    if request.method == "OPTIONS":
        return jsonify({}), 200
    if not _token:
        return jsonify({"error": "Sin token"}), 401
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {_token}"}
    url = f"{HGI_BASE}/{ruta}"
    try:
        if request.method == "POST":
            r = requests.post(url, json=request.get_json(), headers=headers, params=request.args.to_dict(), timeout=30, verify=False)
        else:
            r = requests.get(url, headers=headers, params=request.args.to_dict(), timeout=30, verify=False)
        try:
            return jsonify(r.json()), r.status_code
        except:
            return r.text, r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("[MILO] Iniciando...")
    auth()
    print("[MILO] Proxy en http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
