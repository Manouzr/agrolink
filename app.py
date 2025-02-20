from flask import Flask, render_template, request, flash, jsonify, redirect, url_for, session, send_file
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import csv
import os
import io
import base64
import json
import uuid
import pyotp
import qrcode
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  
import matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, InputLayer
import pickle
from functools import wraps
import secrets
import matplotlib
import qrcode
from io import BytesIO
app = Flask(__name__, 
            template_folder='templates',
            static_folder='static',
            static_url_path='/static')

app.config.update(
    SECRET_KEY=secrets.token_hex(32),
    SESSION_COOKIE_SECURE=False,  
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=2800  
)

os.makedirs('data', exist_ok=True)
os.makedirs('templates', exist_ok=True)

# Fonctions utilitaires pour l'authentification
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter pour accéder à cette page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def load_users():
    if not os.path.exists('data/users.json'):
        with open('data/users.json', 'w') as f:
            json.dump({'users': []}, f)
    with open('data/users.json', 'r') as f:
        return json.load(f)

def save_users(users_data):
    with open('data/users.json', 'w') as f:
        json.dump(users_data, f, indent=4)

def generate_totp_secret():
    return pyotp.random_base32()

def generate_totp_uri(secret, email):
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(email, issuer_name="AgroLink")

# Fonctions utilitaires pour l'IA
def extract_number_from_onclick(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    anchor = soup.find('a', {
        'class': 'btn btn-info p-0 btn-history text-right me-1',
        'href': '#inner-pub'
    })
    
    if anchor and 'onclick' in anchor.attrs:
        onclick_value = anchor['onclick']
        match = re.search(r'anchorGraph\((\d+)', onclick_value)
        if match:
            return match.group(1)
    return None

def generate_csv(product_url):
    try:
        req = requests.get(product_url)
        number = extract_number_from_onclick(req.text)
        if not number:
            return False, "Impossible d'extraire le numéro du produit"

        req = requests.get(f"https://www.terre-net.fr/MarketData/All/{number}")
        data = req.json()

        csv_filename = "prix_uree.csv"
        with open(csv_filename, 'w', newline='') as csvfile:
            csvwriter = csv.writer(csvfile)
            csvwriter.writerow(['Date', 'Prix'])
            
            for timestamp, price in data['prices']:
                date = datetime.fromtimestamp(timestamp / 1000.0).strftime('%Y-%m-%d')
                csvwriter.writerow([date, price])
        
        return True, csv_filename
    except Exception as e:
        return False, str(e)

def load_data(file_path):
    df = pd.read_csv(file_path)
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(by='Date')
    return df

def create_sequences(data, seq_length):
    X, y = [], []
    for i in range(len(data) - seq_length):
        X.append(data[i:i + seq_length])
        y.append(data[i + seq_length])
    return np.array(X), np.array(y)

def train_model(df):
    scaler = MinMaxScaler()
    df['Prix_scaled'] = scaler.fit_transform(df[['Prix']])

    with open("scaler.pkl", 'wb') as f:
        pickle.dump(scaler, f)

    sequence_length = 10
    X, y = create_sequences(df['Prix_scaled'].values, sequence_length)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=False)
    X_train = X_train.reshape((X_train.shape[0], X_train.shape[1], 1))
    X_test = X_test.reshape((X_test.shape[0], X_test.shape[1], 1))

    model = Sequential([
        InputLayer(input_shape=(sequence_length, 1)),
        LSTM(units=50, activation='relu'),
        Dense(units=1)
    ])

    model.compile(optimizer='adam', loss='mean_squared_error')
    model.fit(X_train, y_train, epochs=500, batch_size=16, verbose=0)
    model.save("stock_price_prediction_model.keras")

    return model, scaler

def predict_future_prices(model, last_sequence, scaler, sequence_length, target_year):
    current_date = datetime.now()
    months_until_target_year = ((target_year - current_date.year) * 12) + (12 - current_date.month)
    
    predictions = []
    current_sequence = last_sequence.copy()
    
    for _ in range(months_until_target_year + 12):
        current_sequence_reshaped = current_sequence.reshape(1, sequence_length, 1)
        next_pred = model.predict(current_sequence_reshaped, verbose=0)[0][0]
        predictions.append(next_pred)
        current_sequence = np.roll(current_sequence, -1)
        current_sequence[-1] = next_pred
    
    predictions = scaler.inverse_transform(np.array(predictions).reshape(-1, 1))
    return predictions

