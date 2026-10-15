# 🤖 Bot Sentinel Multi-Réseau

> **Système d'estimation probabiliste et explicable pour la détection de comptes automatisés sur Telegram, X (Twitter) et LinkedIn.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Telethon](https://img.shields.io/badge/Telethon-1.45%2B-orange.svg)](https://docs.telethon.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#licence)

---

## 📌 Contexte & Problématique

Les comptes automatisés sur les réseaux sociaux (userbots IA) deviennent de plus en plus sophistiqués : réponses fluides et instantanées, imitation des comportements humains, intégration dans les conversations privées ou de groupe. Utilisés par des escrocs, ils servent à :

- L'arnaque sentimentale (*romance scam*)
- Le vol de données (SMS OTP, mots de passe, identifiants)
- La promotion d'investissements frauduleux (crypto, forex, trading)
- L'hameçonnage (phishing)

**Bot Sentinel** couvre actuellement 3 réseaux : Telegram, X (Twitter) et LinkedIn. Il analyse les attributs publics, surveille la télémétrie comportementale du rythme de réponse (Telegram), propose des défis anti-bot interactifs et évalue le niveau de dangerosité du texte pour produire une **estimation probabiliste explicable**.

---

## 🏗️ Architecture du système

Le système repose sur :

```
Toi (Telegram/X/LinkedIn)  →  bot_client        →  commandes /analyser, /analyser_x, /analyser_ld...
                             user_client         →  requêtes API Telegram, mesure délais
                             FastAPI/uvicorn     →  dashboard SOC web (http://127.0.0.1:8000)
                             x_detector.py       →  requêtes API X (Bearer Token)
                             linkedin_detector.py→  analyse URL/slug LinkedIn
```

| Composant | Rôle |
|---|---|
| `bot_client` | Interface Telegram : reçoit tes commandes, renvoie les rapports |
| `user_client` | Collecteur Telegram : lit les profils publics, mesure les délais dans tes conversations |
| `server.py` | API REST + WebSocket : expose les données pour le dashboard web |
| `x_detector.py` | Module X (Twitter) : analyse via API X v2 (Bearer Token requis) |
| `linkedin_detector.py` | Module LinkedIn : analyse URL/slug (sans clé), prêt pour API officielle |

### Structure des fichiers

```
Bot_Detector/
├── main.py              # Script principal (bot + userbot + orchestration)
├── veille.py            # Télémétrie comportementale (délais & activité 24h/24)
├── defis.py             # Générateur de défis anti-bot
├── server.py            # API FastAPI + dashboard SOC web (v3.0)
├── telegram_detector.py # Prototype initial (référence)
├── x_detector.py        # Module d'analyse X (Twitter)
├── linkedin_detector.py # Module d'analyse LinkedIn
├── requirements.txt     # Dépendances Python
├── .env.example         # Modèle de configuration (v3.0)
├── .gitignore
├── data/
│   ├── analyses.db      # Base SQLite (WAL mode) — analyses, retours, surveillances
│   └── retours.csv      # Export CSV des verdicts terrain
└── web/
    ├── index.html       # SPA dashboard (multi-réseau v3.0)
    ├── index.css        # Thème dark SOC
    └── app.js           # Logique client + WebSocket temps réel
```

---

## 📊 Moteur de scoring explicable

Le système génère **deux scores distincts de 0 à 100 %**.

### Score d'automatisation (0–100 %)

| Famille | Signal | Impact | Réseaux concernés |
|---|---|---|---|
| **Réputation** | Marqué `SCAM` ou `FAKE` par la plateforme | +40 | Telegram, X |
| **Réputation** | Listé dans la base anti-spam CAS (Combot) | +40 | Telegram |
| **Profil** | Aucune photo de profil | +15 | Telegram, X |
| **Profil** | Bio vide | +10 | Telegram, X |
| **Profil** | Pseudo d'allure aléatoire (chiffres, consonnes) | +10 | Telegram, X, LinkedIn |
| **Ancienneté** | Compte récent (création estimée ≥ 2024) | +15 | Telegram, X |
| ** Réseau** | Aucun groupe/abonné en commun | +5 | Telegram, X |
| **Présence** | Jamais vu en ligne / activité 24h/24 anormale | +5 / +15 | Telegram, X |
| **Comportement** | Réponses quasi instantanées (médiane < 5 s) | +20 | Telegram |
| **Comportement** | Régularité robotique des délais (écart-type < 3 s) | +25 | Telegram |
| **Comportement** | Activité quasi 24h/24 (≥ 20h/jour) | +15 | Telegram |
| **Atténuation** | Compte vérifié (badge bleu/doré) | −25 à −30 | Telegram, X, LinkedIn |
| **Ratio** | Follower/Following anormal | +10 à +20 | Telegram, X |
| **Densité** | Publication très fréquente (>50 tweets/jour) | +12 à +25 | X uniquement |

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
# Telegram API & Bot
TG_API_ID=1234567
TG_API_HASH=abcdef1234567890abcdef1234567890
TG_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TG_OWNER_ID=987654321

