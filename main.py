"""
Détecteur de comptes Telegram automatisés et dangereux (Socle + Veille + Défis).

Ce script fait tourner deux clients Telethon :
  - bot_client  : L'interface utilisateur Telegram (commandes /analyser, /veille, /rapport, /defi, /retour)
  - user_client : Le compte personnel de l'utilisateur (utilisé pour lire les métadonnées et surveiller le rythme)
"""
import asyncio
import csv
import datetime
import os
import re
from typing import Tuple

import aiohttp
from dotenv import load_dotenv
from telethon import TelegramClient, events, functions, types

from defis import nouveau_defi
from veille import SURVEILLES, autre_ecrit, moi_ecris, rapport as rapport_comportement

# Chargement des variables d'environnement depuis le fichier .env
load_dotenv()

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
BOT_TOKEN = os.environ["TG_BOT_TOKEN"]
OWNER_ID = int(os.environ["TG_OWNER_ID"])

bot_client = TelegramClient("session_bot", API_ID, API_HASH)
user_client = TelegramClient("session_user", API_ID, API_HASH)

# Repères approximatifs ID Telegram -> Année de création estimée
ID_REPERES = [
    (100_000_000, 2015),
    (300_000_000, 2017),
    (1_000_000_000, 2020),
    (2_000_000_000, 2021),
    (5_000_000_000, 2022),
    (6_500_000_000, 2023),
    (7_500_000_000, 2024),
    (8_500_000_000, 2025),
]

MOTS_DANGER = {
    "argent / crypto": r"\b(crypto|bitcoin|btc|usdt|investi\w*|trading|forex|virement|western union|wallet)\b",
    "promesse de gains": r"\b(gains?|profits?|rentab\w+|revenu passif|garanti|100 ?%)\b",
    "urgence": r"\b(urgent|immédiatement|dernière chance|maintenant|vite|aujourd'hui seulement)\b",
    "données sensibles": r"\b(mot de passe|code (sms|de vérification)|otp|pin|carte bancaire|iban|passeport)\b",
    "sortie de plateforme": r"(wa\.me|whatsapp|t\.me/|bit\.ly|tinyurl|https?://)",
    "séduction / confiance": r"\b(mon chéri|ma chérie|mon amour|dear|darling|veuve|héritage)\b",
}


def annee_estimee(user_id: int) -> int:
    """Estime l'année de création d'un compte d'après son ID numérique Telegram."""
    annee = 2013
    for seuil, a in ID_REPERES:
        if user_id >= seuil:
            annee = a
    return annee


async def cas_banni(user_id: int) -> bool:
    """Interroge l'API du service Combot Anti-Spam (CAS)."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.cas.chat/check?user_id={user_id}",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                data = await r.json()
                return bool(data.get("ok"))
    except Exception:
        return False


def score_texte_danger(texte: str) -> Tuple[int, list]:
    """Calcule le score de dangerosité d'un texte (bio ou message transféré)."""
    score, raisons = 0, []
    for nom, motif in MOTS_DANGER.items():
        if re.search(motif, texte, re.IGNORECASE):
            score += 15
            raisons.append(nom)
    return min(score, 100), raisons


