# Plan de Marche — Bot Detector : Évolutions Prioritaires

> **Projet :** Bot_Detector — Détecteur de comptes automatisés Telegram  
> **Date de rédaction :** Octobre 2026  
> **Objectif global :** Passer d'un outil mono-utilisateur / local à une plateforme multi-utilisateurs, déployée en ligne, puis étendue aux autres réseaux sociaux.

---

## Vue d'ensemble des phases

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
Multi-user   Déploiement  X & LinkedIn  WhatsApp / Meta
(1-2 sem.)   distant      (1-2 mois)    (3-6 mois)
             (1-2 sem.)
```

---

## Phase 1 — Multi-utilisateurs du bot Telegram

**Objectif :** Permettre à plusieurs personnes d'utiliser le `@` du bot sans modifier la logique métier.

**Durée estimée :** 1 semaine

### Tâches

- [x] **1.1** Ajouter une variable `TG_ALLOWED_IDS` dans `.env` (liste d'IDs séparés par des virgules)
- [x] **1.2** Remplacer le check `event.sender_id != OWNER_ID` par une vérification dans un `set` d'IDs autorisés, dans tous les handlers de `main.py`
- [x] **1.3** Ajouter une commande `/whoami` qui renvoie l'ID Telegram de l'appelant (pour faciliter l'onboarding des nouveaux utilisateurs)
- [x] **1.4** Ajouter une commande `/acces` réservée à `OWNER_ID` pour lister les utilisateurs autorisés
- [x] **1.5** Mettre à jour `.env.example` avec le nouveau champ `TG_ALLOWED_IDS`
- [x] **1.6** Mettre à jour le `README.md` avec les instructions d'ajout d'un utilisateur

> ✅ **Phase 1 complétée le 8 octobre 2026**

### Contraintes à documenter
- Le `user_client` (compte Telethon) reste **un seul compte** partagé par tous.
- Les analyses de tous les utilisateurs sont stockées dans la **même base SQLite**.
- Le dashboard web reste accessible à quiconque connaît l'URL (à sécuriser en Phase 2).

---

## Phase 2 — Déploiement sur un domaine distant

**Objectif :** Faire tourner le système 24h/24 sur un serveur distant accessible via une URL publique, sans dépendre de l'exécution locale de `main.py`.

**Durée estimée :** 1 à 2 semaines

### Architecture cible

```
Internet
   │
   ▼
[Nom de domaine]  ex: botdetector.mondomaine.com
   │
   ▼
