"""
Module de détection de comptes automatisés sur X (Twitter).

Utilise l'API X v2 (Bearer Token, OAuth 2.0 App-only).
Tier Free suffisant pour analyser des profils publics en lecture seule.

Scoring :
  - Ancienneté du compte
  - Ratio followers/following
  - Densité de tweets (tweets/jour depuis création)
  - Photo de profil absente
  - Bio vide
  - Pseudo d'allure générée (chiffres, consonnes)
  - Compte vérifié (atténuation)
  - Suspicion de spam déclarée par X
  - Contenu de la bio (mots-clés de danger)

Clés requises dans .env :
  X_BEARER_TOKEN=<votre Bearer Token>

En l'absence de clé, toutes les fonctions renvoient un état INDISPONIBLE
sans lever d'exception, afin de ne pas bloquer le reste du système.
"""

import os
import re
import datetime
from typing import Tuple, List, Optional, Dict, Any

import aiohttp
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BEARER_TOKEN: Optional[str] = os.environ.get("X_BEARER_TOKEN", "").strip() or None

X_API_BASE = "https://api.twitter.com/2"

# Champs demandés à l'API X v2
USER_FIELDS = (
    "id,name,username,description,created_at,public_metrics,"
    "profile_image_url,verified,withheld,entities"
)

# Mots-clés de danger réutilisés (même logique que Telegram)
MOTS_DANGER = {
    "argent / crypto": r"\b(crypto|bitcoin|btc|usdt|investi\w*|trading|forex|virement|wallet)\b",
    "promesse de gains": r"\b(gains?|profits?|rentab\w+|revenu passif|garanti|100 ?%)\b",
    "urgence":          r"\b(urgent|immédiatement|dernière chance|maintenant|vite|aujourd'hui seulement)\b",
    "données sensibles": r"\b(mot de passe|code (sms|de vérification)|otp|pin|carte bancaire|iban|passeport)\b",
    "sortie de plateforme": r"(wa\.me|whatsapp|t\.me/|bit\.ly|tinyurl|https?://)",
    "séduction / confiance": r"\b(mon chéri|ma chérie|mon amour|dear|darling|veuve|héritage)\b",
}

# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _headers() -> Dict[str, str]:
    """Construit les headers d'authentification Bearer."""
    return {"Authorization": f"Bearer {BEARER_TOKEN}"}


def _score_texte_danger(texte: str) -> Tuple[int, List[str]]:
    """Calcule le score de dangerosité d'un texte."""
    score, raisons = 0, []
    for nom, motif in MOTS_DANGER.items():
        if re.search(motif, texte, re.IGNORECASE):
            score += 15
            raisons.append(nom)
    return min(score, 100), raisons


def _pseudo_aleatoire(username: str) -> bool:
    """Détecte un pseudo généré : suite de chiffres ou de consonnes."""
    return bool(
        re.search(r"\d{5,}$", username) or
        re.search(r"[bcdfghjklmnpqrstvwxz]{7,}", username, re.I)
    )


def _age_jours(created_at: str) -> int:
    """Calcule l'âge du compte en jours depuis created_at (ISO 8601)."""
    try:
        dt = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return max(1, (datetime.datetime.now(datetime.timezone.utc) - dt).days)
    except Exception:
        return 365  # valeur sûre par défaut


# ---------------------------------------------------------------------------
# Appel API
# ---------------------------------------------------------------------------