async def analyser_compte(ident) -> str:
    """Analyse les métadonnées publiques d'un compte utilisateur Telegram."""
    ent = await user_client.get_entity(ident)
    if not isinstance(ent, types.User):
        return "⚠️ Ce n'est pas un compte utilisateur (groupe, canal ou entité non valide)."
    if ent.bot:
        return "🤖 **Bot Telegram officiel** (déclaré comme tel par l'API Telegram)."

    full = await user_client(functions.users.GetFullUserRequest(ent))
    bio = (full.full_user.about or "").strip()
    communs = full.full_user.common_chats_count or 0

    auto, raisons = 0, []

    def ajouter(points: int, raison: str):
        nonlocal auto
        auto += points
        prefix = f"+{points}" if points > 0 else str(points)
        raisons.append(f"{prefix} : {raison}")

    if getattr(ent, "scam", False) or getattr(ent, "fake", False):
        ajouter(40, "Marqué SCAM/FAKE par Telegram")
    if await cas_banni(ent.id):
        ajouter(40, "Listé dans la base anti-spam Combot (CAS)")
    if not ent.photo:
        ajouter(15, "Aucune photo de profil")
    if not bio:
        ajouter(10, "Bio (description) vide")
    if not ent.username:
        ajouter(5, "Pas d'identifiant public (@pseudo)")
    elif re.search(r"\d{4,}$", ent.username) or re.search(
        r"[bcdfghjklmnpqrstvwxz]{6,}", ent.username, re.I
    ):
        ajouter(10, "Pseudo d'allure aléatoire (suite de chiffres ou consonnes)")

    annee = annee_estimee(ent.id)
    if annee >= 2024:
        ajouter(15, f"Compte récent (création estimée ~{annee})")

    if communs == 0:
        ajouter(5, "Aucun groupe en commun avec vous")
    if isinstance(ent.status, types.UserStatusEmpty):
        ajouter(5, "Statut de présence : jamais vu en ligne")
    if getattr(ent, "premium", False):
        ajouter(-5, "Compte Telegram Premium")
    if getattr(ent, "verified", False):
        ajouter(-30, "Compte officiel vérifié")

    auto = max(0, min(auto, 100))
    danger, raisons_danger = score_texte_danger(bio)
    niveau = "ÉLEVÉ 🔴" if auto >= 60 else "MOYEN 🟠" if auto >= 30 else "FAIBLE 🟢"

    nom_affich = f"{ent.first_name or ''} {ent.last_name or ''}".strip() or "Sans Nom"
    pseudo_str = f" (@{ent.username})" if ent.username else ""

    rep = [
        f"🔎 **Rapport d'analyse pour :** {nom_affich}{pseudo_str}",
        f"🆔 **ID Telegram :** `{ent.id}` (Création estimée : ~{annee})",
        f"📊 **Probabilité d'automatisation :** **{auto} %** ({niveau})",
        "",
        "📌 **Signaux de profil détectés :**",
    ]
    if raisons:
        rep.extend([f"  • {r}" for r in raisons])
    else:
        rep.append("  • Aucun signal de risque particulier sur le profil.")

    if danger > 0:
        rep.append(
            f"\n⚠️ **Danger détecté dans la bio ({danger} %) :** {', '.join(raisons_danger)}"
        )

    rep.append(
        "\nℹ️ *Ce score est une estimation explicable et non une preuve absolue.*"
    )
    return "\n".join(rep)


# --- Handlers Telethon ---


@user_client.on(events.NewMessage)
async def veille_handler(event):
    """Intercepte les messages dans les chats surveillés pour enregistrer la télémétrie comportementale."""
    if event.chat_id not in SURVEILLES:
        return
    if event.out:
        moi_ecris(event.chat_id)
    else:
        autre_ecrit(event.chat_id)


@bot_client.on(events.NewMessage(pattern=r"^/(start|help)"))
async def start_handler(event):
    if event.sender_id != OWNER_ID:
        return
    msg = (
        "🤖 **Détecteur de Comptes Automatisés Telegram**\n\n"
        "**Commandes disponibles :**\n"
        "• `/analyser @pseudo` - Analyse le profil et calcule le score d'automatisation.\n"
        "• *(Transfert de message)* - Évalue la dangerosité du texte et l'expéditeur.\n"
        "• `/veille @pseudo` - Active la surveillance comportementale (temps de réponse).\n"
        "• `/rapport @pseudo` - Affiche le rapport comportemental du compte surveillé.\n"
        "• `/defi` - Génère une consigne ou défi anti-bot à transmettre.\n"
        "• `/retour @pseudo humain|bot` - Enregistre une vérité terrain (CSV).\n"
    )
    await event.respond(msg)


@bot_client.on(events.NewMessage(pattern=r"^/analyser\s+(\S+)"))
async def cmd_analyser(event):
    if event.sender_id != OWNER_ID:
        return
    ident = event.pattern_match.group(1)
    await event.respond(f"⏳ Analyse du compte `{ident}` en cours...")
    try:
        rapport_txt = await analyser_compte(ident)
        await event.respond(rapport_txt)
    except Exception as e:
        await event.respond(f"❌ Impossible d'analyser `{ident}` : {e}")


