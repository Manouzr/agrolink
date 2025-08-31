# 🌾 AgroLink - Prédiction des Prix Agricoles


# 🎬  Video de Présentation

https://youtu.be/X-z2m9g8lPo

## 📝 Description
AgroLink est une application web innovante qui utilise l'intelligence artificielle pour prédire les prix des produits agricoles. Elle permet aux agriculteurs et aux professionnels du secteur de prendre des décisions éclairées basées sur des prévisions de prix précises.

## ✨ Fonctionnalités

- 🔐 Authentification sécurisée avec 2FA
- 📊 Prédiction des prix basée sur l'apprentissage automatique
- 📈 Visualisation graphique des prévisions
- 📱 Interface utilisateur moderne et responsive
- 🔍 Analyse des données de Terre-net en temps réel

## 🛠️ Technologies Utilisées

- **Backend**: Python, Flask
- **Frontend**: HTML5, CSS3, JavaScript
- **Base de données**: JSON
- **Machine Learning**: TensorFlow, Keras
- **Sécurité**: 2FA avec PyOTP
- **Data Scraping**: BeautifulSoup4

## 📦 Installation

1. Clonez le repository :
```bash
git clone https://github.com/Manouzr/agrolink.git
cd agrolink
```

2. Installez les dépendances :
```bash
pip install -r requirements.txt
```

3. Lancez l'application :
```bash
python app.py
```

L'application sera accessible à l'adresse `http://localhost:5000`

## 🔧 Configuration

1. Créez un dossier `data` à la racine du projet :
```bash
mkdir data
```

2. Assurez-vous que les fichiers de configuration sont présents :
- `data/users.json` pour les données utilisateurs
- `stock_price_prediction_model.keras` pour le modèle ML (généré automatiquement)

## 💻 Utilisation

1. Créez un compte utilisateur
2. Configurez l'authentification à deux facteurs (2FA)
3. Connectez-vous à votre compte
4. Entrez l'URL d'un produit Terre-net
5. Sélectionnez l'année pour la prédiction
6. Visualisez les résultats et le graphique des prévisions

## 🔒 Sécurité

- Authentification à deux facteurs (2FA)
- Sessions sécurisées
- Protection contre les attaques CSRF
- Stockage sécurisé des mots de passe

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :

1. Fork le projet
2. Créer une branche pour votre fonctionnalité
3. Commiter vos changements
4. Pousser vers la branche
5. Ouvrir une Pull Request

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

