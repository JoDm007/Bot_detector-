"""
Détecteur de comptes Telegram automatisés / dangereux (prototype).

Deux clients Telethon dans le même script :
  - bot_client  : l'interface (vous lui écrivez /analyser @pseudo)
  - user_client : votre propre compte, utilisé uniquement pour lire les infos publiques

Installation :  pip install telethon aiohttp
Configuration : variables d'environnement
  TG_API_ID, TG_API_HASH  -> https://my.telegram.org
  TG_BOT_TOKEN            -> créé via @BotFather
  TG_OWNER_ID             -> votre ID Telegram (seul autorisé à utiliser le bot)
"""
import asyncio
import os
import re

import aiohttp
from telethon import TelegramClient, events, functions, types

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
BOT_TOKEN = os.environ["TG_BOT_TOKEN"]
OWNER_ID = int(os.environ["TG_OWNER_ID"])

bot_client = TelegramClient("session_bot", API_ID, API_HASH)
user_client = TelegramClient("session_user", API_ID, API_HASH)

# Repères approximatifs ID -> année de création (à recalibrer avec le temps).
ID_REPERES = [(100_000_000, 2015), (300_000_000, 2017), (1_000_000_000, 2020),
              (2_000_000_000, 2021), (5_000_000_000, 2022), (6_500_000_000, 2023),
              (7_500_000_000, 2024), (8_500_000_000, 2025)]

MOTS_DANGER = {
    "argent / crypto": r"\b(crypto|bitcoin|btc|usdt|investi\w*|trading|forex|virement|western union|wallet)\b",
    "promesse de gains": r"\b(gains?|profits?|rentab\w+|revenu passif|garanti|100 ?%)\b",
    "urgence": r"\b(urgent|immédiatement|dernière chance|maintenant|vite|aujourd'hui seulement)\b",
    "données sensibles": r"\b(mot de passe|code (sms|de vérification)|otp|pin|carte bancaire|iban|passeport)\b",
    "sortie de plateforme": r"(wa\.me|whatsapp|t\.me/|bit\.ly|tinyurl|https?://)",
    "séduction / confiance": r"\b(mon chéri|ma chérie|mon amour|dear|darling|veuve|héritage)\b",
}


def annee_estimee(user_id: int) -> int:
    annee = 2013
    for seuil, a in ID_REPERES:
        if user_id >= seuil:
            annee = a
    return annee


async def cas_banni(user_id: int) -> bool:
    """Interroge la base anti-spam CAS (Combot Anti-Spam)."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://api.cas.chat/check?user_id={user_id}",
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                return bool((await r.json()).get("ok"))
    except Exception:
        return False


def score_texte_danger(texte: str):
    score, raisons = 0, []
    for nom, motif in MOTS_DANGER.items():
        if re.search(motif, texte, re.IGNORECASE):
            score += 15
            raisons.append(nom)
    return min(score, 100), raisons


async def analyser_compte(ident) -> str:
    ent = await user_client.get_entity(ident)
    if not isinstance(ent, types.User):
        return "Ce n'est pas un compte utilisateur (groupe ou canal)."
    if ent.bot:
        return "🤖 Bot Telegram officiel (déclaré comme tel par Telegram)."

    full = await user_client(functions.users.GetFullUserRequest(ent))
    bio = (full.full_user.about or "").strip()
    communs = full.full_user.common_chats_count or 0

    auto, raisons = 0, []

    def ajouter(points, raison):
        nonlocal auto
        auto += points
        raisons.append(f"{'+' if points > 0 else ''}{points} : {raison}")

    if getattr(ent, "scam", False) or getattr(ent, "fake", False):
        ajouter(40, "marqué SCAM/FAKE par Telegram")
    if await cas_banni(ent.id):
        ajouter(40, "listé dans la base anti-spam CAS")
    if not ent.photo:
        ajouter(15, "aucune photo de profil")
    if not bio:
        ajouter(10, "bio vide")
    if not ent.username:
        ajouter(5, "pas de @pseudo")
    elif re.search(r"\d{4,}$", ent.username) or re.search(r"[bcdfghjklmnpqrstvwxz]{6,}", ent.username, re.I):
        ajouter(10, "pseudo d'allure aléatoire")
    annee = annee_estimee(ent.id)
    if annee >= 2024:
        ajouter(15, f"compte récent (création estimée ~{annee})")
    if communs == 0:
        ajouter(5, "aucun groupe en commun avec vous")
    if isinstance(ent.status, types.UserStatusEmpty):
        ajouter(5, "jamais vu en ligne")
    if getattr(ent, "premium", False):
        ajouter(-5, "compte Premium")
    if getattr(ent, "verified", False):
        ajouter(-30, "compte vérifié")
    auto = max(0, min(auto, 100))

    danger, raisons_danger = score_texte_danger(bio)
    niveau = "élevé" if auto >= 60 else "moyen" if auto >= 30 else "faible"

    rep = [f"🔎 Analyse de {ident}",
           f"Automatisation probable : {auto} % ({niveau})",
           "Signaux :"] + [f"  • {r}" for r in raisons]
    if danger:
        rep.append(f"⚠️ Danger détecté dans la bio : {danger} % ({', '.join(raisons_danger)})")
    rep.append("\nCe score est une estimation, pas une preuve. Un compte peut être "
               "légitime avec un score élevé (et inversement).")
    return "\n".join(rep)


@bot_client.on(events.NewMessage(pattern=r"^/start"))
async def start(event):
    await event.respond("Envoyez /analyser @pseudo, ou transférez-moi un message suspect.")


@bot_client.on(events.NewMessage(pattern=r"^/analyser\s+(\S+)"))
async def commande_analyser(event):
    if event.sender_id != OWNER_ID:
        return
    ident = event.pattern_match.group(1)
    try:
        await event.respond(await analyser_compte(ident))
    except Exception as e:
        await event.respond(f"Impossible d'analyser {ident} : {e}")


@bot_client.on(events.NewMessage(func=lambda e: e.forward is not None))
async def message_transfere(event):
    """Analyse du texte (danger) + de l'expéditeur si son identité n'est pas masquée."""
    if event.sender_id != OWNER_ID:
        return
    danger, raisons = score_texte_danger(event.raw_text or "")
    rep = [f"Danger du message : {danger} % ({', '.join(raisons) or 'aucun signal'})"]
    origine = event.forward.sender_id
    if origine:
        try:
            rep.append(await analyser_compte(origine))
        except Exception as e:
            rep.append(f"Compte d'origine non analysable : {e}")
    else:
        rep.append("L'expéditeur masque son identité lors des transferts : "
                   "envoyez-moi son @pseudo avec /analyser.")
    await event.respond("\n\n".join(rep))


async def main():
    await bot_client.start(bot_token=BOT_TOKEN)
    await user_client.start()  # demande votre numéro et le code la 1re fois
    print("Bot en ligne.")
    await bot_client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
