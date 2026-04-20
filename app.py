from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import threading
import time
import urllib3
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

urllib3.disable_warnings()

app = Flask(__name__)
CORS(app, origins="*")

# ─── CONFIG HGI ────────────────────────────────────────────
HGI_BASE     = 'https://900405097.hginet.com.co/Api'
HGI_USUARIO  = '98711025'
HGI_CLAVE    = 'C9871'
HGI_COMPANIA = '1'
HGI_EMPRESA  = '1'

# ─── CONFIG NOTIFICACIONES ─────────────────────────────────
EMAIL_ORIGEN     = os.environ.get('EMAIL_ORIGEN', '')
EMAIL_PASSWORD   = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_CARTERA    = os.environ.get('EMAIL_CARTERA', '')
EMAIL_LOGISTICA  = os.environ.get('EMAIL_LOGISTICA', '')
WA_API_KEY_CARTERA = os.environ.get('WA_API_KEY_CARTERA', '')
WA_NUM_CARTERA     = os.environ.get('WA_NUM_CARTERA', '')
SHEETS_CREDS_JSON  = os.environ.get('SHEETS_CREDS_JSON', '{}')
SHEET_ID_CARTERA   = os.environ.get('SHEET_ID_CARTERA', '')
SHEET_ID_MENSAJEROS = os.environ.get('SHEET_ID_MENSAJEROS', '')

try:
    _wa_keys = json.loads(os.environ.get('WA_API_KEY_MENS', '{}'))
    _wa_nums = json.loads(os.environ.get('WA_NUMS_MENSAJEROS', '{}'))
except:
    _wa_keys = {}
    _wa_nums = {}

# ─── TOKEN HGI (background thread) ────────────────────────
_token = None
_token_lock = threading.Lock()

def renovar_token():
    global _token
    url = f"{HGI_BASE}/Autenticar?usuario={HGI_USUARIO}&clave={HGI_CLAVE}&cod_compania={HGI_COMPANIA}&cod_empresa={HGI_EMPRESA}"
    while True:
        try:
            r = requests.get(url, timeout=15, verify=False)
            data = r.json()
            jwt = data.get('JwtToken')
            if jwt:
                with _token_lock:
                    _token = jwt
                print(f'[MILO] ✅ Token renovado!')
                time.sleep(18 * 60)  # Renovar cada 18 minutos
            else:
                msg = data.get('Error', {}).get('Mensaje', '?')
                print(f'[MILO] Token vigente ({msg}) - esperando 60s...')
                time.sleep(60)
        except Exception as e:
            print(f'[MILO] Error auth: {e}')
            time.sleep(30)

# ─── UTILIDADES ────────────────────────────────────────────
def fmt_cop(v):
    try: return f"${int(v):,}".replace(',', '.')
    except: return str(v)

def ts_col():
    return datetime.now().strftime('%d/%m/%Y %H:%M')

def enviar_correo(dest, asunto, html):
    if not EMAIL_PASSWORD: return True
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
    if not api_key: return True
    try:
        r = requests.get('https://api.callmebot.com/whatsapp.php',
            params={'phone': numero, 'text': mensaje, 'apikey': api_key}, timeout=10)
        return r.status_code == 200
    except: return False

def sheets_append(sheet_id, tab, row):
    if not sheet_id: return False
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
        creds_dict = json.loads(SHEETS_CREDS_JSON)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(sheet_id)
        try: ws = sh.worksheet(tab)
        except: ws = sh.add_worksheet(title=tab, rows=1000, cols=20)
        ws.append_row(row)
        return True
    except Exception as e:
        print(f'[Sheets] Error: {e}')
        return False

# ─── HEALTH ────────────────────────────────────────────────
@app.route('/', methods=['GET'])
def health():
    with _token_lock:
        tok = _token
    return jsonify({
        'status': 'ok',
        'app': 'MILO Backend',
        'version': '2.0',
        'token': bool(tok),
        'preview': tok[:20] + '...' if tok else None
    })

@app.route('/ping', methods=['GET'])
def ping():
    with _token_lock:
        tok = _token
    return jsonify({'pong': True, 'ts': ts_col(), 'token': bool(tok)})

# ─── LOGIN (devuelve token al frontend) ────────────────────
@app.route('/hgi/token', methods=['POST', 'OPTIONS'])
def hgi_token():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    with _token_lock:
        tok = _token
    if tok:
        print(f'[Login] Token disponible, enviando al frontend')
        return jsonify({'JwtToken': tok, 'access_token': tok}), 200
    else:
        return jsonify({'error': 'Token no disponible aún, espera 30s'}), 503

# ─── PROXY HGI GENÉRICO ────────────────────────────────────
@app.route('/hgi/<path:endpoint>', methods=['GET', 'POST', 'OPTIONS'])
def hgi_proxy(endpoint):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    with _token_lock:
        tok = _token
    if not tok:
        return jsonify({'error': 'Sin token'}), 401
    headers = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}
    params = {k: v for k, v in request.args.items()}
    url = f'{HGI_BASE}/{endpoint}'
    print(f'[Proxy] {request.method} /{endpoint}')
    try:
        if request.method == 'POST':
            r = requests.post(url, json=request.get_json(), headers=headers,
                              params=params, timeout=30, verify=False)
        else:
            r = requests.get(url, headers=headers, params=params,
                             timeout=30, verify=False)
        if r.status_code == 401:
            with _token_lock:
                _token = None
        try:
            return jsonify(r.json()), r.status_code
        except:
            return r.text, r.status_code
    except Exception as e:
        print(f'[Proxy] Error: {e}')
        return jsonify({'error': str(e)}), 500