@bot_client.on(events.NewMessage(pattern=r"^/veille\s+(\S+)"))
async def cmd_veille(event):
    if event.sender_id != OWNER_ID:
        return
    ident = event.pattern_match.group(1)
    try:
        ent = await user_client.get_entity(ident)
        SURVEILLES.add(ent.id)
        await event.respond(
            f"👁️ **Surveillance activée pour `{ident}` (ID: {ent.id}).**\n"
            "Discutez normalement avec ce compte via votre Telegram, puis tapez `/rapport @pseudo` pour consulter la télémétrie."
        )
    except Exception as e:
        await event.respond(f"❌ Impossible d'activer la veille pour `{ident}` : {e}")


@bot_client.on(events.NewMessage(pattern=r"^/rapport\s+(\S+)"))
async def cmd_rapport(event):
    if event.sender_id != OWNER_ID:
        return
    ident = event.pattern_match.group(1)
    try:
        ent = await user_client.get_entity(ident)
        score, raisons = rapport_comportement(ent.id)
        niveau = "ÉLEVÉ 🔴" if score >= 40 else "MOYEN 🟠" if score >= 20 else "FAIBLE 🟢"
        rep = [
            f"📈 **Rapport comportemental pour :** `{ident}`",
            f"⚡ **Score de rythme de réponse :** **{score}/60** ({niveau})",
            "",
            "📌 **Signaux observés :**",
        ] + [f"  • {r}" for r in raisons]
        await event.respond("\n".join(rep))
    except Exception as e:
        await event.respond(f"❌ Erreur lors de l'établissement du rapport pour `{ident}` : {e}")


@bot_client.on(events.NewMessage(pattern=r"^/defi"))
async def cmd_defi(event):
    if event.sender_id != OWNER_ID:
        return
    challenge = nouveau_defi()
    msg = (
        "🎯 **Nouveau défi anti-bot généré !**\n\n"
        "Copiez-collez le message ci-dessous à votre interlocuteur suspect :\n"
        "───────────────\n"
        f"{challenge}\n"
        "───────────────"
    )
    await event.respond(msg)


@bot_client.on(events.NewMessage(pattern=r"^/retour\s+(\S+)\s+(humain|bot)"))
async def cmd_retour(event):
    if event.sender_id != OWNER_ID:
        return
    pseudo = event.pattern_match.group(1)
    verdict = event.pattern_match.group(2).lower()

    os.makedirs("data", exist_ok=True)
    fichier_csv = os.path.join("data", "retours.csv")
    existe = os.path.exists(fichier_csv)

    with open(fichier_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not existe:
            writer.writerow(["date_iso", "compte", "verdict"])
        writer.writerow([datetime.datetime.now().isoformat(), pseudo, verdict])

    await event.respond(f"✅ Vérité terrain enregistrée avec succès dans `data/retours.csv` pour `{pseudo}` : **{verdict.upper()}**.")


@bot_client.on(events.NewMessage(func=lambda e: e.forward is not None))
async def message_transfere(event):
    if event.sender_id != OWNER_ID:
        return
    text = event.raw_text or ""
    danger, raisons = score_texte_danger(text)
    rep = [f"📩 **Analyse du message transféré :**"]

    if danger > 0:
        rep.append(f"⚠️ **Danger du texte ({danger} %) :** {', '.join(raisons)}")
    else:
        rep.append("🟢 **Danger du texte :** 0 % (aucun mot-clé suspect repéré dans le message)")

    origine = event.forward.sender_id
    if origine:
        try:
            rep.append("\n" + await analyser_compte(origine))
        except Exception as e:
            rep.append(f"\n⚠️ Compte d'origine non analysable : {e}")
    else:
        rep.append(
            "\n🔒 *L'expéditeur original a masqué son profil dans les transferts Telegram. "
            "Utilisez `/analyser @pseudo` si vous connaissez son identifiant.*"
        )

    await event.respond("\n".join(rep))


async def main():
    print("🚀 Démarrage des clients Telegram...")
    await bot_client.start(bot_token=BOT_TOKEN)
    await user_client.start()
    print("✅ Bot et Userbot connectés avec succès. En attente de commandes...")
    await bot_client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
