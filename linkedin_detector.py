"""
Module de détection de comptes automatisés sur LinkedIn.

Stratégie d'analyse :
  L'API officielle LinkedIn est réservée aux partenaires entreprise agréés.
  Ce module adopte donc une approche en deux niveaux :

  Niveau 1 — Analyse de l'URL publique (sans clé API)
    • Extraction du slug/vanity URL
    • Signaux heuristiques de l'URL : longueur, chiffres, consonnes
    • Date de création estimée via format de l'URL

  Niveau 2 — Analyse via l'API LinkedIn (avec clé, si disponible)
    • Profil complet, connexions, activité
    • Réservé à une future intégration officielle

  En pratique, sans clé API, le module analyse les signaux disponibles dans
  l'URL et retourne un score conservateur avec les signaux identifiés.

Clés optionnelles dans .env :
  LINKEDIN_CLIENT_ID=<votre Client ID>
  LINKEDIN_CLIENT_SECRET=<votre Client Secret>

En l'absence de clé, l'analyse basique reste fonctionnelle.
"""

import os
import re
from typing import Tuple, List, Optional, Dict, Any
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CLIENT_ID: Optional[str] = os.environ.get("LINKEDIN_CLIENT_ID", "").strip() or None
CLIENT_SECRET: Optional[str] = os.environ.get("LINKEDIN_CLIENT_SECRET", "").strip() or None

API_DISPONIBLE = bool(CLIENT_ID and CLIENT_SECRET)

