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
import sqlite3
import time
from typing import Tuple, List, Optional

import aiohttp
from dotenv import load_dotenv
from telethon import TelegramClient, events, functions, types
from telethon.errors import FloodWaitError

from defis import nouveau_defi
from veille import SURVEILLES, autre_ecrit, moi_ecris, rapport as rapport_comportement

# Configuration de la base de données SQLite
DB_PATH = os.path.join("data", "analyses.db")


def get_db() -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec WAL mode et timeout pour éviter les verrous."""
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL mode = plusieurs lecteurs + 1 écrivain simultanément sans bloquer
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db() -> None:
    """Initialise la base de données avec les tables nécessaires."""
    os.makedirs("data", exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            score_automatisation INTEGER NOT NULL,
            score_danger INTEGER NOT NULL,
            signaux_automatisation TEXT NOT NULL,
            signaux_danger TEXT NOT NULL,
            date_analyse TEXT NOT NULL,
            version_regles INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS retours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analyse_id INTEGER NOT NULL,
            verdict TEXT NOT NULL CHECK(verdict IN ('humain', 'bot', 'incertain')),
            date_retour TEXT NOT NULL,
            FOREIGN KEY (analyse_id) REFERENCES analyses(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS surveillances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER UNIQUE NOT NULL,
            pseudo TEXT,
            date_debut TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parametres (
            cle TEXT PRIMARY KEY,
            valeur TEXT NOT NULL,
            description TEXT
        )
    """)

    # Paramètres par défaut
    defaults = [
        ("seuil_bot", "60", "Score minimum pour classer un compte comme bot (%)"),
        ("seuil_suspect", "30", "Score minimum pour classer un compte comme suspect (%)"),
        ("cas_active", "1", "Interroger la base CAS lors des analyses (1=oui, 0=non)"),
        ("dashboard_port", "8000", "Port du dashboard web"),
        ("version_regles", "1", "Version actuelle du moteur de règles"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO parametres (cle, valeur, description) VALUES (?, ?, ?)",
        defaults
    )

    conn.commit()
    conn.close()


def sauvegarder_analyse(
    chat_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    score_automatisation: int,
    score_danger: int,
    signaux_automatisation: List[str],
    signaux_danger: List[str]
) -> int:
    """Sauvegarde une analyse dans la base de données et renvoie l'ID."""
    conn = get_db()
    cursor = conn.cursor()

    date_iso = datetime.datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO analyses
        (chat_id, username, first_name, last_name, score_automatisation, score_danger,
         signaux_automatisation, signaux_danger, date_analyse)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chat_id, username, first_name, last_name,
        score_automatisation, score_danger,
        str(signaux_automatisation), str(signaux_danger), date_iso
    ))

    analyse_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Notifier les clients WebSocket du dashboard
    try:
        from server import ws_manager
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(ws_manager.broadcast({
                "type": "new_analysis",
                "data": {
                    "id": analyse_id, "chat_id": chat_id, "username": username,
                    "first_name": first_name, "score_automatisation": score_automatisation,
                    "score_danger": score_danger, "date_analyse": date_iso
                }
            }))
    except Exception:
        pass

    return analyse_id


def recuperer_analyse(analyse_id: int) -> Optional[dict]:
    """Récupère une analyse par son ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analyses WHERE id = ?", (analyse_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row["id"], "chat_id": row["chat_id"], "username": row["username"],
            "first_name": row["first_name"], "last_name": row["last_name"],
            "score_automatisation": row["score_automatisation"],
            "score_danger": row["score_danger"],
            "signaux_automatisation": eval(row["signaux_automatisation"]),
            "signaux_danger": eval(row["signaux_danger"]),
            "date_analyse": row["date_analyse"],
        }
    return None


def sauvegarder_retour(analyse_id: int, verdict: str) -> None:
    """Enregistre le retour de l'utilisateur (humain/bot)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO retours (analyse_id, verdict, date_retour) VALUES (?, ?, ?)",
        (analyse_id, verdict, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def ajouter_surveillance(chat_id: int, pseudo: Optional[str]) -> None:
    """Ajoute un chat à la liste des surveillés."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO surveillances (chat_id, pseudo, date_debut) VALUES (?, ?, ?)",
        (chat_id, pseudo, datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def recuperer_surveilles() -> List[int]:
    """Récupère la liste des IDs de chats surveillés."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM surveillances")
    rows = cursor.fetchall()
    conn.close()
    return [row["chat_id"] for row in rows]


