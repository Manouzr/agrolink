from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import json
import os
from functools import wraps
import pyotp
import qrcode
from io import BytesIO
import secrets

app = Flask(__name__, 
            template_folder='templates',
            static_folder='static',
            static_url_path='/static')

# Configuration de la session
app.config.update(
    SECRET_KEY=secrets.token_hex(32),
    SESSION_COOKIE_SECURE=False,  # Mettre à True en production avec HTTPS
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=1800  # 30 minutes
)

# Création du dossier data s'il n'existe pas
if not os.path.exists('data'):
    os.makedirs('data')

# Chemin vers le fichier JSON des utilisateurs
USERS_FILE = 'data/users.json'

# Création du fichier users.json s'il n'existe pas
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w') as f:
        json.dump({"users": []}, f)

def generate_totp_secret():
    """Génère une clé secrète pour TOTP"""
    return pyotp.random_base32()

def generate_totp_uri(secret, email):
    """Génère l'URI pour le QR code"""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name="AgroLink")

def verify_totp(secret, token):
    """Vérifie un token TOTP"""
    totp = pyotp.TOTP(secret)
    return totp.verify(token)

def load_users():
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter pour accéder à cette page.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sign-up', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        name = request.form.get('name')
        
        if not email or not password or not name:
            flash('Tous les champs sont requis.')
            return redirect(url_for('signup'))
        
        users_data = load_users()
        
        # Vérifier si l'email existe déjà
        if any(user['email'] == email for user in users_data['users']):
            flash('Cet email est déjà utilisé.')
            return redirect(url_for('signup'))
        
        try:
            # Générer une clé secrète pour 2FA
            totp_secret = generate_totp_secret()
            
            # Ajouter le nouvel utilisateur
            new_user = {
                'id': len(users_data['users']) + 1,
                'name': name,
                'email': email,
                'password': password,  # En production, utilisez le hachage du mot de passe
                'totp_secret': totp_secret,
                'totp_enabled': False
            }
            
            # Ajouter l'utilisateur et sauvegarder
            users_data['users'].append(new_user)
            save_users(users_data)
            
            # Configurer la session
            session.clear()
            session['setup_2fa_user_id'] = new_user['id']
            session['_fresh'] = True
            
            # Rediriger vers la configuration 2FA
            return redirect(url_for('setup_2fa'))
            
        except Exception as e:
            print(f"Erreur lors de la création de l'utilisateur: {e}")
            flash('Une erreur est survenue lors de la création du compte.')
            return redirect(url_for('signup'))
    
    return render_template('sign-up.html')

@app.route('/setup-2fa')
def setup_2fa():
    # Vérifier la session
    if '_fresh' not in session or not session.get('_fresh'):
        flash('Session expirée. Veuillez vous inscrire à nouveau.')
        return redirect(url_for('signup'))
    
    user_id = session.get('setup_2fa_user_id')
    if not user_id:
        flash('Veuillez vous inscrire d\'abord.')
        return redirect(url_for('signup'))
    
    try:
        users_data = load_users()
        user = next((user for user in users_data['users'] if user['id'] == user_id), None)
        
        if not user:
            session.clear()
            flash('Utilisateur non trouvé.')
            return redirect(url_for('signup'))
        
        if user['totp_enabled']:
            flash('2FA déjà configuré.')
            return redirect(url_for('login'))
        
        # Générer l'URI TOTP
        totp_uri = generate_totp_uri(user['totp_secret'], user['email'])
        qr_code_url = url_for('qr_code', secret=user['totp_secret'], email=user['email'])
        return render_template('setup-2fa.html', totp_uri=totp_uri, qr_code_url=qr_code_url)
        
    except Exception as e:
        print(f"Erreur lors de la configuration 2FA: {e}")
        flash('Une erreur est survenue lors de la configuration 2FA.')
        return redirect(url_for('signup'))