# ─── CARTERA ───────────────────────────────────────────────
@app.route('/api/cartera/gestion', methods=['POST'])
def cartera_gestion():
    d = request.get_json()
    if not d: return jsonify({'error': 'Sin datos'}), 400
    ts = ts_col()
    res = {
        'correo': enviar_correo(EMAIL_CARTERA,
            f'[MILO] Cartera · {d.get("nit","-")}',
            f"<html><body><h2>Gestión Cartera</h2><p>NIT: {d.get('nit')}</p><p>Tipo: {d.get('tipo')}</p><p>Valor: {fmt_cop(d.get('valor',0))}</p><p>Obs: {d.get('observaciones')}</p></body></html>"),
        'whatsapp': enviar_wa(WA_NUM_CARTERA, WA_API_KEY_CARTERA,
            f"MILO Cartera\nNIT: {d.get('nit')}\nTipo: {d.get('tipo')}\nValor: {fmt_cop(d.get('valor',0))}"),
        'sheets': sheets_append(SHEET_ID_CARTERA, 'Gestiones',
            [ts, d.get('nit'), d.get('tipo'), fmt_cop(d.get('valor',0)),
             d.get('fecha'), d.get('observaciones'), d.get('registradoPor')])
    }
    return jsonify({'ok': True, 'resultados': res, 'timestamp': ts})

# ─── MENSAJEROS ────────────────────────────────────────────
@app.route('/api/mensajeros/despachos', methods=['GET'])
def mensajeros_despachos():
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
        creds_dict = json.loads(SHEETS_CREDS_JSON)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID_MENSAJEROS)
        return jsonify(sh.worksheet('Despachos').get_all_records())
    except: return jsonify([])

@app.route('/api/mensajeros/asignar', methods=['POST'])
def mensajeros_asignar():
    d = request.get_json()
    if not d: return jsonify({'error': 'Sin datos'}), 400
    ts = ts_col()
    mens_id = d.get('mensajeroId', '')
    res = {
        'correo': enviar_correo(EMAIL_LOGISTICA,
            f'[MILO] Despacho {d.get("pedido")}',
            f"<html><body><h2>Despacho Asignado</h2><p>Pedido: {d.get('pedido')}</p><p>Cliente: {d.get('cliente')}</p><p>Mensajero: {d.get('mensajero')}</p></body></html>"),
        'whatsapp': enviar_wa(_wa_nums.get(mens_id,''), _wa_keys.get(mens_id,''),
            f"MILO Despacho\n{d.get('pedido')}\n{d.get('cliente')}\n{d.get('direccion')}") if _wa_nums.get(mens_id) else False,
        'sheets': sheets_append(SHEET_ID_MENSAJEROS, 'Despachos',
            [ts, d.get('pedido'), d.get('cliente'), d.get('direccion'),
             d.get('mensajero'), d.get('fecha'), 'pendiente', d.get('observaciones','')])
    }
    return jsonify({'ok': True, 'id': f'DES-{int(datetime.now().timestamp())}', 'resultados': res})

@app.route('/api/mensajeros/estado', methods=['POST'])
def mensajeros_estado():
    d = request.get_json()
    return jsonify({'ok': True, 'estado': d.get('estado'), 'timestamp': ts_col()})

@app.route('/api/mensajeros/novedad', methods=['POST'])
def mensajeros_novedad():
    d = request.get_json()
    if not d: return jsonify({'error': 'Sin datos'}), 400
    ts = ts_col()
    res = {
        'correo': enviar_correo(EMAIL_LOGISTICA,
            f'⚠️ [MILO] Novedad {d.get("pedido")}',
            f"<html><body><h2 style='color:red'>Novedad</h2><p>{d.get('pedido')}</p><p>{d.get('tipo')}</p><p>{d.get('descripcion')}</p></body></html>"),
        'whatsapp': enviar_wa(WA_NUM_CARTERA, WA_API_KEY_CARTERA,
            f"MILO NOVEDAD\n{d.get('pedido')}\n{d.get('tipo')}\n{d.get('descripcion','')[:100]}"),
        'sheets': sheets_append(SHEET_ID_MENSAJEROS, 'Novedades',
            [ts, d.get('pedido'), d.get('tipo'), d.get('descripcion'), d.get('reportadoPor','')])
    }
    return jsonify({'ok': True, 'timestamp': ts, 'resultados': res})

# ─── ARRANQUE DEL THREAD ──────────────────────────────────
_thread_iniciado = False

@app.before_request
def iniciar_thread():
    global _thread_iniciado
    if not _thread_iniciado:
        _thread_iniciado = True
        t = threading.Thread(target=renovar_token, daemon=True)
        t.start()
        print('[MILO] Thread de token iniciado')

if __name__ == '__main__':
    t = threading.Thread(target=renovar_token, daemon=True)
    t.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