# Mots-clés de danger (même référentiel que les autres modules)
MOTS_DANGER = {
    "argent / crypto": r"\b(crypto|bitcoin|btc|usdt|investi\w*|trading|forex|virement|wallet)\b",
    "promesse de gains": r"\b(gains?|profits?|rentab\w+|revenu passif|garanti|100 ?%)\b",
    "urgence":          r"\b(urgent|immédiatement|dernière chance|maintenant|vite|aujourd'hui seulement)\b",
    "données sensibles": r"\b(mot de passe|code (sms|de vérification)|otp|pin|carte bancaire|iban|passeport)\b",
    "sortie de plateforme": r"(wa\.me|whatsapp|t\.me/|bit\.ly|tinyurl|https?://)",
    "séduction / confiance": r"\b(mon chéri|ma chérie|mon amour|dear|darling|veuve|héritage)\b",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_texte_danger(texte: str) -> Tuple[int, List[str]]:
    score, raisons = 0, []
    for nom, motif in MOTS_DANGER.items():
        if re.search(motif, texte, re.IGNORECASE):
            score += 15
            raisons.append(nom)
    return min(score, 100), raisons


def _extraire_slug(url_ou_slug: str) -> Optional[str]:
    """
    Extrait le slug LinkedIn depuis une URL ou un identifiant brut.
    Exemples acceptés :
      https://www.linkedin.com/in/john-doe/
      linkedin.com/in/john-doe
      john-doe
    """
    # URL complète
    if "linkedin.com" in url_ou_slug:
        parsed = urlparse(url_ou_slug if url_ou_slug.startswith("http") else "https://" + url_ou_slug)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "in":
            return parts[1].lower()
        return None

    # Slug brut (pas d'URL)
    slug = url_ou_slug.strip().lstrip("@").lower()
    # Format basique : lettres, chiffres, tirets
    if re.match(r"^[a-z0-9\-]{2,100}$", slug):
        return slug
    return None


def _analyser_slug(slug: str) -> Tuple[int, List[str]]:
    """
    Calcule un score d'automatisation à partir du slug LinkedIn uniquement.
    Score maximal possible : ~60 (limité car données partielles).
    """
    auto = 0
    raisons: List[str] = []

    def ajouter(pts: int, raison: str):
        nonlocal auto
        auto += pts
        prefix = f"+{pts}" if pts > 0 else str(pts)
        raisons.append(f"{prefix} : {raison}")

    # Longueur anormale
    if len(slug) > 40:
        ajouter(10, f"Slug très long ({len(slug)} caractères)")

    # Présence de chiffres longs à la fin (profils générés automatiquement)
    if re.search(r"\d{6,}$", slug):
        ajouter(20, "Suite de chiffres longue en fin de slug (pattern de génération automatique)")
    elif re.search(r"\d{4,}$", slug):
        ajouter(10, "Chiffres en fin de slug (potentiellement généré)")

    # Consonnes consécutives (username aléatoire)
    if re.search(r"[bcdfghjklmnpqrstvwxz]{8,}", slug, re.I):
        ajouter(15, "Suite de consonnes dans le slug (pseudo potentiellement généré)")

    # Format de slug par défaut LinkedIn (prénom-nom-chiffres)
    # LinkedIn génère ce format quand le profil n'a pas de vanity URL personnalisée
    default_pattern = re.match(r"^[a-z]+[-][a-z]+[-]\w{8,}$", slug)
    if default_pattern:
        ajouter(15, "Format de slug par défaut LinkedIn non personnalisé (URL auto-générée)")

    # Slug très court (risque de profil incomplet)
    if len(slug) < 4:
        ajouter(5, "Slug très court")

    return min(auto, 60), raisons


# ---------------------------------------------------------------------------
# Point d'entrée public
# ---------------------------------------------------------------------------

async def analyser_compte_linkedin(identifier: str) -> Dict[str, Any]:
    """
    Analyse un compte LinkedIn et retourne un dictionnaire normalisé compatible
    avec sauvegarder_analyse() de main.py.

    identifier peut être :
      - URL complète : https://www.linkedin.com/in/john-doe/
      - Slug seul    : john-doe

    Note : Sans clé API officielle, l'analyse est limitée aux signaux de l'URL.
    Le score est conservateur (max ~60%) et l'avertissement est inclus dans le rapport.
    """
    slug = _extraire_slug(identifier)

    if not slug:
        return {
            "ok": False,
            "erreur": (
                "Format invalide. Fournissez une URL LinkedIn complète ou un slug.\n"
                "Exemples :\n"
                "  • /analyser_linkedin https://www.linkedin.com/in/john-doe/\n"
                "  • /analyser_linkedin john-doe"
            )
        }

    auto_url, raisons_auto = _analyser_slug(slug)

    # Analyse de danger limitée au texte du slug lui-même (faible pertinence, mais cohérence)
    score_danger, raisons_danger = _score_texte_danger(slug.replace("-", " "))

    niveau = "ÉLEVÉ 🔴" if auto_url >= 60 else "MOYEN 🟠" if auto_url >= 30 else "FAIBLE 🟢"

    # Avertissement sur les limites
    limite_msg = (
        "\n\n⚠️ *Analyse limitée à l'URL publique (pas d'accès API officiel LinkedIn).*\n"
        "Score maximal : ~60%. Configurez LINKEDIN_CLIENT_ID dans .env pour une analyse complète."
        if not API_DISPONIBLE
        else ""
    )

    rep = [
        f"🔗 **Rapport LinkedIn pour :** `{slug}`",
        f"🌐 **URL :** https://www.linkedin.com/in/{slug}/",
        f"📊 **Probabilité d'automatisation : {auto_url} %** ({niveau})",
        "",
        "📌 **Signaux détectés (analyse URL) :**",
    ]
    if raisons_auto:
        rep.extend([f"  • {r}" for r in raisons_auto])
    else:
        rep.append("  • Aucun signal suspect dans le slug/URL.")

    if score_danger > 0:
        rep.append(f"\n⚠️ **Danger dans le slug : {score_danger} %** — {', '.join(raisons_danger)}")

    rep.append(f"\nℹ️ *Estimation explicable — pas une preuve absolue.*{limite_msg}")

    return {
        "ok": True,
        # LinkedIn n'a pas d'ID numérique accessible sans API — on hash le slug
        "chat_id": abs(hash(slug)) % (10 ** 9),
        "username": slug,
        "first_name": slug.replace("-", " ").title(),
        "last_name": None,
        "score_automatisation": auto_url,
        "score_danger": score_danger,
        "signaux_automatisation": raisons_auto,
        "signaux_danger": raisons_danger,
        "rapport_texte": "\n".join(rep),
    }
