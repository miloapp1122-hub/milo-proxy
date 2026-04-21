from flask import Flask, request, jsonify
from flask_cors import CORS
import requests, threading, time, urllib3, json, os, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import base64

urllib3.disable_warnings()
app = Flask(__name__)
CORS(app, origins="*")

HGI_BASE     = 'https://900405097.hginet.com.co/Api'
HGI_USUARIO  = '98711025'
HGI_CLAVE    = 'C9871'
HGI_COMPANIA = '1'
HGI_EMPRESA  = '1'
TOKEN_FILE   = '/tmp/hgi_token.txt'

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

_token = os.environ.get('HGI_TOKEN_INICIAL', None)
_token_lock = threading.Lock()
if _token:
    print(f'[MILO] Token inicial cargado desde env var')

def jwt_exp(token):
    """Obtiene el tiempo de expiración del JWT"""
    try:
        payload = token.split('.')[1]
        payload += '=' * (4 - len(payload) % 4)
        data = json.loads(base64.b64decode(payload))
        return data.get('exp', 0)
    except:
        return 0

def token_valido(token):
    """Verifica si el token no ha expirado"""
    if not token:
        return False
    exp = jwt_exp(token)
    return exp > time.time() + 60  # 60s de margen

def cargar_token_disco():
    """Carga token guardado en disco"""
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                tok = f.read().strip()
            if token_valido(tok):
                print(f'[MILO] Token cargado desde disco ✅')
                return tok
    except:
        pass
    return None

def guardar_token_disco(tok):
    """Guarda token en disco"""
    try:
        with open(TOKEN_FILE, 'w') as f:
            f.write(tok)
    except:
        pass

def autenticar_hgi():
    """Obtiene token de HGI"""
    url = f"{HGI_BASE}/Autenticar?usuario={HGI_USUARIO}&clave={HGI_CLAVE}&cod_compania={HGI_COMPANIA}&cod_empresa={HGI_EMPRESA}"
    r = requests.get(url, timeout=15, verify=False)
    data = r.json()
    return data.get('JwtToken'), data.get('Error', {})

def renovar_token():
    global _token
    # Intentar cargar desde disco primero
    tok_disco = cargar_token_disco()
    if tok_disco:
        with _token_lock:
            _token = tok_disco
    while True:
        try:
            jwt, error = autenticar_hgi()
            if jwt:
                with _token_lock:
                    _token = jwt
                guardar_token_disco(jwt)
                exp = jwt_exp(jwt)
                print(f'[MILO] ✅ Token renovado! Expira: {datetime.fromtimestamp(exp).strftime("%H:%M")}')
                # Dormir hasta 2 min antes de expirar
                sleep_time = max(60, (exp - time.time()) - 120)
                print(f'[MILO] Próxima renovación en {int(sleep_time/60)} min')
                time.sleep(sleep_time)
            elif error.get('Codigo') == 3:
                # Token vigente en HGI — intentar usar el que tenemos en disco
                print(f'[MILO] Token vigente en HGI')
                with _token_lock:
                    tok_actual = _token
                if not tok_actual:
                    tok_disco = cargar_token_disco()
                    if tok_disco and token_valido(tok_disco):
                        with _token_lock:
                            _token = tok_disco
                        print(f'[MILO] ✅ Usando token del disco')
                    else:
                        print(f'[MILO] Sin token válido - esperando 60s...')
                        time.sleep(60)
                else:
                    if token_valido(tok_actual):
                        exp = jwt_exp(tok_actual)
                        mins = int((exp - time.time()) / 60)
                        print(f'[MILO] ✅ Token actual válido por {mins} min más')
                        time.sleep(60)
                    else:
                        print(f'[MILO] Token expirado - reintentando en 30s...')
                        with _token_lock:
                            _token = None
                        time.sleep(30)
            else:
                print(f'[MILO] Error: {error}')
                time.sleep(30)
        except Exception as e:
            print(f'[MILO] Error auth: {e}')
            time.sleep(30)

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
        print(f'[Correo] {e}')
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
        print(f'[Sheets] {e}')
        return False

@app.route('/', methods=['GET'])
def health():
    with _token_lock:
        tok = _token
    valido = token_valido(tok) if tok else False
    mins = int((jwt_exp(tok) - time.time()) / 60) if valido else 0
    return jsonify({'status': 'ok', 'app': 'MILO Backend', 'version': '2.0',
                    'token': valido, 'expira_en': f'{mins} min' if valido else 'N/A'})

