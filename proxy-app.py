from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

HGI_BASE = "https://900405097.hginet.com.co/Api"

def cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

@app.after_request
def after(r):
    return cors(r)

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "Milo Proxy activo", "hgi": HGI_BASE})

@app.route("/api/<path:ruta>", methods=["GET", "POST", "OPTIONS"])
def proxy(ruta):
    if request.method == "OPTIONS":
        return jsonify({}), 200
    url = f"{HGI_BASE}/{ruta}"
    headers = {}
    if request.headers.get("Authorization"):
        headers["Authorization"] = request.headers.get("Authorization")
    if request.method == "POST":
        r = requests.post(url, json=request.get_json(), headers=headers, params=request.args, timeout=15)
    else:
        r = requests.get(url, headers=headers, params=request.args, timeout=15)
    try:
        return jsonify(r.json()), r.status_code
    except Exception:
        return r.text, r.status_code

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