def create_prediction_plot(df, target_year, target_dates, target_predictions):
    plt.figure(figsize=(12, 6))
    
    last_real_dates = df['Date'].tail(12)
    last_real_prices = df['Prix'].tail(12)
    plt.plot(last_real_dates, last_real_prices, 
            marker='o', linestyle='-', color='blue', 
            label='Prix réels (12 derniers mois)')
    
    plt.plot(target_dates, target_predictions, 
            marker='o', linestyle='--', color='green', 
            label=f'Prédictions pour {target_year}')
    
    plt.xlabel('Date')
    plt.ylabel('Prix')
    plt.title(f'Prédictions des prix pour l\'année {target_year}')
    plt.legend()
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.tight_layout()

    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight')
    img.seek(0)
    plt.close()
    return base64.b64encode(img.getvalue()).decode()

# Routes pour l'authentification
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
            flash('Tous les champs sont requis.', 'danger')
            return redirect(url_for('signup'))
        
        users_data = load_users()
        
        if any(user['email'] == email for user in users_data['users']):
            flash('Cet email est déjà utilisé.', 'danger')
            return redirect(url_for('signup'))
        
        try:
            totp_secret = generate_totp_secret()
            
            new_user = {
                'id': len(users_data['users']) + 1,
                'name': name,
                'email': email,
                'password': password,
                'totp_secret': totp_secret,
                'totp_enabled': False
            }
            
            users_data['users'].append(new_user)
            save_users(users_data)
            
            session.clear()
            session['setup_2fa_user_id'] = new_user['id']
            session['_fresh'] = True
            
            return redirect(url_for('setup_2fa'))
            
        except Exception as e:
            print(f"Erreur lors de la création de l'utilisateur: {e}")
            flash('Une erreur est survenue lors de la création du compte.', 'danger')
            return redirect(url_for('signup'))
    
    return render_template('sign-up.html')

@app.route('/setup-2fa')
def setup_2fa():
    if '_fresh' not in session or not session.get('_fresh'):
        flash('Session expirée. Veuillez vous inscrire à nouveau.', 'danger')
        return redirect(url_for('signup'))
    
    user_id = session.get('setup_2fa_user_id')
    if not user_id:
        flash('Veuillez vous inscrire d\'abord.', 'danger')
        return redirect(url_for('signup'))
    
    try:
        users_data = load_users()
        user = next((user for user in users_data['users'] if user['id'] == user_id), None)
        
        if not user:
            session.clear()
            flash('Utilisateur non trouvé.', 'danger')
            return redirect(url_for('signup'))
        
        if user['totp_enabled']:
            flash('2FA déjà configuré.', 'danger')
            return redirect(url_for('login'))
        
        totp_uri = generate_totp_uri(user['totp_secret'], user['email'])
        return render_template('setup-2fa.html', totp_uri=totp_uri)
        
    except Exception as e:
        print(f"Erreur lors de la configuration 2FA: {e}")
        flash('Une erreur est survenue lors de la configuration 2FA.', 'danger')
        return redirect(url_for('signup'))

@app.route('/verify-2fa', methods=['POST'])
def verify_2fa():
    if 'setup_2fa_user_id' not in session:
        flash('Session expirée.', 'danger')
        return redirect(url_for('signup'))
        
    token = request.form.get('token')
    if not token:
        flash('Code requis.', 'danger')
        return redirect(url_for('setup_2fa'))
        
    users_data = load_users()
    user = next((user for user in users_data['users'] if user['id'] == session['setup_2fa_user_id']), None)
    
    if not user:
        flash('Utilisateur non trouvé.', 'danger')
        return redirect(url_for('signup'))
        
    totp = pyotp.TOTP(user['totp_secret'])
    if totp.verify(token):
        user['totp_enabled'] = True
        save_users(users_data)
        
        session.clear()
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        flash('2FA configuré avec succès!', 'success')
        return redirect(url_for('dashboard'))
    else:
        flash('Code invalide.', 'danger')
        return redirect(url_for('setup_2fa'))

