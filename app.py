"""
MILO Backend - Flask en Render
Módulos: Cartera + Mensajeros
Notificaciones: Correo (SMTP) + WhatsApp (CallMeBot) + Google Sheets
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ─── CONFIGURACIÓN ─────────────────────────────────────────
# Pon estas variables en Render > Environment Variables

# Correo (Gmail con App Password)
EMAIL_ORIGEN     = os.environ.get('EMAIL_ORIGEN', 'milo@lubriandes.com')
EMAIL_PASSWORD   = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_CARTERA    = os.environ.get('EMAIL_CARTERA', 'cartera@lubriandes.com')
EMAIL_LOGISTICA  = os.environ.get('EMAIL_LOGISTICA', 'logistica@lubriandes.com')

# WhatsApp vía CallMeBot (gratis, API simple)
# Registro: https://www.callmebot.com/blog/free-api-whatsapp-messages/
WA_API_KEY_CARTERA   = os.environ.get('WA_API_KEY_CARTERA', '')
WA_NUM_CARTERA       = os.environ.get('WA_NUM_CARTERA', '+573001234567')   # Asesor de cartera
WA_API_KEY_MENS      = os.environ.get('WA_API_KEY_MENS', {})  # JSON: {"M1":"apikey1","M2":"apikey2"}
WA_NUMS_MENSAJEROS   = os.environ.get('WA_NUMS_MENSAJEROS', '{}')  # JSON: {"M1":"+573009999999"}

# Google Sheets
SHEETS_CREDS_JSON    = os.environ.get('SHEETS_CREDS_JSON', '{}')   # JSON de service account
SHEET_ID_CARTERA     = os.environ.get('SHEET_ID_CARTERA', '')
SHEET_ID_MENSAJEROS  = os.environ.get('SHEET_ID_MENSAJEROS', '')

# Parsear JSONs de env vars
try:
    _wa_keys = json.loads(WA_API_KEY_MENS) if isinstance(WA_API_KEY_MENS, str) else {}
    _wa_nums = json.loads(WA_NUMS_MENSAJEROS) if isinstance(WA_NUMS_MENSAJEROS, str) else {}
except:
    _wa_keys = {}
    _wa_nums = {}


# ─── UTILIDADES ────────────────────────────────────────────

def fmt_cop(valor):
    """Formatea número a pesos colombianos"""
    try:
        return f"${int(valor):,}".replace(',', '.')
    except:
        return str(valor)

def ts_colombia():
    """Timestamp legible en hora Colombia"""
    return datetime.now().strftime('%d/%m/%Y %H:%M')


# ─── GOOGLE SHEETS ─────────────────────────────────────────

def get_sheets_client():
    """Retorna cliente de Google Sheets autenticado"""
    try:
        creds_dict = json.loads(SHEETS_CREDS_JSON)
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f'[Sheets] Error auth: {e}')
        return None

def sheets_append(sheet_id, tab_name, row_data):
    """Agrega una fila al Google Sheet indicado"""
    try:
        gc = get_sheets_client()
        if not gc:
            return False
        sh = gc.open_by_key(sheet_id)
        try:
            ws = sh.worksheet(tab_name)
        except:
            ws = sh.add_worksheet(title=tab_name, rows=1000, cols=20)
        ws.append_row(row_data)
        return True
    except Exception as e:
        print(f'[Sheets] Error append: {e}')
        return False


# ─── CORREO ────────────────────────────────────────────────

def enviar_correo(destinatario, asunto, html_body):
    """Envía correo HTML vía Gmail SMTP"""
    if not EMAIL_PASSWORD:
        print('[Correo] Sin contraseña configurada, simulando envío')
        return True
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = asunto
        msg['From']    = EMAIL_ORIGEN
        msg['To']      = destinatario
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_ORIGEN, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ORIGEN, destinatario, msg.as_string())
        print(f'[Correo] Enviado a {destinatario}')
        return True
    except Exception as e:
        print(f'[Correo] Error: {e}')
        return False


# ─── WHATSAPP (CallMeBot) ──────────────────────────────────

def enviar_whatsapp(numero, api_key, mensaje):
    """Envía mensaje de WhatsApp vía CallMeBot"""
    if not api_key:
        print(f'[WA] Sin API key para {numero}, simulando envío')
        return True
    try:
        url = 'https://api.callmebot.com/whatsapp.php'
        params = {
            'phone': numero,
            'text': mensaje,
            'apikey': api_key
        }
        r = requests.get(url, params=params, timeout=10)
        print(f'[WA] Respuesta: {r.status_code} - {r.text[:100]}')
        return r.status_code == 200
    except Exception as e:
        print(f'[WA] Error: {e}')
        return False


# ─── TEMPLATES HTML CORREO ─────────────────────────────────

def template_cartera(datos):
    nit = datos.get('nit', '-')
    tipo = datos.get('tipo', '-')
    valor = fmt_cop(datos.get('valor', 0))
    fecha = datos.get('fecha', '-')
    obs = datos.get('observaciones', '-')
    usuario = datos.get('registradoPor', '-')
    ts = ts_colombia()
    return f"""