@app.route('/verify-2fa', methods=['POST'])
def verify_2fa():
    if 'setup_2fa_user_id' not in session:
        flash('Session expirée.')
        return redirect(url_for('signup'))
        
    token = request.form.get('token')
    if not token:
        flash('Code requis.')
        return redirect(url_for('setup_2fa'))
        
    users_data = load_users()
    user = next((user for user in users_data['users'] if user['id'] == session['setup_2fa_user_id']), None)
    
    if not user:
        flash('Utilisateur non trouvé.')
        return redirect(url_for('signup'))
        
    totp = pyotp.TOTP(user['totp_secret'])
    if totp.verify(token):
        # Activer 2FA pour l'utilisateur
        user['totp_enabled'] = True
        save_users(users_data)
        
        # Connecter l'utilisateur
        session.clear()
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        flash('2FA configuré avec succès!')
        return redirect(url_for('dashboard'))
    else:
        flash('Code invalide.')
        return redirect(url_for('setup_2fa'))

@app.route('/verify-login', methods=['GET', 'POST'])
def verify_login():
    if request.method == 'POST':
        email = session.get('login_email')
        temp_user_id = session.get('temp_user_id')
        token = request.form.get('token')
        
        if not email or not token or not temp_user_id:
            flash('Session expirée ou données manquantes.')
            return redirect(url_for('login'))
            
        users_data = load_users()
        user = next((user for user in users_data['users'] if user['id'] == temp_user_id and user['email'] == email), None)
        
        if not user:
            flash('Utilisateur non trouvé.')
            return redirect(url_for('login'))
            
        totp = pyotp.TOTP(user['totp_secret'])
        if totp.verify(token):
            # Authentification réussie
            session.clear()
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            flash('Connexion réussie!')
            return redirect(url_for('dashboard'))
        else:
            flash('Code 2FA invalide.')
            return redirect(url_for('verify_login'))
            
    return render_template('verify-login.html') 

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Email et mot de passe requis.')
            return redirect(url_for('login'))
            
        users_data = load_users()
        user = next((user for user in users_data['users'] if user['email'] == email), None)
        
        if not user or user['password'] != password:
            flash('Email ou mot de passe incorrect.')
            return redirect(url_for('login'))
            
        if user['totp_enabled']:
            # Stocker l'email et l'ID pour la vérification 2FA
            session['login_email'] = email
            session['temp_user_id'] = user['id']  # Stockage temporaire de l'ID
            return redirect(url_for('verify_login'))
        else:
            # Pas de 2FA, connexion directe
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            flash('Connexion réussie!')
            return redirect(url_for('dashboard'))
            
    return render_template('sign-in.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email')
        token = request.form.get('token')
        new_password = request.form.get('new_password')
        
        users_data = load_users()
        user = next((user for user in users_data['users'] if user['email'] == email), None)
        
        if not user:
            flash('Aucun compte associé à cet email.')
            return redirect(url_for('reset_password'))
        
        if not verify_totp(user['totp_secret'], token):
            flash('Code d\'authentification incorrect.')
            return redirect(url_for('reset_password'))
        
        # Mettre à jour le mot de passe
        user_index = next(i for i, u in enumerate(users_data['users']) if u['id'] == user['id'])
        users_data['users'][user_index]['password'] = new_password
        save_users(users_data)
        
        flash('Votre mot de passe a été réinitialisé avec succès.')
        return redirect(url_for('login'))
    
    return render_template('reset-password.html')

@app.route('/qr-code/<secret>/<email>')
def qr_code(secret, email):
    # Générer le QR code
    totp_uri = generate_totp_uri(secret, email)
    img = qrcode.make(totp_uri)
    
    # Sauvegarder l'image dans un buffer
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return send_file(buffer, mimetype='image/png')

@app.route('/logout')
def logout():
    session.clear()
    flash('Vous avez été déconnecté.')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user_name=session.get('name'))

@app.route('/about-us')
def about():
    return render_template('about-us.html')

@app.route('/contact-us')
def contact():
    return render_template('contact-us.html')

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')

if __name__ == '__main__':
    app.run(debug=True)