@app.route('/verify-login', methods=['GET', 'POST'])
def verify_login():
    if request.method == 'POST':
        email = session.get('login_email')
        token = request.form.get('token')
        
        if not email or not token:
            flash('Session expirée ou données manquantes.', 'danger')
            return redirect(url_for('login'))
            
        users_data = load_users()
        user = next((user for user in users_data['users'] if user['email'] == email), None)
        
        if not user:
            flash('Utilisateur non trouvé.', 'danger')
            return redirect(url_for('login'))
            
        totp = pyotp.TOTP(user['totp_secret'])
        if totp.verify(token):
            session.clear()
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            flash('Connexion réussie!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Code 2FA invalide.', 'danger')
            return redirect(url_for('verify_login'))
            
    return render_template('verify-login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('Email et mot de passe requis.', 'danger')
            return redirect(url_for('login'))
            
        users_data = load_users()
        user = next((user for user in users_data['users'] if user['email'] == email), None)
        
        if not user or user['password'] != password:
            flash('Email ou mot de passe incorrect.', 'danger')
            return redirect(url_for('login'))
            
        if user['totp_enabled']:
            session['login_email'] = email
            return redirect(url_for('verify_login'))
        else:
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            flash('Connexion réussie!', 'success')
            return redirect(url_for('dashboard'))
            
    return render_template('sign-in.html')

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    users_data = load_users()
    user = next((user for user in users_data['users'] if user['id'] == session['user_id']), None)
    
    if request.method == 'POST' and 'predict' in request.form:
        try:
            product_url = request.form.get('product_url')
            target_year = int(request.form.get('year'))
            
            if target_year < datetime.now().year:
                flash('Veuillez entrer une année future', 'danger')
                return render_template('dashboard.html', 
                                    user_name=user['name'] if user else None,
                                    current_year=datetime.now().year)

            success, message = generate_csv(product_url)
            if not success:
                flash(f'Erreur lors de la récupération des données: {message}', 'danger')
                return render_template('dashboard.html', 
                                    user_name=user['name'] if user else None,
                                    current_year=datetime.now().year)

            df = load_data('prix_uree.csv')
            model, scaler = train_model(df)

            sequence_length = 10
            df['Prix_scaled'] = scaler.transform(df[['Prix']])
            last_known_sequence = df['Prix_scaled'].values[-sequence_length:]
            
            future_predictions = predict_future_prices(model, last_known_sequence, scaler, sequence_length, target_year)
            
            last_date = df['Date'].iloc[-1]
            future_dates = pd.date_range(start=last_date, periods=len(future_predictions) + 1, freq='M')[1:]
            
            target_dates_mask = future_dates.year == target_year
            target_predictions = future_predictions[target_dates_mask]
            target_dates = future_dates[target_dates_mask]

            if len(target_predictions) > 0:
                plot_url = create_prediction_plot(df, target_year, target_dates, target_predictions)
                predictions_data = [
                    {
                        'date': date.strftime('%B %Y'),
                        'price': float(price[0])
                    }
                    for date, price in zip(target_dates, target_predictions)
                ]
                return render_template('dashboard.html', 
                                    user_name=user['name'] if user else None,
                                    plot_url=plot_url,
                                    predictions=predictions_data,
                                    target_year=target_year,
                                    current_year=datetime.now().year)
            else:
                flash('Aucune prédiction disponible pour cette année', 'danger')
        except Exception as e:
            flash(f'Erreur lors du traitement: {str(e)}', 'danger')

    return render_template('dashboard.html', 
                         user_name=user['name'] if user else None,
                         current_year=datetime.now().year)

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('Vous avez été déconnecté avec succès', 'success')
    return redirect(url_for('login'))

# Routes supplémentaires
@app.route('/about-us')
def about():
    return render_template('about-us.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email')
        token = request.form.get('token')
        new_password = request.form.get('new_password')
        
        users_data = load_users()
        user = next((user for user in users_data['users'] if user['email'] == email), None)
        
        if not user:
            flash('Aucun compte associé à cet email.', 'danger')
            return redirect(url_for('reset_password'))
        
        totp = pyotp.TOTP(user['totp_secret'])
        if not totp.verify(token):
            flash('Code d\'authentification incorrect.', 'danger')
            return redirect(url_for('reset_password'))
        
        user['password'] = new_password
        save_users(users_data)
        
        flash('Votre mot de passe a été réinitialisé avec succès.', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset-password.html')

@app.route('/qr-code/<secret>/<email>')
def qr_code(secret, email):
    totp_uri = generate_totp_uri(secret, email)
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

if __name__ == '__main__':
    app.run(debug=True)