<html><body style="font-family:Arial,sans-serif;background:#f0f4f3;padding:20px">
<div style="max-width:520px;margin:0 auto;background:white;border-radius:14px;overflow:hidden;border:1px solid #e0e7e5">
  <div style="background:#0F6E56;color:white;padding:20px 24px">
    <h2 style="margin:0;font-size:20px">📊 MILO · Gestión de Cartera</h2>
    <p style="margin:4px 0 0;opacity:.85;font-size:13px">Antioqueña de Lubricantes · {ts}</p>
  </div>
  <div style="padding:24px">
    <table style="width:100%;border-collapse:collapse">
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">NIT Cliente</td><td style="padding:8px 0;font-weight:600;font-size:13px;border-bottom:1px solid #f0f4f3">{nit}</td></tr>
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">Tipo gestión</td><td style="padding:8px 0;font-weight:600;font-size:13px;border-bottom:1px solid #f0f4f3">{tipo}</td></tr>
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">Valor comprometido</td><td style="padding:8px 0;font-weight:700;color:#185FA5;font-size:14px;border-bottom:1px solid #f0f4f3">{valor}</td></tr>
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">Fecha compromiso</td><td style="padding:8px 0;font-weight:600;font-size:13px;border-bottom:1px solid #f0f4f3">{fecha}</td></tr>
      <tr><td style="padding:8px 0;color:#666;font-size:13px" colspan="2">Observaciones</td></tr>
      <tr><td colspan="2" style="padding:8px 12px;background:#f8faf9;border-radius:8px;font-size:13px;color:#444">{obs}</td></tr>
    </table>
    <p style="margin:16px 0 0;font-size:12px;color:#aaa">Registrado por: {usuario} · MILO Plataforma LubriAndes</p>
  </div>
</div></body></html>"""

def template_mensajero_asignacion(datos):
    pedido = datos.get('pedido', '-')
    cliente = datos.get('cliente', '-')
    dir_ = datos.get('direccion', '-')
    mensajero = datos.get('mensajero', '-')
    fecha = datos.get('fecha', '-')
    obs = datos.get('observaciones', '')
    ts = ts_colombia()
    return f"""
<html><body style="font-family:Arial,sans-serif;background:#f0f4f3;padding:20px">
<div style="max-width:520px;margin:0 auto;background:white;border-radius:14px;overflow:hidden;border:1px solid #e0e7e5">
  <div style="background:#0F6E56;color:white;padding:20px 24px">
    <h2 style="margin:0;font-size:20px">🚚 MILO · Nuevo Despacho Asignado</h2>
    <p style="margin:4px 0 0;opacity:.85;font-size:13px">Antioqueña de Lubricantes · {ts}</p>
  </div>
  <div style="padding:24px">
    <table style="width:100%;border-collapse:collapse">
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">Pedido HGI</td><td style="padding:8px 0;font-weight:700;color:#0F6E56;font-size:14px;border-bottom:1px solid #f0f4f3">{pedido}</td></tr>
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">Cliente</td><td style="padding:8px 0;font-weight:600;font-size:13px;border-bottom:1px solid #f0f4f3">{cliente}</td></tr>
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">Dirección entrega</td><td style="padding:8px 0;font-weight:600;font-size:13px;border-bottom:1px solid #f0f4f3">{dir_}</td></tr>
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">Mensajero</td><td style="padding:8px 0;font-weight:600;font-size:13px;border-bottom:1px solid #f0f4f3">{mensajero}</td></tr>
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">Fecha estimada</td><td style="padding:8px 0;font-weight:600;font-size:13px;border-bottom:1px solid #f0f4f3">{fecha}</td></tr>
      {'<tr><td colspan="2" style="padding:8px 12px;background:#f8faf9;border-radius:8px;font-size:13px;color:#444;margin-top:8px">'+obs+'</td></tr>' if obs else ''}
    </table>
  </div>
