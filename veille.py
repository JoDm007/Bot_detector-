"""
Module de veille comportementale pour le détecteur Telegram.
Mesure le rythme de réponse, la régularité (écart-type) et l'activité 24h/24.
"""
import statistics
import time
from collections import defaultdict
from typing import List, Tuple

SURVEILLES = set()                 # Ensemble des IDs des comptes surveillés
dernier_envoi = {}                 # chat_id -> timestamp de mon dernier message
delais = defaultdict(list)         # chat_id -> liste des délais de réponse en secondes
heures = defaultdict(set)          # chat_id -> ensemble des heures (0-23) où il a envoyé un message


def moi_ecris(chat_id: int) -> None:
    """Enregistre le timestamp lorsqu'on envoie un message dans un chat surveillé."""
    dernier_envoi[chat_id] = time.time()


def autre_ecrit(chat_id: int) -> None:
    """Enregistre le temps de réponse et l'heure de présence de l'interlocuteur."""
    heures[chat_id].add(time.localtime().tm_hour)
    if chat_id in dernier_envoi:
        delai = time.time() - dernier_envoi.pop(chat_id)
        delais[chat_id].append(delai)


def rapport(chat_id: int) -> Tuple[int, List[str]]:
    """
    Calcule le score comportemental (0 à 60 points) et fournit l'explication des signaux.
    """
    d = delais[chat_id]
    if len(d) < 5:
        return 0, [f"Pas assez d'échanges enregistrés ({len(d)}/5 échanges minimum)"]

    score = 0
    raisons = []

    mediane = statistics.median(d)
    ecart = statistics.pstdev(d) if len(d) > 1 else 0.0

    if mediane < 5.0:
        score += 20
        raisons.append(f"+20 : réponse quasi instantanée (médiane {mediane:.1f} s)")
    elif mediane < 15.0:
        score += 10
        raisons.append(f"+10 : délai de réponse très court (médiane {mediane:.1f} s)")

    if ecart < 3.0:
        score += 25
        raisons.append(f"+25 : régularité robotique des réponses (écart-type {ecart:.1f} s)")
    elif ecart < 7.0:
        score += 10
        raisons.append(f"+10 : délais modérément constants (écart-type {ecart:.1f} s)")

    nb_heures = len(heures[chat_id])
    if nb_heures >= 20:
        score += 15
        raisons.append(f"+15 : actif quasi 24h/24 sans pause de sommeil ({nb_heures}/24h observées)")
    elif nb_heures >= 16:
        score += 10
        raisons.append(f"+10 : plage d'activité horaire anormalement vaste ({nb_heures}/24h observées)")

    return min(score, 60), raisons
