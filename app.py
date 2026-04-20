from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import urllib3
import json
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

urllib3.disable_warnings()

app = Flask(__name__)
CORS(app, origins="*")

HGI_BASE         = 'https://900405097.hginet.com.co/Api'
EMAIL_ORIGEN     = os.environ.get('EMAIL_ORIGEN', '')
EMAIL_PASSWORD   = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_CARTERA    = os.environ.get('EMAIL_CARTERA', '')
EMAIL_LOGISTICA  = os.environ.get('EMAIL_LOGISTICA', '')
WA_API_KEY_CARTERA = os.environ.get('WA_API_KEY_CARTERA', '')
WA_NUM_CARTERA   = os.environ.get('WA_NUM_CARTERA', '')
SHEETS_CREDS_JSON  = os.environ.get('SHEETS_CREDS_JSON', '{}')
SHEET_ID_CARTERA   = os.environ.get('SHEET_ID_CARTERA', '')
SHEET_ID_MENSAJEROS = os.environ.get('SHEET_ID_MENSAJEROS', '')

try:
    _wa_keys = json.loads(os.environ.get('WA_API_KEY_MENS', '{}'))
    _wa_nums = json.loads(os.environ.get('WA_NUMS_MENSAJEROS', '{}'))
except:
    _wa_keys = {}
    _wa_nums = {}

def fmt_cop(v):
    try: return f"${int(v):,}".replace(',','.')
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
            params={'phone':numero,'text':mensaje,'apikey':api_key}, timeout=10)
        return r.status_code == 200
    except: return False

def sheets_append(sheet_id, tab, row):
    if not sheet_id: return False
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
        creds_dict = json.loads(SHEETS_CREDS_JSON)
        scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
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

@app.route('/', methods=['GET'])
def health():
    return jsonify({'status':'ok','app':'MILO Backend','version':'2.0'})

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({'pong':True,'ts':ts_col()})

@app.route('/hgi/token', methods=['POST','OPTIONS'])
def hgi_token():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    datos = request.get_json()
    u = datos.get('username','')
    p = datos.get('password','')
    print(f'[Login] Usuario: {u}')
    try:
        # HGI requiere form-urlencoded con grant_type=password
        # HGI usa GET con params para autenticar
        r = requests.get(
            f'{HGI_BASE}/Autenticar',
            params={'usuario':u,'clave':p,'cod_compania':'1','cod_empresa':'1'},
            timeout=20,
            verify=False
        )
        print(f'[Login] Status HGI: {r.status_code}')
        print(f'[Login] Respuesta: {r.text[:300]}')
        data = r.json()
        # HGI devuelve JwtToken, lo mapeamos a access_token también
        if 'JwtToken' in data:
            data['access_token'] = data['JwtToken']
        return jsonify(data), r.status_code
    except Exception as e:
        print(f'[Login] ERROR: {e}')
        return jsonify({'error':str(e)}), 500

@app.route('/hgi/<path:endpoint>', methods=['GET','POST','OPTIONS'])
def hgi_proxy(endpoint):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    token = request.headers.get('X-HGI-Token','')
    headers = {'Authorization':f'Bearer {token}'}
    print(f'[Proxy] {request.method} /{endpoint}')
    try:
        if request.method == 'GET':
            r = requests.get(f'{HGI_BASE}/{endpoint}',
                params=request.args, headers=headers, timeout=20, verify=False)
        else:
            r = requests.post(f'{HGI_BASE}/{endpoint}',
                json=request.get_json(), headers=headers, timeout=20, verify=False)
        print(f'[Proxy] Status: {r.status_code}')
        return jsonify(r.json()), r.status_code
    except Exception as e:
        print(f'[Proxy] ERROR: {e}')
        return jsonify({'error':str(e)}), 500