# Utilisateurs autorisés (optionnel)
TG_ALLOWED_IDS=111222333,444555666

# API X (Twitter) — obligatoire pour /analyser_x
X_BEARER_TOKEN=<ton_Bearer_Token_from_developer.twitter.com>

# API LinkedIn — optionnel (niveau 1 sans clé déjà fonctionnel)
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
```

> **Note sur les clés API :**  
> - X : Nécessite un Bearer Token (tier Free suffit pour les profils publics)  
> - LinkedIn : Le niveau 1 (analyse URL/slug) fonctionne sans clé API — le niveau 2 (API officielle) est réservé aux futurs déploiements.

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
| `/analyser @pseudo` | Analyse un compte Telegram public + calcule les scores + sauvegarde en base |
| *(Transfert d'un message)* | Score de danger du texte + analyse de l'expéditeur |
| `/veille @pseudo` | Active la mesure des délais de réponse dans ta conversation Telegram |
| `/rapport @pseudo` | Affiche le rapport comportemental (nécessite ≥ 5 échanges mesurés) |
| `/defi` | Génère un défi anti-bot à transmettre à ton interlocuteur |
| `/retour @pseudo humain\|bot` | Enregistre une vérité terrain dans `data/retours.csv` |
| `/whoami` | Affiche votre ID Telegram et votre statut d'accès |
| `/acces` | *(Propriétaire uniquement)* Liste tous les utilisateurs autorisés |

---

## 💻 Commandes X (Twitter)

| Commande | Description |
|---|---|
| `/analyser_x @username` | Analyse un compte X public (Bearer Token requis) |

**Prérequis :**
1. Crée une App sur [developer.twitter.com](https://developer.twitter.com) → *Apps*
2. Génère un Bearer Token (OAuth 2.0 App-only) dans *Keys and tokens*
3. Copie le Bearer Token et ajoute-le dans `.env` : `X_BEARER_TOKEN=xxxxxxx`
4. Redémarre `main.py`

**Score d'automatisation (0–100 %) sur X :**

| Famille | Signal | Impact |
|---|---|---|
| **Ancienneté** | Compte très récent (< 90 jours) | +20 |
| **Ancienneté** | Compte récent (< 1 an) | +10 |
| **Ratio** | Follower/Following très faible (< 0.05) | +20 |
| **Ratio** | Follower/Following faible (< 0.2) | +10 |
| **Densité** | > 50 tweets/jour | +25 |
| **Densité** | > 20 tweets/jour | +12 |
| **Profil** | Aucun tweet publié | +10 |
| **Profil** | Aucune photo de profil personnalisée | +15 |
| **Profil** | Bio vide | +10 |
| **Pseudo** | Suite de chiffres ≥ 5 en fin de pseudo | +20 |
| **Pseudo** | Suite de chiffres ≥ 4 en fin de pseudo | +10 |
| **Pseudo** | Suite de consonnes ≥ 7 (pseudo aléatoire) | +15 |
| **Atténuation** | Compte vérifié (badge bleu/doré) | −25 |
| **Atténuation** | Souvent ajouté à des listes (≥ 100) | −10 |

> **Note :** X (Twitter) n'a pas de télémétrie comportementale (temps de réponse) comme Telegram — le score est basé uniquement sur les métadonnées du profil.

---

## 💻 Commandes LinkedIn

| Commande | Description |
|---|---|
| `/analyser_ld <url|slug>` | Analyse un profil LinkedIn public (URL ou slug) |

**Prérequis :** Aucun — le niveau 1 fonctionne sans clé API (analyse URL/slug uniquement).

**Niveaux d'analyse :**

| Niveau | Description | Clé API requise |
|---|---|---|
| **Niveau 1** | Analyse de l'URL/slug (longueur, chiffres, format) | ❌ Aucune |
| **Niveau 2** | Analyse complète (connexions, activités, compétences) | ✅ LinkedIn Developer API |

**Score d'automatisation (0–60 %) sur LinkedIn (niveau 1) :**

| Famille | Signal | Impact |
|---|---|---|
| **Slug** | Suite de chiffres ≥ 6 en fin de slug | +20 |
| **Slug** | Suite de chiffres ≥ 4 en fin de slug | +10 |
| **Slug** | Consonnes consécutives ≥ 8 (pseudo aléatoire) | +15 |
| **Slug** | Format par défaut LinkedIn non personnalisé | +15 |
| **Slug** | Slug très court (< 4 caractères) | +5 |

> **Important :** Sans clé API, le score est limité aux signaux de l'URL/slug. Le rapport affichera clairement cette limitation. Pour une analyse complète, configure `LINKEDIN_CLIENT_ID` et `LINKEDIN_CLIENT_SECRET` dans `.env`.

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

## 🌐 Dashboard SOC Web (v3.0)

Accessible sur `http://127.0.0.1:8000` (port auto-détecté si 8000 est occupé).