</div></body></html>"""

def template_novedad(datos):
    pedido = datos.get('pedido', '-')
    tipo = datos.get('tipo', '-')
    desc = datos.get('descripcion', '-')
    gps = datos.get('gps') or {}
    gps_str = f"{gps.get('lat','-')}, {gps.get('lng','-')}" if gps else 'No disponible'
    ts = ts_colombia()
    return f"""
<html><body style="font-family:Arial,sans-serif;background:#f0f4f3;padding:20px">
<div style="max-width:520px;margin:0 auto;background:white;border-radius:14px;overflow:hidden;border:1px solid #e0e7e5">
  <div style="background:#E24B4A;color:white;padding:20px 24px">
    <h2 style="margin:0;font-size:20px">⚠️ MILO · Novedad en Despacho</h2>
    <p style="margin:4px 0 0;opacity:.85;font-size:13px">{ts}</p>
  </div>
  <div style="padding:24px">
    <table style="width:100%;border-collapse:collapse">
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">Pedido</td><td style="padding:8px 0;font-weight:700;color:#E24B4A;font-size:14px;border-bottom:1px solid #f0f4f3">{pedido}</td></tr>
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">Tipo novedad</td><td style="padding:8px 0;font-weight:600;font-size:13px;border-bottom:1px solid #f0f4f3">{tipo}</td></tr>
      <tr><td style="padding:8px 0;color:#666;font-size:13px;border-bottom:1px solid #f0f4f3">GPS mensajero</td><td style="padding:8px 0;font-size:12px;color:#888;border-bottom:1px solid #f0f4f3">{gps_str}</td></tr>
    </table>
    <div style="margin-top:12px;padding:12px;background:#FCEBEB;border-radius:8px;border-left:4px solid #E24B4A">
      <p style="font-size:13px;color:#A32D2D;margin:0">{desc}</p>
    </div>
  </div>
