# 🤖 Telegram Bot Sentinel

> **Système d'estimation probabiliste et explicable pour la détection de comptes Telegram automatisés (userbots IA) et dangereux.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Telethon](https://img.shields.io/badge/Telethon-1.45%2B-orange.svg)](https://docs.telethon.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#licence)

---

## 📌 Contexte & Problématique

Les comptes Telegram automatisés par des agents IA (userbots) sont de plus en plus sophistiqués : réponses fluides et instantanées, imitation des comportements humains, intégration dans les conversations privées ou de groupe. Utilisés par des escrocs, ils servent à :

- L'arnaque sentimentale (*romance scam*)
- Le vol de données (SMS OTP, mots de passe, identifiants)
- La promotion d'investissements frauduleux (crypto, forex, trading)
- L'hameçonnage (phishing)

Ces comptes **n'ont aucun marqueur officiel** (contrairement aux bots déclarés en `@..._bot`) et nient systématiquement être des bots.

**Telegram Bot Sentinel** analyse les attributs publics, surveille la télémétrie comportementale du rythme de réponse, propose des défis anti-bot interactifs et évalue le niveau de dangerosité du texte pour produire une **estimation probabiliste explicable**.

---

## 🏗️ Architecture du système

Le système repose sur **deux clients Telethon** s'exécutant en parallèle, plus un **dashboard web** :

```
Toi (Telegram)  →  bot_client       →  commandes /analyser, /veille, /defi...
                   user_client      →  requêtes API, lecture profils, mesure délais
                   FastAPI/uvicorn  →  dashboard SOC web (http://127.0.0.1:8000)
```

| Client | Rôle |
|---|---|
| `bot_client` | Interface Telegram : reçoit tes commandes, renvoie les rapports |
| `user_client` | Collecteur : lit les profils publics, mesure les délais dans tes conversations |
| `server.py` | API REST + WebSocket : expose les données pour le dashboard web |

### Structure des fichiers

```
Bot_Detector/
├── main.py              # Script principal (bot + userbot + orchestration)
├── veille.py            # Télémétrie comportementale (délais & activité 24h/24)
├── defis.py             # Générateur de défis anti-bot
├── server.py            # API FastAPI + dashboard SOC web
├── telegram_detector.py # Prototype initial (référence)
├── requirements.txt     # Dépendances Python
├── .env.example         # Modèle de configuration
├── .gitignore
├── data/
│   ├── analyses.db      # Base SQLite (WAL mode) — analyses, retours, surveillances
│   └── retours.csv      # Export CSV des verdicts terrain
└── web/
    ├── index.html       # SPA dashboard (4 pages)
    ├── index.css        # Thème dark SOC
    └── app.js           # Logique client + WebSocket temps réel
```

---

## 📊 Moteur de scoring explicable

Le système génère **deux scores distincts de 0 à 100 %**.

### Score d'automatisation (0–100 %)