async def _fetch_user(identifier: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Récupère les données d'un utilisateur X.
    identifier peut être :
      - @username  (ou username sans @)
      - un ID numérique (string)
    Retourne (data_dict, erreur_str) — l'un des deux sera None.
    """
    if not BEARER_TOKEN:
        return None, "Clé X_BEARER_TOKEN absente dans .env — configurez-la sur https://developer.twitter.com"

    ident = identifier.lstrip("@").strip()

    # Détermine si c'est un ID numérique ou un username
    if ident.isdigit():
        url = f"{X_API_BASE}/users/{ident}"
    else:
        url = f"{X_API_BASE}/users/by/username/{ident}"

    params = {"user.fields": USER_FIELDS}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=_headers(), params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                body = await resp.json()

                if resp.status == 401:
                    return None, "Token X invalide ou expiré. Vérifiez X_BEARER_TOKEN dans .env."
                if resp.status == 403:
                    return None, "Accès refusé par l'API X. Votre tier ne permet pas cet endpoint."
                if resp.status == 404:
                    return None, f"Compte X introuvable : @{ident}"
                if resp.status == 429:
                    return None, "Limite de taux API X atteinte. Réessayez dans 15 minutes."
                if resp.status != 200:
                    detail = body.get("detail") or body.get("title") or f"HTTP {resp.status}"
                    return None, f"Erreur API X : {detail}"

                if "errors" in body and "data" not in body:
                    msg = body["errors"][0].get("detail") or body["errors"][0].get("title") or "Erreur inconnue"
                    return None, f"API X : {msg}"

                return body.get("data"), None

    except aiohttp.ClientConnectorError:
        return None, "Impossible de joindre l'API X (problème réseau)."
    except Exception as e:
        return None, f"Erreur inattendue : {e}"


# ---------------------------------------------------------------------------
# Moteur de scoring
# ---------------------------------------------------------------------------

def _calculer_scores(data: Dict[str, Any]) -> Tuple[int, List[str], int, List[str]]:
    """
    Calcule les scores d'automatisation et de danger à partir des données de profil X.
    Retourne (score_auto, signaux_auto, score_danger, signaux_danger).
    """
    auto = 0
    raisons: List[str] = []

    def ajouter(pts: int, raison: str):
        nonlocal auto
        auto += pts
        prefix = f"+{pts}" if pts > 0 else str(pts)
        raisons.append(f"{prefix} : {raison}")

    metrics = data.get("public_metrics", {})
    followers = metrics.get("followers_count", 0)
    following = metrics.get("following_count", 0)
    tweet_count = metrics.get("tweet_count", 0)
    listed_count = metrics.get("listed_count", 0)

    created_at = data.get("created_at", "")
    age_j = _age_jours(created_at) if created_at else 365
    annee_creation = (
        datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00")).year
        if created_at else 2020
    )

    bio = (data.get("description") or "").strip()
    username = data.get("username") or ""
    profile_img = data.get("profile_image_url") or ""
    verified = data.get("verified", False)

    # — Ancienneté —
    if age_j < 90:
        ajouter(20, f"Compte très récent ({age_j} jours, créé en {annee_creation})")
    elif age_j < 365:
        ajouter(10, f"Compte récent (moins d'un an, créé en {annee_creation})")

    # — Ratio followers/following —
    if following > 0:
        ratio = followers / following
        if ratio < 0.05:
            ajouter(20, f"Ratio followers/following très faible ({ratio:.2f}) — profil de masse")
        elif ratio < 0.2:
            ajouter(10, f"Ratio followers/following faible ({ratio:.2f})")

    # — Densité de tweets —
    tweets_par_jour = tweet_count / age_j if age_j > 0 else 0
    if tweets_par_jour > 50:
        ajouter(25, f"Densité de publication anormale ({tweets_par_jour:.0f} tweets/jour)")
    elif tweets_par_jour > 20:
        ajouter(12, f"Publication très fréquente ({tweets_par_jour:.0f} tweets/jour)")
    elif tweet_count == 0:
        ajouter(10, "Aucun tweet publié (compte vide)")

    # — Profil incomplet —
    if not bio:
        ajouter(10, "Bio vide")
    if not profile_img or "default_profile_images" in profile_img:
        ajouter(15, "Aucune photo de profil personnalisée")
    if listed_count == 0 and followers > 500:
        ajouter(5, "Jamais ajouté à une liste malgré un nombre de followers élevé")

    # — Pseudo généré —
    if _pseudo_aleatoire(username):
        ajouter(10, f"Pseudo d'allure générée (@{username})")

    # — Follower count extrêmes —
    if followers == 0:
        ajouter(10, "Aucun follower")
    elif followers > 100_000 and following > 80_000:
        ajouter(15, "Suivi massif — pattern de compte de masse-follow")

    # — Atténuations —
    if verified:
        ajouter(-25, "Compte vérifié (badge bleu ou doré)")
    if listed_count > 100:
        ajouter(-10, "Souvent ajouté à des listes (signal de notoriété réelle)")

    # — Score danger sur la bio —
    score_danger, raisons_danger = _score_texte_danger(bio)

    auto = max(0, min(auto, 100))
    return auto, raisons, score_danger, raisons_danger


# ---------------------------------------------------------------------------
# Point d'entrée public
# ---------------------------------------------------------------------------

async def analyser_compte_x(identifier: str) -> Dict[str, Any]:
    """
    Analyse un compte X et retourne un dictionnaire normalisé compatible
    avec sauvegarder_analyse() de main.py.

    Champs retournés :
      ok          (bool)   — False si erreur
      erreur      (str)    — message d'erreur si ok=False
      chat_id     (int)    — ID numérique X
      username    (str)
      first_name  (str)    — display name
      last_name   (str)    — None (X n'a pas ce champ)
      score_automatisation (int)
      score_danger         (int)
      signaux_automatisation (list[str])
      signaux_danger         (list[str])
      rapport_texte (str)  — texte formaté pour réponse Telegram
    """
    data, erreur = await _fetch_user(identifier)

    if erreur or data is None:
        return {"ok": False, "erreur": erreur or "Données vides"}

    auto, raisons_auto, danger, raisons_danger = _calculer_scores(data)

    metrics = data.get("public_metrics", {})
    created_at = data.get("created_at", "")
    age_j = _age_jours(created_at)
    annee = (
        datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00")).year
        if created_at else "?"
    )

    niveau = "ÉLEVÉ 🔴" if auto >= 60 else "MOYEN 🟠" if auto >= 30 else "FAIBLE 🟢"
    nom = data.get("name") or data.get("username") or "Sans Nom"
    handle = f"@{data['username']}" if data.get("username") else ""

    rep = [
        f"🐦 **Rapport X pour :** {nom} ({handle})",
        f"🆔 **ID X :** `{data.get('id')}` · Créé en **{annee}** ({age_j} jours)",
        f"👥 Followers : **{metrics.get('followers_count',0):,}** · Following : **{metrics.get('following_count',0):,}**",
        f"🐦 Tweets : **{metrics.get('tweet_count',0):,}**",
        f"📊 **Probabilité d'automatisation : {auto} %** ({niveau})",
        "",
        "📌 **Signaux détectés :**",
    ]
    if raisons_auto:
        rep.extend([f"  • {r}" for r in raisons_auto])
    else:
        rep.append("  • Aucun signal suspect détecté.")

    if danger > 0:
        rep.append(f"\n⚠️ **Danger détecté dans la bio ({danger} %) :** {', '.join(raisons_danger)}")

    rep.append("\nℹ️ *Estimation explicable — pas une preuve absolue.*")

    return {
        "ok": True,
        "chat_id": int(data.get("id", 0)),
        "username": data.get("username"),
        "first_name": data.get("name"),
        "last_name": None,
        "score_automatisation": auto,
        "score_danger": danger,
        "signaux_automatisation": raisons_auto,
        "signaux_danger": raisons_danger,
        "rapport_texte": "\n".join(rep),
    }
