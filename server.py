"""
API REST et WebSockets pour le tableau de bord de détection de bots Telegram.
Expose les données de la base SQLite et permet la diffusion en direct.
"""
import ast
import asyncio
import datetime
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH = os.path.join("data", "analyses.db")

app = FastAPI(
    title="Telegram Bot Sentinel - SOC Dashboard",
    description="Plateforme de supervision et détection de bots Telegram",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        text_data = json.dumps(message)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(text_data)
            except Exception:
                if connection in self.active_connections:
                    self.active_connections.remove(connection)


ws_manager = ConnectionManager()


def parse_safe_list(val: Any) -> list:
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        parsed = ast.literal_eval(val)
        return parsed if isinstance(parsed, list) else [str(parsed)]
    except Exception:
        return [str(val)]


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/stats")
def get_stats():
    """Fournit les métriques globales pour les KPI cards et graphiques."""
    conn = get_db_connection()
    c = conn.cursor()

    total_analyses = c.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    total_bots = c.execute("SELECT COUNT(*) FROM analyses WHERE score_automatisation >= 60").fetchone()[0]
    total_suspects = c.execute("SELECT COUNT(*) FROM analyses WHERE score_automatisation >= 30 AND score_automatisation < 60").fetchone()[0]
    total_humains = c.execute("SELECT COUNT(*) FROM analyses WHERE score_automatisation < 30").fetchone()[0]
    total_dangers = c.execute("SELECT COUNT(*) FROM analyses WHERE score_danger > 0").fetchone()[0]

    # Retours humains vs bots validés
    retours_bots = c.execute("SELECT COUNT(*) FROM retours WHERE verdict = 'bot'").fetchone()[0]
    retours_humains = c.execute("SELECT COUNT(*) FROM retours WHERE verdict = 'humain'").fetchone()[0]
    retours_incertains = c.execute("SELECT COUNT(*) FROM retours WHERE verdict = 'incertain'").fetchone()[0]

    # Surveillances actives
    total_surveilles = c.execute("SELECT COUNT(*) FROM surveillances").fetchone()[0]

    # Moyennes
    avg_score_row = c.execute("SELECT AVG(score_automatisation), AVG(score_danger) FROM analyses").fetchone()
    avg_auto = round(avg_score_row[0] or 0, 1)
    avg_danger = round(avg_score_row[1] or 0, 1)

    # Historique chronologique (30 dernières analyses)
    rows_chrono = c.execute("""
        SELECT id, username, first_name, score_automatisation, score_danger, date_analyse
        FROM analyses
        ORDER BY id ASC
        LIMIT 50
    """).fetchall()

    timeline = [
        {
            "id": r["id"],
            "nom": r["username"] or r["first_name"] or f"ID {r['id']}",
            "auto": r["score_automatisation"],
            "danger": r["score_danger"],
            "date": r["date_analyse"],
        }
        for r in rows_chrono
    ]

    # Détection des principaux signaux (Top signaux)
    all_rows = c.execute("SELECT signaux_automatisation, signaux_danger FROM analyses").fetchall()
    signal_counts = {}
    for r in all_rows:
        sigs = parse_safe_list(r["signaux_automatisation"])
        for s in sigs:
            cleaned = s.split(" : ", 1)[-1] if " : " in s else s
            signal_counts[cleaned] = signal_counts.get(cleaned, 0) + 1

    top_signaux = sorted(
        [{"signal": k, "count": v} for k, v in signal_counts.items()],
        key=lambda x: x["count"],
        reverse=True
    )[:8]

    conn.close()

    return {
        "total_analyses": total_analyses,
        "total_bots": total_bots,
        "total_suspects": total_suspects,
        "total_humains": total_humains,
        "total_dangers": total_dangers,
        "total_surveilles": total_surveilles,
        "avg_automatisation": avg_auto,
        "avg_danger": avg_danger,
        "verdicts": {
            "bot": retours_bots,
            "humain": retours_humains,
            "incertain": retours_incertains,
        },
        "timeline": timeline,
        "top_signaux": top_signaux,
    }


@app.get("/api/analyses")
def get_analyses(limit: int = 50, offset: int = 0):
    """Liste détaillée de toutes les analyses avec pagination."""
    conn = get_db_connection()
    c = conn.cursor()

    rows = c.execute("""
        SELECT a.*, r.verdict as retour_verdict
        FROM analyses a
        LEFT JOIN (
            SELECT analyse_id, verdict FROM retours ORDER BY id DESC
        ) r ON a.id = r.analyse_id
        ORDER BY a.id DESC
        LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()

    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "chat_id": r["chat_id"],
            "username": r["username"],
            "first_name": r["first_name"],
            "last_name": r["last_name"],
            "score_automatisation": r["score_automatisation"],
            "score_danger": r["score_danger"],
            "signaux_automatisation": parse_safe_list(r["signaux_automatisation"]),
            "signaux_danger": parse_safe_list(r["signaux_danger"]),
            "date_analyse": r["date_analyse"],
            "retour_verdict": r["retour_verdict"],
        })

    conn.close()
    return result


@app.get("/api/analyses/{analyse_id}")
def get_analyse_detail(analyse_id: int):
    """Détail approfondi d'une analyse spécifique."""
    conn = get_db_connection()
    c = conn.cursor()
    row = c.execute("SELECT * FROM analyses WHERE id = ?", (analyse_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Analyse non trouvée")

    return {
        "id": row["id"],
        "chat_id": row["chat_id"],
        "username": row["username"],
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "score_automatisation": row["score_automatisation"],
        "score_danger": row["score_danger"],
        "signaux_automatisation": parse_safe_list(row["signaux_automatisation"]),
        "signaux_danger": parse_safe_list(row["signaux_danger"]),
        "date_analyse": row["date_analyse"],
    }


class FeedbackModel(BaseModel):
    analyse_id: int
    verdict: str


@app.post("/api/feedback")
async def save_feedback(data: FeedbackModel):
    """Enregistre une vérité terrain (humain / bot / incertain)."""
    if data.verdict not in ("humain", "bot", "incertain"):
        raise HTTPException(status_code=400, detail="Verdict invalide")

    conn = get_db_connection()
    c = conn.cursor()
    now_iso = datetime.datetime.now().isoformat()
    c.execute("""
        INSERT INTO retours (analyse_id, verdict, date_retour)
        VALUES (?, ?, ?)
    """, (data.analyse_id, data.verdict, now_iso))
    conn.commit()
    conn.close()

    # Diffuser la mise à jour via WebSocket
    await ws_manager.broadcast({
        "type": "feedback_added",
        "data": {
            "analyse_id": data.analyse_id,
            "verdict": data.verdict,
            "date": now_iso
        }
    })

    return {"status": "ok", "message": "Vérité terrain enregistrée avec succès"}


@app.get("/api/surveillances")
def get_surveillances():
    """Liste des comptes actuellement sous veille comportementale."""
    conn = get_db_connection()
    c = conn.cursor()
    rows = c.execute("SELECT * FROM surveillances ORDER BY id DESC").fetchall()
    conn.close()

    return [
        {
            "id": r["id"],
            "chat_id": r["chat_id"],
            "pseudo": r["pseudo"],
            "date_debut": r["date_debut"]
        }
        for r in rows
    ]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Flux bidirectionnel temps réel pour notifier l'interface web."""
    await ws_manager.connect(websocket)
    try:
        # Message de bienvenue avec statut
        await websocket.send_text(json.dumps({
            "type": "connected",
            "message": "Connecté au flux de détection temps réel Telegram Sentinel"
        }))
        while True:
            # Maintenir la connexion ouverte
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# Servir les fichiers statiques de l'interface web
static_dir = os.path.join(os.path.dirname(__file__), "web")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Initialisation de l'interface en cours...</h1>")