@app.route('/ping', methods=['GET'])
def ping():
    with _token_lock:
        tok = _token
    return jsonify({'pong': True, 'ts': ts_col(), 'token': token_valido(tok) if tok else False})

@app.route('/hgi/token', methods=['POST', 'OPTIONS'])
def hgi_token():
    global _token
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    with _token_lock:
        tok = _token
    if tok and token_valido(tok):
        print(f'[Login] ✅ Token entregado al frontend')
        return jsonify({'JwtToken': tok, 'access_token': tok}), 200
    else:
        print(f'[Login] Token no disponible aún')
        return jsonify({'error': 'Token no disponible, espera 30s y reintenta'}), 503

@app.route('/hgi/<path:endpoint>', methods=['GET', 'POST', 'OPTIONS'])
def hgi_proxy(endpoint):
    global _token
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    with _token_lock:
        tok = _token
    if not tok or not token_valido(tok):
        return jsonify({'error': 'Sin token válido'}), 401
    headers = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}
    params = dict(request.args)
    url = f'{HGI_BASE}/{endpoint}'
    try:
        if request.method == 'POST':
            r = requests.post(url, json=request.get_json(), headers=headers, params=params, timeout=30, verify=False)
        else:
            # Construir query string - decodificar %2A a * para HGI
            from urllib.parse import unquote
            qs = '&'.join(f'{k}={unquote(str(v))}' for k,v in params.items())
            full_url = f'{url}?{qs}' if qs else url
            r = requests.get(full_url, headers=headers, timeout=30, verify=False)
        if r.status_code == 401:
            with _token_lock:
                _token = None
        try: return jsonify(r.json()), r.status_code
        except: return r.text, r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cartera/gestion', methods=['POST'])
def cartera_gestion():
    d = request.get_json()
    if not d: return jsonify({'error': 'Sin datos'}), 400
    ts = ts_col()
    res = {
        'correo': enviar_correo(EMAIL_CARTERA, f'[MILO] Cartera · {d.get("nit","-")}',
            f"<html><body><h2>Gestión Cartera</h2><p>NIT: {d.get('nit')}</p><p>Tipo: {d.get('tipo')}</p><p>Valor: {fmt_cop(d.get('valor',0))}</p><p>Obs: {d.get('observaciones')}</p></body></html>"),
        'whatsapp': enviar_wa(WA_NUM_CARTERA, WA_API_KEY_CARTERA,
            f"MILO Cartera\nNIT: {d.get('nit')}\nTipo: {d.get('tipo')}\nValor: {fmt_cop(d.get('valor',0))}"),
        'sheets': sheets_append(SHEET_ID_CARTERA, 'Gestiones',
            [ts, d.get('nit'), d.get('tipo'), fmt_cop(d.get('valor',0)), d.get('fecha'), d.get('observaciones'), d.get('registradoPor')])
    }
    return jsonify({'ok': True, 'resultados': res, 'timestamp': ts})

@app.route('/api/mensajeros/despachos', methods=['GET'])
def mensajeros_despachos():
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
        creds_dict = json.loads(SHEETS_CREDS_JSON)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        gc = gspread.authorize(creds)
        return jsonify(gc.open_by_key(SHEET_ID_MENSAJEROS).worksheet('Despachos').get_all_records())
    except: return jsonify([])

@app.route('/api/mensajeros/asignar', methods=['POST'])
def mensajeros_asignar():
    d = request.get_json()
    if not d: return jsonify({'error': 'Sin datos'}), 400
    ts = ts_col()
    mens_id = d.get('mensajeroId', '')
    res = {
        'correo': enviar_correo(EMAIL_LOGISTICA, f'[MILO] Despacho {d.get("pedido")}',
            f"<html><body><h2>Despacho</h2><p>Pedido: {d.get('pedido')}</p><p>Cliente: {d.get('cliente')}</p><p>Mensajero: {d.get('mensajero')}</p></body></html>"),
        'whatsapp': enviar_wa(_wa_nums.get(mens_id,''), _wa_keys.get(mens_id,''),
            f"MILO Despacho\n{d.get('pedido')}\n{d.get('cliente')}\n{d.get('direccion')}") if _wa_nums.get(mens_id) else False,
        'sheets': sheets_append(SHEET_ID_MENSAJEROS, 'Despachos',
            [ts, d.get('pedido'), d.get('cliente'), d.get('direccion'), d.get('mensajero'), d.get('fecha'), 'pendiente', d.get('observaciones','')])
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
        'correo': enviar_correo(EMAIL_LOGISTICA, f'⚠️ [MILO] Novedad {d.get("pedido")}',
            f"<html><body><h2 style='color:red'>Novedad</h2><p>{d.get('pedido')}</p><p>{d.get('tipo')}</p><p>{d.get('descripcion')}</p></body></html>"),
        'whatsapp': enviar_wa(WA_NUM_CARTERA, WA_API_KEY_CARTERA,
            f"MILO NOVEDAD\n{d.get('pedido')}\n{d.get('tipo')}\n{d.get('descripcion','')[:100]}"),
        'sheets': sheets_append(SHEET_ID_MENSAJEROS, 'Novedades',
            [ts, d.get('pedido'), d.get('tipo'), d.get('descripcion'), d.get('reportadoPor','')])
    }
    return jsonify({'ok': True, 'timestamp': ts, 'resultados': res})


