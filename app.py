"""
MILO Backend v2.0 - Flask en Render
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import urllib3
import json
import os
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
CORS(app, origins="*")

HGI_BASE         = 'https://900405097.hginet.com.co/Api'
EMAIL_ORIGEN     = os.environ.get('EMAIL_ORIGEN', 'milo@lubriandes.com')
EMAIL_PASSWORD   = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_CARTERA    = os.environ.get('EMAIL_CARTERA', 'cartera@lubriandes.com')
EMAIL_LOGISTICA  = os.environ.get('EMAIL_LOGISTICA', 'logistica@lubriandes.com')
WA_API_KEY_CARTERA  = os.environ.get('WA_API_KEY_CARTERA', '')
WA_NUM_CARTERA      = os.environ.get('WA_NUM_CARTERA', '')
SHEETS_CREDS_JSON   = os.environ.get('SHEETS_CREDS_JSON', '{}')
SHEET_ID_CARTERA    = os.environ.get('SHEET_ID_CARTERA', '')
SHEET_ID_MENSAJEROS = os.environ.get('SHEET_ID_MENSAJEROS', '')

try:
    _wa_keys = json.loads(os.environ.get('WA_API_KEY_MENS', '{}'))
    _wa_nums = json.loads(os.environ.get('WA_NUMS_MENSAJEROS', '{}'))
except:
    _wa_keys = {}
    _wa_nums = {}

def fmt_cop(valor):
    try: return f"${int(valor):,}".replace(',', '.')
    except: return str(valor)

def ts_col():
    return datetime.now().strftime('%d/%m/%Y %H:%M')

def get_sheets_client():
    try:
        creds_dict = json.loads(SHEETS_CREDS_JSON)
        scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f'[Sheets] Error: {e}')
        return None

def sheets_append(sheet_id, tab, row):
    try:
        gc = get_sheets_client()
        if not gc: return False
        sh = gc.open_by_key(sheet_id)
        try: ws = sh.worksheet(tab)
        except: ws = sh.add_worksheet(title=tab, rows=1000, cols=20)
        ws.append_row(row)
        return True
    except Exception as e:
        print(f'[Sheets] Error: {e}')
        return False

def enviar_correo(dest, asunto, html):
    if not EMAIL_PASSWORD:
        print(f'[Correo] Sin password, simulando')
        return True
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = asunto
        msg['From'] = EMAIL_ORIGEN
        msg['To'] = dest
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(EMAIL_ORIGEN, EMAIL_PASSWORD)
            s.sendmail(EMAIL_ORIGEN, dest, msg.as_string())
        return True
    except Exception as e:
        print(f'[Correo] Error: {e}')
        return False

def enviar_wa(numero, api_key, mensaje):
    if not api_key:
        print(f'[WA] Sin apikey')
        return True
    try:
        r = requests.get('https://api.callmebot.com/whatsapp.php',
            params={'phone': numero, 'text': mensaje, 'apikey': api_key}, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f'[WA] Error: {e}')
        return False

# ─── HEALTH & KEEP ALIVE ───────────────────────────────────
@app.route('/', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'app': 'MILO Backend', 'version': '2.0'})

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({'pong': True, 'ts': ts_col()})

# ─── PROXY HGI ─────────────────────────────────────────────
@app.route('/hgi/token', methods=['POST', 'OPTIONS'])
def hgi_token():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    datos = request.get_json()
    u = datos.get('username', '')
    p = datos.get('password', '')
    print(f'[HGI Token] Intentando login para: {u}')
    try:
        r = requests.post(
            f'{HGI_BASE}/token',
            data=f'grant_type=password&username={u}&password={p}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=20,
            verify=False
        )
        print(f'[HGI Token] Status: {r.status_code}')
        print(f'[HGI Token] Respuesta: {r.text[:200]}')
        return jsonify(r.json()), r.status_code
    except Exception as e:
        print(f'[HGI Token] ERROR: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/hgi/<path:endpoint>', methods=['GET', 'POST', 'OPTIONS'])
def hgi_proxy(endpoint):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    token = request.headers.get('X-HGI-Token', '')
    headers = {'Authorization': f'Bearer {token}'}
    print(f'[HGI Proxy] {request.method} /{endpoint}')
    try:
        if request.method == 'GET':
            r = requests.get(f'{HGI_BASE}/{endpoint}',
                params=request.args, headers=headers, timeout=20, verify=False)
        else:
            r = requests.post(f'{HGI_BASE}/{endpoint}',
                json=request.get_json(), headers=headers, timeout=20, verify=False)
        print(f'[HGI Proxy] Status: {r.status_code}')
        return jsonify(r.json()), r.status_code
    except Exception as e:
        print(f'[HGI Proxy] ERROR: {e}')
        return jsonify({'error': str(e)}), 500

# ─── CARTERA ───────────────────────────────────────────────
@app.route('/api/cartera/gestion', methods=['POST'])
def cartera_gestion():
    d = request.get_json()
    if not d: return jsonify({'error': 'Sin datos'}), 400
    nit    = d.get('nit', '-')
    tipo   = d.get('tipo', '-')
    valor  = d.get('valor', 0)
    obs    = d.get('observaciones', '-')
    fecha  = d.get('fecha', '-')
    usuario = d.get('registradoPor', '-')
    ts = ts_col()
    res = {}
    html = f"<html><body style='font-family:Arial'><h2>Gestión Cartera · {ts}</h2><p><b>NIT:</b> {nit}</p><p><b>Tipo:</b> {tipo}</p><p><b>Valor:</b> {fmt_cop(valor)}</p><p><b>Obs:</b> {obs}</p></body></html>"
    res['correo'] = enviar_correo(EMAIL_CARTERA, f'[MILO] Cartera · {nit}', html)
    res['whatsapp'] = enviar_wa(WA_NUM_CARTERA, WA_API_KEY_CARTERA,
        f"MILO Cartera\nNIT: {nit}\nTipo: {tipo}\nValor: {fmt_cop(valor)}\n{obs[:80]}")
    gps = d.get('gps') or {}
    res['sheets'] = sheets_append(SHEET_ID_CARTERA, 'Gestiones',
        [ts, nit, tipo, fmt_cop(valor), fecha, obs, usuario, gps.get('lat',''), gps.get('lng','')])
    return jsonify({'ok': True, 'resultados': res})

@app.route('/api/cartera/historial', methods=['GET'])
def cartera_historial():
    try:
        gc = get_sheets_client()
        if not gc: return jsonify([])
        sh = gc.open_by_key(SHEET_ID_CARTERA)
        return jsonify(sh.worksheet('Gestiones').get_all_records())
    except: return jsonify([])

# ─── MENSAJEROS ────────────────────────────────────────────
@app.route('/api/mensajeros/despachos', methods=['GET'])
def mensajeros_despachos():
    try:
        gc = get_sheets_client()
        if not gc: return jsonify([])
        sh = gc.open_by_key(SHEET_ID_MENSAJEROS)
        return jsonify(sh.worksheet('Despachos').get_all_records())
    except: return jsonify([])

@app.route('/api/mensajeros/asignar', methods=['POST'])
def mensajeros_asignar():
    d = request.get_json()
    if not d: return jsonify({'error': 'Sin datos'}), 400
    pedido = d.get('pedido','-'); cliente = d.get('cliente','-')
    dir_ = d.get('direccion','-'); mensajero = d.get('mensajero','-')
    mens_id = d.get('mensajeroId',''); fecha = d.get('fecha','-')
    obs = d.get('observaciones',''); ts = ts_col()
    res = {}
    html = f"<html><body style='font-family:Arial'><h2>Despacho Asignado · {ts}</h2><p><b>Pedido:</b> {pedido}</p><p><b>Cliente:</b> {cliente}</p><p><b>Dir:</b> {dir_}</p><p><b>Mensajero:</b> {mensajero}</p></body></html>"
    res['correo'] = enviar_correo(EMAIL_LOGISTICA, f'[MILO] Despacho {pedido}', html)
    wa_num = _wa_nums.get(mens_id,''); wa_key = _wa_keys.get(mens_id,'')
    if wa_num:
        res['whatsapp'] = enviar_wa(wa_num, wa_key, f"MILO Despacho\n{pedido}\n{cliente}\n{dir_}")
    res['sheets'] = sheets_append(SHEET_ID_MENSAJEROS, 'Despachos',
        [ts, pedido, cliente, dir_, mensajero, fecha, 'pendiente', obs])
    return jsonify({'ok': True, 'id': f'DES-{int(datetime.now().timestamp())}', 'resultados': res})

@app.route('/api/mensajeros/estado', methods=['POST'])
def mensajeros_estado():
    d = request.get_json()
    if not d: return jsonify({'error': 'Sin datos'}), 400
    return jsonify({'ok': True, 'estado': d.get('estado'), 'timestamp': ts_col()})

@app.route('/api/mensajeros/novedad', methods=['POST'])
def mensajeros_novedad():
    d = request.get_json()
    if not d: return jsonify({'error': 'Sin datos'}), 400
    pedido = d.get('pedido','-'); tipo = d.get('tipo','-'); desc = d.get('descripcion','-')
    ts = ts_col(); res = {}
    res['correo'] = enviar_correo(EMAIL_LOGISTICA, f'⚠️ [MILO] Novedad {pedido}',
        f"<html><body><h2 style='color:red'>Novedad: {pedido}</h2><p>{tipo}</p><p>{desc}</p></body></html>")
    res['whatsapp'] = enviar_wa(WA_NUM_CARTERA, WA_API_KEY_CARTERA,
        f"MILO NOVEDAD\n{pedido}\n{tipo}\n{desc[:100]}")
    gps = d.get('gps') or {}
    res['sheets'] = sheets_append(SHEET_ID_MENSAJEROS, 'Novedades',
        [ts, pedido, tipo, desc, d.get('reportadoPor',''), gps.get('lat',''), gps.get('lng','')])
    return jsonify({'ok': True, 'timestamp': ts, 'resultados': res})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