**Pages disponibles :**

- **Dashboard** — KPI cards (total, bots, suspects, humains, dangers, surveillances), **mini-cards par réseau**, chronologie des scores, répartition, top signaux, inspecteur de profil
- **Analyses** — tableau complet paginé avec **filtre par réseau**, recherche, suppression individuelle
- **Surveillances** — liste des comptes sous veille comportementale
- **Paramètres** — seuils de scoring configurables, activation/désactivation CAS, export CSV, purge RGPD

**Fonctionnalités v3.0 :**
- Sélecteur de réseau en haut et dans la sidebar (Telegram / X / LinkedIn)
- Filter chips pour filtrer les analyses par réseau dans la page Analyses
- Mini-cards réseau dans le dashboard pour un aperçu rapide
- Badge de réseau dans toutes les tables et l'inspecteur

**API REST disponible (v3.0) :**

| Endpoint | Méthode | Description |
|---|---|---|
| `/api/stats` | GET | Métriques globales (avec `?reseau=` optionnel) |
| `/api/reseaux` | GET | Liste des réseaux avec nombre d'analyses |
| `/api/analyses` | GET | Liste paginée des analyses (avec `?reseau=` optionnel) |
| `/api/analyses/{id}` | GET / DELETE | Détail ou suppression |
| `/api/feedback` | POST | Enregistrer un verdict |
| `/api/surveillances` | GET | Comptes sous veille |
| `/api/parametres` | GET | Liste des paramètres |
| `/api/parametres/{cle}` | PUT | Modifier un paramètre |
| `/api/utilisateurs` | GET | Utilisateurs autorisés |
| `/api/utilisateurs` | POST | Ajouter un utilisateur |
| `/api/utilisateurs/{id}` | DELETE | Retirer un utilisateur |
| `/ws` | WebSocket | Flux temps réel |

---

## 🛡️ Sécurité, éthique & limites

- **Pas de verdict absolu** — le système produit une estimation. Un score élevé n'est pas une preuve et ne doit pas servir à accuser une personne.
- **RGPD** — seules les métadonnées publiques des conversations auxquelles tu participes sont analysées. Le contenu des messages privés n'est pas stocké.
- **Faux positifs** — un humain au profil vide ou récent peut être mal classé. Le rapport le signale systématiquement.
- **Limites API** — le script respecte les délais Telegram (FloodWait) pour éviter le blocage du compte.
- **Bots officiels** — identifiés immédiatement sur Telegram/X via `ent.bot` ou `bot` en fin de pseudo, et sur LinkedIn via le format d'URL par défaut.
- **Sessions** — les fichiers `.env` et `*.session` contiennent tes clés et tokens d'accès. Ils sont exclus de Git via `.gitignore`.
- **Clés API X** — sans `X_BEARER_TOKEN`, la commande `/analyser_x` affichera un message d'erreur. Le tier Free de X suffit pour les profils publics.
- **LinkedIn niveau 1** — sans clé API, l'analyse est limitée aux signaux de l'URL/slug (longueur, chiffres, format). Le rapport le signale clairement.

---

## 📚 Documentation

- [Cahier des charges complet](docs/Cahier%20des%20charges%20_%20d%C3%A9tection%20de%20comptes%20Telegram%20automatis%C3%A9s.md)
- [Guide de mise en place rapide](docs/GUIDE_MISE_EN_PLACE.md)
- [Plan de marche v3.0 — Multi-réseau](docs/Planning/Plan01.md)

---

## 📄 Licence

Ce projet est sous licence MIT.