</div></body></html>"""


# ─── ENDPOINTS CARTERA ─────────────────────────────────────

@app.route('/api/cartera/gestion', methods=['POST'])
def cartera_gestion():
    """Registra gestión de cobro + notifica correo + WhatsApp + Sheets"""
    datos = request.get_json()
    if not datos:
        return jsonify({'error': 'Sin datos'}), 400

    nit      = datos.get('nit', '-')
    tipo     = datos.get('tipo', '-')
    valor    = datos.get('valor', 0)
    obs      = datos.get('observaciones', '-')
    fecha    = datos.get('fecha', '-')
    usuario  = datos.get('registradoPor', '-')
    ts       = ts_colombia()

    resultados = {}

    # 1. CORREO al asesor de cartera
    html = template_cartera(datos)
    asunto = f'[MILO] Gestión de cartera · NIT {nit} · {tipo}'
    resultados['correo'] = enviar_correo(EMAIL_CARTERA, asunto, html)

    # 2. WHATSAPP al asesor de cartera
    msg_wa = (
        f"🏦 *MILO - Gestión Cartera*\n"
        f"NIT: {nit}\n"
        f"Tipo: {tipo}\n"
        f"Valor: {fmt_cop(valor)}\n"
        f"Fecha: {fecha}\n"
        f"Obs: {obs[:100]}\n"
        f"Por: {usuario} · {ts}"
    )
    resultados['whatsapp'] = enviar_whatsapp(WA_NUM_CARTERA, WA_API_KEY_CARTERA, msg_wa)

    # 3. GOOGLE SHEETS
    fila = [ts, nit, tipo, fmt_cop(valor), fecha, obs, usuario,
            datos.get('gps', {}).get('lat', '') if datos.get('gps') else '',
            datos.get('gps', {}).get('lng', '') if datos.get('gps') else '']
    resultados['sheets'] = sheets_append(SHEET_ID_CARTERA, 'Gestiones', fila)

    return jsonify({
        'ok': True,
        'mensaje': 'Gestión registrada y notificaciones enviadas',
        'resultados': resultados,
        'timestamp': ts
    })


@app.route('/api/cartera/historial', methods=['GET'])
def cartera_historial():
    """Retorna historial de gestiones desde Sheets"""
    try:
        gc = get_sheets_client()
        if not gc:
            return jsonify([])
        sh = gc.open_by_key(SHEET_ID_CARTERA)
        ws = sh.worksheet('Gestiones')
        rows = ws.get_all_records()
        return jsonify(rows)
    except Exception as e:
        print(f'[Cartera historial] Error: {e}')
        return jsonify([])


# ─── ENDPOINTS MENSAJEROS ──────────────────────────────────

@app.route('/api/mensajeros/despachos', methods=['GET'])
def mensajeros_despachos():
    """Retorna despachos activos del día desde Sheets"""
    try:
        gc = get_sheets_client()
        if not gc:
            return jsonify([])
        sh = gc.open_by_key(SHEET_ID_MENSAJEROS)
        ws = sh.worksheet('Despachos')
        rows = ws.get_all_records()
        # Filtrar solo del día actual
        hoy = datetime.now().strftime('%d/%m/%Y')
        activos = [r for r in rows if r.get('Estado','') != 'entregado' or
                   r.get('Fecha','').startswith(hoy)]
        return jsonify(activos)
    except Exception as e:
        print(f'[Mensajeros despachos] Error: {e}')
        return jsonify([])


@app.route('/api/mensajeros/asignar', methods=['POST'])
def mensajeros_asignar():
    """Asigna despacho a mensajero + notifica correo + WhatsApp + Sheets"""
    datos = request.get_json()
    if not datos:
        return jsonify({'error': 'Sin datos'}), 400

    pedido    = datos.get('pedido', '-')
    cliente   = datos.get('cliente', '-')
    dir_      = datos.get('direccion', '-')
    mensajero = datos.get('mensajero', '-')
    mens_id   = datos.get('mensajeroId', '')
    fecha     = datos.get('fecha', '-')
    obs       = datos.get('observaciones', '')
    ts        = ts_colombia()

    resultados = {}

    # 1. CORREO a logística
    html = template_mensajero_asignacion(datos)
    asunto = f'[MILO] Despacho asignado · {pedido} → {mensajero}'
    resultados['correo_logistica'] = enviar_correo(EMAIL_LOGISTICA, asunto, html)

    # 2. WHATSAPP al mensajero asignado
    wa_key = _wa_keys.get(mens_id, '')
    wa_num = _wa_nums.get(mens_id, '')
    msg_wa = (
        f"🚚 *MILO - Nuevo Despacho*\n"
        f"Pedido: *{pedido}*\n"
        f"Cliente: {cliente}\n"
        f"Dirección: {dir_}\n"
        f"Fecha entrega: {fecha}\n"
        f"{('Obs: ' + obs) if obs else ''}\n"
        f"¡Confirma recepción!"
    )
    if wa_num:
        resultados['whatsapp_mensajero'] = enviar_whatsapp(wa_num, wa_key, msg_wa)
    else:
        resultados['whatsapp_mensajero'] = False

    # 3. GOOGLE SHEETS
    fila = [ts, pedido, cliente, dir_, mensajero, fecha, 'pendiente', obs, '']
    resultados['sheets'] = sheets_append(SHEET_ID_MENSAJEROS, 'Despachos', fila)

    return jsonify({
        'ok': True,
        'mensaje': 'Despacho asignado y notificaciones enviadas',
        'resultados': resultados,
        'id': 'DES-' + str(int(datetime.now().timestamp())),
        'timestamp': ts
    })


@app.route('/api/mensajeros/estado', methods=['POST'])
def mensajeros_estado():
    """Actualiza estado de despacho + notifica si es entrega"""
    datos = request.get_json()
    if not datos:
        return jsonify({'error': 'Sin datos'}), 400

    despacho_id  = datos.get('id', '-')
    nuevo_estado = datos.get('estado', '-')
    gps          = datos.get('gps', {})
    ts           = ts_colombia()

    resultados = {}

    # Actualizar en Sheets
    try:
        gc = get_sheets_client()
        if gc:
            sh = gc.open_by_key(SHEET_ID_MENSAJEROS)
            ws = sh.worksheet('Despachos')
            # Buscar la fila por id o pedido
            cell = ws.find(despacho_id)
            if cell:
                ws.update_cell(cell.row, 7, nuevo_estado)  # Col 7 = Estado
                ws.update_cell(cell.row, 9, ts)
            resultados['sheets'] = True
    except Exception as e:
        print(f'[Estado] Error Sheets: {e}')
        resultados['sheets'] = False

    # Si es entrega confirmada, notificar
    if nuevo_estado == 'entregado':
        msg = f"✅ *MILO - Entrega Confirmada*\nDespacho: {despacho_id}\nHora: {ts}"
        resultados['correo'] = enviar_correo(EMAIL_LOGISTICA,
            f'[MILO] Entrega confirmada · {despacho_id}',
            f'<p style="font-family:Arial">{msg.replace(chr(10),"<br>")}</p>')

    return jsonify({'ok': True, 'estado': nuevo_estado, 'timestamp': ts, 'resultados': resultados})


@app.route('/api/mensajeros/novedad', methods=['POST'])
def mensajeros_novedad():
    """Reporta novedad de despacho + notifica correo + WhatsApp + Sheets"""
    datos = request.get_json()
    if not datos:
        return jsonify({'error': 'Sin datos'}), 400

    pedido = datos.get('pedido', '-')
    tipo   = datos.get('tipo', '-')
    desc   = datos.get('descripcion', '-')
    ts     = ts_colombia()

    resultados = {}

    # 1. CORREO urgente a logística
    html = template_novedad(datos)
    asunto = f'⚠️ [MILO] NOVEDAD · {pedido} · {tipo}'
    resultados['correo'] = enviar_correo(EMAIL_LOGISTICA, asunto, html)

    # 2. WHATSAPP a cartera/logística
    msg_wa = (f"⚠️ *MILO - NOVEDAD DESPACHO*\n"
              f"Pedido: *{pedido}*\nTipo: {tipo}\n{desc[:120]}\n{ts}")
    resultados['whatsapp'] = enviar_whatsapp(WA_NUM_CARTERA, WA_API_KEY_CARTERA, msg_wa)

    # 3. SHEETS
    gps = datos.get('gps', {}) or {}
    fila = [ts, pedido, tipo, desc, datos.get('reportadoPor', '-'),
            gps.get('lat', ''), gps.get('lng', '')]
    resultados['sheets'] = sheets_append(SHEET_ID_MENSAJEROS, 'Novedades', fila)

    return jsonify({'ok': True, 'timestamp': ts, 'resultados': resultados})


# ─── PROXY HGI (evita CORS del navegador) ─────────────────

HGI_BASE = 'https://900405097.hginet.com.co/Api'

@app.route('/hgi/token', methods=['POST'])
def hgi_token():
    """Proxy para obtener token HGI — evita bloqueo CORS"""
    datos = request.get_json()
    usuario = datos.get('username', '')
    clave   = datos.get('password', '')
    try:
        r = requests.post(
            f'{HGI_BASE}/token',
            data=f'grant_type=password&username={usuario}&password={clave}',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=15,
            verify=False
        )
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/hgi/<path:endpoint>', methods=['GET', 'POST'])
def hgi_proxy(endpoint):
    """Proxy genérico para todas las llamadas a HGI"""
    token = request.headers.get('X-HGI-Token', '')
    headers = {'Authorization': f'Bearer {token}'}
    try:
        if request.method == 'GET':
            r = requests.get(
                f'{HGI_BASE}/{endpoint}',
                params=request.args,
                headers=headers,
                timeout=15,
                verify=False
            )
        else:
            r = requests.post(
                f'{HGI_BASE}/{endpoint}',
                json=request.get_json(),
                headers=headers,
                timeout=15,
                verify=False
            )
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── HEALTH CHECK ──────────────────────────────────────────
@app.route('/', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'app': 'MILO Backend', 'version': '2.0',
                    'modulos': ['pedidos', 'cartera', 'mensajeros']})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