def get_parametre(cle: str) -> Optional[str]:
    """Lit un paramètre depuis la base."""
    conn = get_db()
    cursor = conn.cursor()
    row = cursor.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
    conn.close()
    return row["valeur"] if row else None


def set_parametre(cle: str, valeur: str) -> None:
    """Met à jour un paramètre dans la base."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE parametres SET valeur = ? WHERE cle = ?", (valeur, cle))
    conn.commit()
    conn.close()

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


async def cas_banni(user_id: int, max_retries: int = 3) -> bool:
    """Interroge l'API du service Combot Anti-Spam (CAS) avec gestion d'erreurs."""
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://api.cas.chat/check?user_id={user_id}",
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    # Gestion du taux limité (FloodTooManyErrors)
                    if r.status == 429:
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1 * (2 ** attempt))  # retry exponentiel
                            continue
                        return False
                    data = await r.json()
                    return bool(data.get("ok"))
        except asyncio.TimeoutError:
            return False
        except aiohttp.ClientError:
            return False
        except FloodWaitError as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(e.seconds if hasattr(e, 'seconds') else 5)
                continue
            return False
        except Exception:
            return False
    return False


def score_texte_danger(texte: str) -> Tuple[int, list]:
    """Calcule le score de dangerosité d'un texte (bio ou message transféré)."""
    score, raisons = 0, []
    for nom, motif in MOTS_DANGER.items():
        if re.search(motif, texte, re.IGNORECASE):
            score += 15
            raisons.append(nom)
    return min(score, 100), raisons


def est_bot_par_username(username: Optional[str]) -> bool:
    """Retourne True si le pseudo respecte la convention Telegram des bots officiels (_bot en fin)."""
    if not username:
        return False
    return username.lower().endswith("bot")