@app.route('/api/cartera/gestion', methods=['POST'])
def cartera_gestion():
    d = request.get_json()
    if not d: return jsonify({'error':'Sin datos'}), 400
    ts = ts_col()
    res = {
        'correo': enviar_correo(EMAIL_CARTERA, f'[MILO] Cartera · {d.get("nit","-")}',
            f"<html><body><h2>Gestión Cartera</h2><p>NIT: {d.get('nit')}</p><p>Tipo: {d.get('tipo')}</p><p>Valor: {fmt_cop(d.get('valor',0))}</p><p>Obs: {d.get('observaciones')}</p></body></html>"),
        'whatsapp': enviar_wa(WA_NUM_CARTERA, WA_API_KEY_CARTERA,
            f"MILO Cartera\nNIT: {d.get('nit')}\nTipo: {d.get('tipo')}\nValor: {fmt_cop(d.get('valor',0))}"),
        'sheets': sheets_append(SHEET_ID_CARTERA, 'Gestiones',
            [ts, d.get('nit'), d.get('tipo'), fmt_cop(d.get('valor',0)),
             d.get('fecha'), d.get('observaciones'), d.get('registradoPor')])
    }
    return jsonify({'ok':True,'resultados':res,'timestamp':ts})

@app.route('/api/mensajeros/despachos', methods=['GET'])
def mensajeros_despachos():
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
        creds_dict = json.loads(SHEETS_CREDS_JSON)
        scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID_MENSAJEROS)
        return jsonify(sh.worksheet('Despachos').get_all_records())
    except: return jsonify([])

@app.route('/api/mensajeros/asignar', methods=['POST'])
def mensajeros_asignar():
    d = request.get_json()
    if not d: return jsonify({'error':'Sin datos'}), 400
    ts = ts_col()
    mens_id = d.get('mensajeroId','')
    wa_num = _wa_nums.get(mens_id,'')
    wa_key = _wa_keys.get(mens_id,'')
    res = {
        'correo': enviar_correo(EMAIL_LOGISTICA, f'[MILO] Despacho {d.get("pedido")}',
            f"<html><body><h2>Despacho Asignado</h2><p>Pedido: {d.get('pedido')}</p><p>Cliente: {d.get('cliente')}</p><p>Mensajero: {d.get('mensajero')}</p></body></html>"),
        'whatsapp': enviar_wa(wa_num, wa_key, f"MILO Despacho\n{d.get('pedido')}\n{d.get('cliente')}\n{d.get('direccion')}") if wa_num else False,
        'sheets': sheets_append(SHEET_ID_MENSAJEROS, 'Despachos',
            [ts, d.get('pedido'), d.get('cliente'), d.get('direccion'),
             d.get('mensajero'), d.get('fecha'), 'pendiente', d.get('observaciones','')])
    }
    return jsonify({'ok':True,'id':f'DES-{int(datetime.now().timestamp())}','resultados':res})

@app.route('/api/mensajeros/estado', methods=['POST'])
def mensajeros_estado():
    d = request.get_json()
    return jsonify({'ok':True,'estado':d.get('estado'),'timestamp':ts_col()})

@app.route('/api/mensajeros/novedad', methods=['POST'])
def mensajeros_novedad():
    d = request.get_json()
    if not d: return jsonify({'error':'Sin datos'}), 400
    ts = ts_col()
    res = {
        'correo': enviar_correo(EMAIL_LOGISTICA, f'⚠️ [MILO] Novedad {d.get("pedido")}',
            f"<html><body><h2 style='color:red'>Novedad</h2><p>Pedido: {d.get('pedido')}</p><p>Tipo: {d.get('tipo')}</p><p>{d.get('descripcion')}</p></body></html>"),
        'whatsapp': enviar_wa(WA_NUM_CARTERA, WA_API_KEY_CARTERA,
            f"MILO NOVEDAD\n{d.get('pedido')}\n{d.get('tipo')}\n{d.get('descripcion','')[:100]}"),
        'sheets': sheets_append(SHEET_ID_MENSAJEROS, 'Novedades',
            [ts, d.get('pedido'), d.get('tipo'), d.get('descripcion'), d.get('reportadoPor','')])
    }
    return jsonify({'ok':True,'timestamp':ts,'resultados':res})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