| Famille | Signal | Impact |
|---|---|---|
| **Réputation** | Marqué `SCAM` ou `FAKE` par Telegram | +40 |
| **Réputation** | Listé dans la base anti-spam CAS (Combot) | +40 |
| **Profil** | Aucune photo de profil | +15 |
| **Profil** | Bio vide | +10 |
| **Profil** | Pseudo d'allure aléatoire (chiffres, consonnes) | +10 |
| **Ancienneté** | Compte récent (création estimée ≥ 2024 via l'ID) | +15 |
| **Réseau** | Aucun groupe en commun (`GetCommonChatsRequest`) | +5 |
| **Présence** | Jamais vu en ligne | +5 |
| **Comportement** | Réponses quasi instantanées (médiane < 5 s) | +20 |
| **Comportement** | Régularité robotique des délais (écart-type < 3 s) | +25 |
| **Comportement** | Activité quasi 24h/24 (≥ 20 heures/jour observées) | +15 |
| **Atténuation** | Compte Telegram Premium | −5 |
| **Atténuation** | Compte officiel vérifié | −30 |

**Seuils** : < 30 % = faible 🟢 · 30–59 % = moyen 🟠 · ≥ 60 % = élevé 🔴

> **Bots officiels** : si le flag `ent.bot` est actif **ou** si le pseudo se termine par `bot` (convention imposée par @BotFather), le compte est immédiatement identifié comme bot officiel déclaré — aucun score calculé.

### Score de danger du texte (0–100 %)

Évalue la bio du compte ou un message transféré :

| Catégorie | Exemples de mots-clés détectés |
|---|---|
| 💸 Argent / Crypto | bitcoin, USDT, virement, wallet, trading |
| 📈 Promesses de gains | garanti, profit, revenu passif, 100% |
| ⏰ Urgence artificielle | urgent, dernière chance, maintenant |
| 🔑 Données sensibles | mot de passe, code SMS, OTP, IBAN |
| 🔗 Sortie de plateforme | WhatsApp, Bitly, URLs externes |
| ❤️ Séduction / Confiance | mon chéri, héritage, veuve, dear |

---

## 🚀 Installation & Configuration

### 1. Prérequis

- Python 3.9 ou supérieur
- Un compte Telegram valide

### 2. Environnement virtuel

```bash
cd Bot_Detector
python -m venv BD_env

# Windows
BD_env\Scripts\activate

# Linux / macOS
source BD_env/bin/activate

pip install -r requirements.txt
```

### 3. Clés API Telegram

1. Va sur [my.telegram.org](https://my.telegram.org) → *API development tools* → note `api_id` et `api_hash`
2. Écris à `@BotFather` → `/newbot` → note le `token`
3. Écris à `@userinfobot` pour obtenir ton `TG_OWNER_ID`

### 4. Fichier `.env`

```bash
cp .env.example .env
```

```env
TG_API_ID=1234567
TG_API_HASH=abcdef1234567890abcdef1234567890
TG_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TG_OWNER_ID=987654321

# Optionnel : autres utilisateurs autorisés (IDs séparés par des virgules)
# L'OWNER_ID est toujours autorisé, même absent de cette liste
TG_ALLOWED_IDS=111222333,444555666
```

### 5. Lancement

```bash
python main.py
```

Au premier lancement, le `user_client` demande ton numéro de téléphone et le code reçu sur Telegram pour générer la session chiffrée.

Le dashboard SOC s'ouvre automatiquement sur un port libre à partir de `8000`.

---

## 💻 Commandes Telegram

| Commande | Description |
|---|---|
| `/start` ou `/help` | Affiche l'aide |
| `/analyser @pseudo` | Analyse le profil public + calcule les scores + sauvegarde en base |
| *(Transfert d'un message)* | Score de danger du texte + analyse de l'expéditeur |
| `/veille @pseudo` | Active la mesure des délais de réponse dans ta conversation Telegram |
| `/rapport @pseudo` | Affiche le rapport comportemental (nécessite ≥ 5 échanges mesurés) |
| `/defi` | Génère un défi anti-bot à transmettre à ton interlocuteur |
| `/retour @pseudo humain\|bot` | Enregistre une vérité terrain dans `data/retours.csv` |
| `/whoami` | Affiche votre ID Telegram et votre statut d'accès |
| `/acces` | *(Propriétaire uniquement)* Liste tous les utilisateurs autorisés |

---

## 👥 Gestion des accès multi-utilisateurs

Par défaut, seul le `TG_OWNER_ID` peut utiliser le bot. Pour autoriser d'autres utilisateurs :

**1. Demandez à chaque utilisateur d'envoyer `/whoami` au bot** — le bot renverra son ID Telegram même sans accès.

**2. Ajoutez les IDs dans le fichier `.env` :**

```env
TG_ALLOWED_IDS=123456789,987654321,555000111
```

**3. Redémarrez `main.py`** — les nouveaux accès sont actifs immédiatement.

**4. Vérifiez avec `/acces`** (commande réservée au propriétaire) pour voir la liste complète.

> **Note :** Tous les utilisateurs autorisés partagent le même `user_client` (le compte Telethon du propriétaire) et la même base de données SQLite. Les analyses de chacun sont visibles dans le dashboard commun.

---

---

## 👁️ Module de veille comportementale

> **Important** : la veille mesure les délais dans **tes conversations Telegram directes**, pas dans le chat du bot.

**Fonctionnement :**

1. `/veille @pseudo` → ajoute le compte à la liste des surveillés
2. Discute normalement avec ce compte **dans ton Telegram** (pas dans le bot)
3. Le `user_client` enregistre chaque échange (horodatage, direction)
4. Après ≥ 5 échanges, `/rapport @pseudo` calcule :
   - **Médiane des délais** — réponse quasi instantanée (< 5 s) → +20
   - **Écart-type des délais** — régularité robotique (< 3 s) → +25
   - **Heures d'activité** — actif 24h/24 (≥ 20h/jour) → +15

> Les données de veille sont en mémoire et se perdent au redémarrage du bot.

---

## 🎯 Défis anti-bot

| Défi | Ce qui trahit un agent IA |
|---|---|
| 🎙️ **Vocal imposé** — dire 3 mots précis | Refus, texte à la place, voix synthétique |
| 🎙️ **Bruit ambiant** — décrire l'environnement sonore | Réponse générique ou impossible |
| 🤖 **Consigne piège** — prompt injection | Obéissance aveugle à la consigne |
| 📸 **Preuve physique** — photo de main avec mot écrit | Évitement, image réutilisée |

Un seul défi n'est pas concluant — il contribue au score comme les autres signaux.

---

## 🌐 Dashboard SOC Web

Accessible sur `http://127.0.0.1:8000` (port auto-détecté si 8000 est occupé).

**Pages disponibles :**

- **Dashboard** — KPI cards (total, bots, suspects, humains, dangers, surveillances), chronologie des scores, répartition, top signaux, inspecteur de profil
- **Analyses** — tableau complet paginé avec recherche, suppression individuelle
- **Surveillances** — liste des comptes sous veille comportementale
- **Paramètres** — seuils de scoring configurables, activation/désactivation CAS, export CSV, purge RGPD

**API REST disponible :**

| Endpoint | Méthode | Description |
|---|---|---|
| `/api/stats` | GET | Métriques globales |
| `/api/analyses` | GET | Liste paginée des analyses |
| `/api/analyses/{id}` | GET / DELETE | Détail ou suppression |
| `/api/feedback` | POST | Enregistrer un verdict |
| `/api/surveillances` | GET | Comptes sous veille |
| `/api/parametres` | GET | Liste des paramètres |
| `/api/parametres/{cle}` | PUT | Modifier un paramètre |
| `/ws` | WebSocket | Flux temps réel |

---

## 🛡️ Sécurité, éthique & limites

- **Pas de verdict absolu** — le système produit une estimation. Un score élevé n'est pas une preuve et ne doit pas servir à accuser une personne.
- **RGPD** — seules les métadonnées publiques des conversations auxquelles tu participes sont analysées. Le contenu des messages privés n'est pas stocké.
- **Faux positifs** — un humain au profil vide ou récent peut être mal classé. Le rapport le signale systématiquement.
- **Limites API** — le script respecte les délais Telegram (FloodWait) pour éviter le blocage du compte.
- **Bots officiels** — les comptes dont le pseudo se termine par `bot` ou marqués `ent.bot` par l'API sont identifiés immédiatement comme bots officiels et exclus du scoring.
- **Sessions** — les fichiers `.env` et `*.session` contiennent tes clés et tokens d'accès. Ils sont exclus de Git via `.gitignore`.

---

## 📚 Documentation

- [Cahier des charges complet](docs/Cahier%20des%20charges%20_%20d%C3%A9tection%20de%20comptes%20Telegram%20automatis%C3%A9s.md)
- [Guide de mise en place rapide](docs/GUIDE_MISE_EN_PLACE.md)

---

## 📄 Licence

Ce projet est sous licence MIT.