[Nginx reverse proxy]  (SSL / HTTPS via Let's Encrypt)
   │
   ├──► /         ──► FastAPI server.py  (port 8000)
   └──► /ws       ──► WebSocket server.py
   
[VPS Linux]
   ├── main.py   (Telethon bot + userbot)  ← systemd service
   └── server.py (FastAPI dashboard)       ← systemd service
```

### Tâches

- [ ] **2.1** Choisir et louer un VPS Linux (Hetzner CX11, OVH VPS Starter, ou DigitalOcean Droplet — ~3-5€/mois)
- [ ] **2.2** Installer les dépendances sur le VPS : Python 3.12, pip, virtualenv
- [ ] **2.3** Transférer le projet sur le VPS (Git clone depuis un dépôt privé recommandé)
- [ ] **2.4** Configurer le fichier `.env` sur le serveur (ne jamais commiter les secrets)
- [ ] **2.5** Créer deux services `systemd` :
  - `botdetector-bot.service` → lance `main.py`
  - `botdetector-api.service` → lance `uvicorn server:app`
- [ ] **2.6** Installer et configurer Nginx comme reverse proxy
- [ ] **2.7** Générer un certificat SSL avec Certbot (Let's Encrypt) pour HTTPS
- [ ] **2.8** Pointer un sous-domaine vers l'IP du VPS (enregistrement DNS de type A)
- [ ] **2.9** Ajouter une authentification basique (token ou login) sur le dashboard web pour le protéger
- [ ] **2.10** Tester la reconnexion automatique du bot après reboot du serveur
- [ ] **2.11** Mettre en place une sauvegarde automatique de `data/analyses.db` (cron quotidien)

### Fichiers à créer
- `deploy/botdetector-bot.service` — unité systemd pour le bot
- `deploy/botdetector-api.service` — unité systemd pour l'API
- `deploy/nginx.conf` — configuration Nginx
- `deploy/README_DEPLOY.md` — guide pas à pas du déploiement

---

## Phase 3 — Extension à X (Twitter) et LinkedIn

**Objectif :** Réutiliser le moteur de scoring et la base de données existants pour analyser des comptes sur d'autres réseaux à API officielle.

**Durée estimée :** 1 à 2 mois

### Pré-requis
- Obtenir les clés API X Developer (gratuit, tier Basic ~100€/mois pour volume ou Free pour tests)
- Obtenir les clés API LinkedIn (via LinkedIn Developer Portal — gratuit pour usage personnel)

### Tâches

- [ ] **3.1** Ajouter un champ `reseau` (TEXT) dans la table `analyses` de SQLite (`telegram`, `x`, `linkedin`)
- [ ] **3.2** Créer `x_detector.py` — module d'analyse de comptes X :
  - Âge du compte, ratio followers/following, fréquence de publication, présence de photo
  - Utilisation de l'API X v2 (`tweepy`)
- [ ] **3.3** Créer `linkedin_detector.py` — module d'analyse de comptes LinkedIn :
  - Complétude du profil, ancienneté, connexions, activité
  - Utilisation de l'API LinkedIn Marketing / People
- [ ] **3.4** Ajouter les commandes bot `/analyser_x @pseudo` et `/analyser_linkedin URL`
- [ ] **3.5** Adapter le dashboard web pour filtrer les analyses par réseau (`?reseau=x`)
- [ ] **3.6** Harmoniser les scores (même échelle 0-100%) entre tous les réseaux
- [ ] **3.7** Mettre à jour `.env.example` avec les nouvelles clés API

---

## Phase 4 — Extension à WhatsApp, Instagram, Facebook

**Objectif :** Couvrir les réseaux Meta. Plus complexe techniquement et légalement.

**Durée estimée :** 3 à 6 mois

### Contexte et contraintes

| Réseau | API disponible | Limitation principale |
|---|---|---|
| WhatsApp | Business API Cloud (Meta) | Impossible d'analyser des comptes tiers sans consentement |
| Instagram | Graph API (via Facebook App) | Profils privés inaccessibles, quotas stricts |
| Facebook | Graph API | Validation Meta obligatoire, données très limitées |

### Approche recommandée
- Se concentrer sur l'analyse des **pages publiques** et **comptes Business** (seul accès légal via API)
- Pour les comptes personnels : collecter uniquement des **signaux publics** (photo, bio, date de création)
- Prévoir une revue juridique (RGPD, CGU de chaque plateforme)

### Tâches

- [ ] **4.1** Créer une Facebook App approuvée par Meta (nécessite une review)
- [ ] **4.2** Implémenter `facebook_detector.py` pour les pages publiques
- [ ] **4.3** Implémenter `instagram_detector.py` pour les profils publics
- [ ] **4.4** Étudier la faisabilité WhatsApp (probablement limité aux signaux de numéro de téléphone)
- [ ] **4.5** Adapter l'interface bot et le dashboard pour la sélection du réseau cible
- [ ] **4.6** Rédiger une politique de confidentialité et conditions d'utilisation

---

## Récapitulatif des priorités

| Priorité | Phase | Impact | Effort |
|---|---|---|---|
| 🔴 Haute | Phase 1 — Multi-utilisateurs | Immédiat | Faible |
| 🔴 Haute | Phase 2 — Déploiement VPS | Fondation pour tout le reste | Moyen |
| 🟠 Moyenne | Phase 3 — X & LinkedIn | Valeur ajoutée forte | Moyen |
| 🟡 Basse | Phase 4 — Meta (WhatsApp/Instagram/Facebook) | Vision long terme | Élevé |

---

## Stack technique prévue

| Couche | Technologie actuelle | Évolution |
|---|---|---|
| Bot Telegram | Telethon | Inchangé |
| API REST | FastAPI | Inchangé |
| Base de données | SQLite (WAL) | → PostgreSQL si trafic élevé |
| Déploiement | Local | → VPS + systemd + Nginx |
| Réseau X | — | Tweepy (API v2) |
| Réseau LinkedIn | — | linkedin-api ou API officielle |
| Réseau Meta | — | facebook-sdk / Graph API |
| Sécurité accès | OWNER_ID unique | → Liste d'IDs + auth dashboard |

---

*Document vivant — à mettre à jour au fil des implémentations.*