# ─── ENDPOINTS DEDICADOS HGI ──────────────────────────────
@app.route('/api/vendedores', methods=['GET'])
def get_vendedores():
    global _token
    with _token_lock:
        tok = _token
    if not tok or not token_valido(tok):
        return jsonify({'error': 'Sin token'}), 401
    try:
        headers = {'Authorization': f'Bearer {tok}'}
        # Asesores Antioqueña de Lubricantes
        vendedores = [
            {"Codigo":"01","Nombre":"SAUL GOMEZ","Estado":1},
            {"Codigo":"02","Nombre":"JESSICA PAOLA ZAPATA SALAZAR","Estado":1},
            {"Codigo":"03","Nombre":"HUGO ALEJANDRO PALACIO LENIS","Estado":1},
            {"Codigo":"04","Nombre":"MARIA FERNANDA PIEDRAHITA","Estado":1},
            {"Codigo":"05","Nombre":"ABOGADO","Estado":1},
            {"Codigo":"06","Nombre":"ALEXANDER GALEANO","Estado":1},
            {"Codigo":"07","Nombre":"JORGE ARTURO CORREA RESTREPO","Estado":1},
            {"Codigo":"08","Nombre":"ROMAN ALCIDES MESA MESA","Estado":1},
            {"Codigo":"09","Nombre":"SANTIAGO BAQUERO SANCHEZ","Estado":1},
            {"Codigo":"10","Nombre":"CLIENTES NO VISITADOS","Estado":1},
            {"Codigo":"11","Nombre":"SEBASTIAN PATIÑO ALVAREZ","Estado":1},
            {"Codigo":"12","Nombre":"TATIANA MONTOYA","Estado":1},
            {"Codigo":"13","Nombre":"HERMAN LADINO","Estado":1},
            {"Codigo":"14","Nombre":"GARCIA GARCIA GUSTAVO ADOLFO","Estado":1},
            {"Codigo":"15","Nombre":"CRISTIAN VELILLA","Estado":1},
            {"Codigo":"16","Nombre":"OSCAR FABIAN PATIÑO VILLADA","Estado":1},
            {"Codigo":"17","Nombre":"YOINER POMARES","Estado":1},
            {"Codigo":"18","Nombre":"HECTOR BUITRAGO","Estado":1},
            {"Codigo":"20","Nombre":"JEFE DE MOSTRADORES","Estado":1},
            {"Codigo":"21","Nombre":"JOSE RICARDO ORTIZ VALENCIA","Estado":1},
            {"Codigo":"22","Nombre":"JUAN DIEGO BENITEZ PINEDA","Estado":1},
            {"Codigo":"23","Nombre":"SEBASTIAN ARIAS SALDARRIAGA","Estado":1},
            {"Codigo":"24","Nombre":"PABLO ANDRES CANO CARDONA","Estado":1},
            {"Codigo":"25","Nombre":"CARLOS ANDRES RODRIGUEZ ARANGO","Estado":1},
            {"Codigo":"26","Nombre":"FELIPE GUTIERREZ","Estado":1},
            {"Codigo":"27","Nombre":"ABOGADO","Estado":1},
            {"Codigo":"28","Nombre":"SANTIAGO ANTONIO FLOREZ GOMEZ","Estado":1},
            {"Codigo":"29","Nombre":"DIANA MARIA LOAIZA LOPEZ","Estado":1},
            {"Codigo":"30","Nombre":"LADY YOHANA BERMUDEZ TOVAR","Estado":1},
            {"Codigo":"31","Nombre":"VACANTE RIONEGRO S","Estado":1},
            {"Codigo":"32","Nombre":"CESAR AUGUSTO ARANGO RIVERA","Estado":1},
            {"Codigo":"33","Nombre":"HERMAN ARIEL LADINO JARAMILLO","Estado":1},
            {"Codigo":"34","Nombre":"SEBASTIAN JIMENEZ MUÑOZ","Estado":1},
            {"Codigo":"35","Nombre":"JUAN FRANCISCO BENITEZ PINEDA","Estado":1},
            {"Codigo":"36","Nombre":"FABIAN PATIÑO","Estado":1},
            {"Codigo":"37","Nombre":"STEFANNYA LOAIZA CASTAÑO","Estado":1},
            {"Codigo":"38","Nombre":"JHOANNA BERMUDEZ","Estado":1},
            {"Codigo":"39","Nombre":"CARLOS SAENZ","Estado":1},
            {"Codigo":"40","Nombre":"CARLOS MARIO BENITEZ PINEDA","Estado":1},
            {"Codigo":"50","Nombre":"EDWAR ARBOLEDA","Estado":1},
            {"Codigo":"51","Nombre":"JUAN ESTEBAN ZAPATA","Estado":1},
            {"Codigo":"52","Nombre":"ANDRES VALENCIA","Estado":1},
            {"Codigo":"53","Nombre":"JOSE M CANO","Estado":1},
            {"Codigo":"54","Nombre":"CAMILO HENAO","Estado":1},
            {"Codigo":"55","Nombre":"JOHAN RAMIREZ","Estado":1},
            {"Codigo":"56","Nombre":"HUGO BUSTAMANTE","Estado":1},
            {"Codigo":"8","Nombre":"GALEANO ZAPATA ANDRES FELIPE","Estado":1},
        ]
        return jsonify(vendedores), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/clientes', methods=['GET'])