async def analyser_compte(ident) -> str:
    """Analyse les métadonnées publiques d'un compte utilisateur Telegram."""
    ent = await user_client.get_entity(ident)
    if not isinstance(ent, types.User):
        return "⚠️ Ce n'est pas un compte utilisateur (groupe ou canal)."

    # Bot officiel via l'API Telegram
    if ent.bot:
        return (
            f"🤖 Bot Telegram officiel — @{ent.username or ent.id}\n"
            "Créé via @BotFather. Pas un userbot suspect."
        )

    # Convention de nommage Telegram : tous les bots finissent par "bot"
    if est_bot_par_username(ent.username):
        return (
            f"🤖 Bot Telegram officiel (convention de nommage)\n"
            f"Le pseudo @{ent.username} se termine par « bot », "
            "ce qui est une règle imposée par @BotFather pour tous les bots déclarés.\n"
            "Pas un userbot suspect."
        )

    full = await user_client(functions.users.GetFullUserRequest(ent))
    bio = (full.full_user.about or "").strip()

    # GetCommonChats est plus fiable que common_chats_count (qui dépend de la visibilité mutuelle)
    try:
        common_result = await user_client(functions.messages.GetCommonChatsRequest(user_id=ent, max_id=0, limit=100))
        communs = len(common_result.chats)
    except Exception:
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
    await event.respond(f"⏳ Analyse de `{ident}` en cours...")
    try:
        ent = await user_client.get_entity(ident)

        # Bot officiel détecté par l'API
        if getattr(ent, "bot", False):
            await event.respond(
                f"🤖 Bot Telegram officiel — @{ent.username or ent.id}\n"
                "Créé via @BotFather. Pas un userbot suspect."
            )
            return

        # Bot officiel détecté par la convention de nommage (_bot en fin de pseudo)
        if est_bot_par_username(ent.username):
            await event.respond(
                f"🤖 Bot Telegram officiel (convention de nommage)\n"
                f"@{ent.username} se termine par « bot » — règle imposée par @BotFather.\n"
                "Pas un userbot suspect."
            )
            return

        # Récupérer les métadonnées
        full = await user_client(functions.users.GetFullUserRequest(ent))
        bio = (full.full_user.about or "").strip()

        # GetCommonChats est plus fiable que common_chats_count (qui dépend de la visibilité mutuelle)
        try:
            common_result = await user_client(functions.messages.GetCommonChatsRequest(user_id=ent, max_id=0, limit=100))
            communs = len(common_result.chats)
        except Exception:
            communs = full.full_user.common_chats_count or 0

        # Calculer les scores
        auto, raisons_auto = 0, []
        danger, raisons_danger = score_texte_danger(bio)

        def ajouter(points: int, raison: str):
            nonlocal auto
            auto += points
            prefix = f"+{points}" if points > 0 else str(points)
            raisons_auto.append(f"{prefix} : {raison}")

        if getattr(ent, "scam", False) or getattr(ent, "fake", False):
            ajouter(40, "Marqué SCAM/FAKE par Telegram")
        if await cas_banni(ent.id):
            ajouter(40, "Listé dans la base anti-spam Combot (CAS)")
        if not ent.photo:
            ajouter(15, "Aucune photo de profil")
        if not bio:
            ajouter(10, "Bio vide")
        if not ent.username:
            ajouter(5, "Pas de @pseudo public")
        elif re.search(r"\d{4,}$", ent.username) or re.search(
            r"[bcdfghjklmnpqrstvwxz]{6,}", ent.username, re.I
        ):
            ajouter(10, "Pseudo d'allure aléatoire")

        annee = annee_estimee(ent.id)
        if annee >= 2024:
            ajouter(15, f"Compte récent (~{annee})")

        if communs == 0:
            ajouter(5, "Aucun groupe en commun")
        if isinstance(ent.status, types.UserStatusEmpty):
            ajouter(5, "Jamais vu en ligne")
        if getattr(ent, "premium", False):
            ajouter(-5, "Compte Premium")
        if getattr(ent, "verified", False):
            ajouter(-30, "Compte vérifié")

        auto = max(0, min(auto, 100))

        # Sauvegarder dans la base de données
        sauvegarder_analyse(
            chat_id=ent.id,
            username=ent.username,
            first_name=ent.first_name,
            last_name=ent.last_name,
            score_automatisation=auto,
            score_danger=danger,
            signaux_automatisation=raisons_auto,
            signaux_danger=raisons_danger
        )

        # Générer le rapport (format concis)
        niveau = "ÉLEVÉ 🔴" if auto >= 60 else "MOYEN 🟠" if auto >= 30 else "FAIBLE 🟢"
        nom_affich = f"{ent.first_name or ''} {ent.last_name or ''}".strip() or "Sans Nom"
        pseudo_str = f" (@{ent.username})" if ent.username else ""

        rep = [
            f"🔎 {nom_affich}{pseudo_str} — ID `{ent.id}` (~{annee})",
            f"📊 Automatisation : {auto}% {niveau}",
        ]
        if raisons_auto:
            rep.append("Signaux : " + " · ".join(
                r.split(" : ", 1)[-1] for r in raisons_auto
            ))
        else:
            rep.append("Aucun signal suspect sur le profil.")

        if danger > 0:
            rep.append(f"⚠️ Danger (bio) : {danger}% — {', '.join(raisons_danger)}")

        rep.append("ℹ️ Estimation, pas une preuve.")

        await event.respond("\n".join(rep))
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


def find_free_port(start: int = 8000, end: int = 8020) -> int:
    """Trouve le premier port libre dans la plage donnée."""
    import socket
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start  # Fallback


def start_web_server() -> int:
    """Démarre le serveur web FastAPI du dashboard en arrière-plan. Retourne le port utilisé."""
    import uvicorn
    import threading

    port = find_free_port(8000, 8020)

    def _run():
        uvicorn.run("server:app", host="127.0.0.1", port=port, log_level="warning")

    thread = threading.Thread(target=_run, daemon=True, name="uvicorn-dashboard")
    thread.start()
    return port


async def main():
    print("🚀 Démarrage des clients Telegram...")
    init_db()
    print("✅ Base de données SQLite initialisée (WAL mode actif)")

    port = start_web_server()
    # Laisser le temps au serveur de démarrer
    await asyncio.sleep(1)
    print(f"🌐 Dashboard SOC actif sur : http://127.0.0.1:{port}")

    await bot_client.start(bot_token=BOT_TOKEN)
    await user_client.start()
    print("✅ Bot et Userbot connectés avec succès. En attente de commandes...")
    await bot_client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