def get_clientes():
    global _token
    q = request.args.get('q', '')
    with _token_lock:
        tok = _token
    if not tok or not token_valido(tok):
        return jsonify({'error': 'Sin token'}), 401
    try:
        headers = {'Authorization': f'Bearer {tok}'}
        r = requests.get(f'{HGI_BASE}/Terceros/Busqueda',
            params={'filtro_busqueda': q},
            headers=headers, timeout=20, verify=False)
        print(f'[Clientes] Status: {r.status_code}')
        print(f'[Clientes] Respuesta: {r.text[:200]}')
        if r.text:
            return jsonify(r.json()), r.status_code
        return jsonify([]), 200
    except Exception as e:
        print(f'[Clientes] ERROR: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/cartera', methods=['GET'])
def get_cartera():
    global _token
    nit = request.args.get('nit', '*')
    with _token_lock:
        tok = _token
    if not tok or not token_valido(tok):
        return jsonify({'error': 'Sin token'}), 401
    try:
        headers = {'Authorization': f'Bearer {tok}'}
        url = f'{HGI_BASE}/Cartera/Obtener?anyo=*&periodo=*&codigo_tercero={nit}&codigo_local=0&tipo_cartera=0&grupo=0&codigo_clase=0'
        r = requests.get(url, headers=headers, timeout=30, verify=False)
        print(f'[Cartera] Status: {r.status_code}')
        print(f'[Cartera] Bytes: {len(r.text)}')
        if r.text:
            return jsonify(r.json()), r.status_code
        return jsonify([]), 200
    except Exception as e:
        print(f'[Cartera] ERROR: {e}')
        return jsonify({'error': str(e)}), 500

# ─── ARRANQUE ──────────────────────────────────────────────
_thread_iniciado = False

@app.before_request
def iniciar_thread():
    global _thread_iniciado
    if not _thread_iniciado:
        _thread_iniciado = True
        t = threading.Thread(target=renovar_token, daemon=True)
        t.start()
        print('[MILO] Thread iniciado')

if __name__ == '__main__':
    t = threading.Thread(target=renovar_token, daemon=True)
    t.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

@app.route('/api/productos', methods=['GET'])
def get_productos():
    global _token
    q = request.args.get('q', '*')
    with _token_lock:
        tok = _token
    if not tok or not token_valido(tok):
        return jsonify({'error': 'Sin token'}), 401
    try:
        headers = {'Authorization': f'Bearer {tok}'}
        r = requests.get(
            f'{HGI_BASE}/Productos/ObtenerProductos',
            params={'codigo_producto': q, 'movil': '1', 'ecommerce': '*',
                    'estado': '1', 'kardex': '*', 'incluir_foto': 'false'},
            headers=headers, timeout=30, verify=False)
        print(f'[Productos] Status: {r.status_code}')
        if r.text:
            return jsonify(r.json()), r.status_code
        return jsonify({'error': 'Sin respuesta', 'status': r.status_code}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500
