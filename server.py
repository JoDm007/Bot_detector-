"""
API REST et WebSockets pour le dashboard de détection de bots Telegram.
Expose les données de la base SQLite et permet la diffusion en temps réel.
"""
import ast
import asyncio
import datetime
import json
import os
import sqlite3
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH = os.path.join("data", "analyses.db")

app = FastAPI(
    title="Telegram Bot Sentinel - SOC Dashboard",
    description="Plateforme de supervision et détection de bots Telegram",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Connexion SQLite avec WAL mode (évite database is locked)
# ---------------------------------------------------------------------------
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


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


# ---------------------------------------------------------------------------
# WebSocket Manager (temps réel)
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket) if hasattr(self.active_connections, 'discard') else (
            self.active_connections.remove(websocket) if websocket in self.active_connections else None
        )

    async def broadcast(self, message: dict):
        text_data = json.dumps(message)
        dead = []
        for conn in list(self.active_connections):
            try:
                await conn.send_text(text_data)
            except Exception:
                dead.append(conn)
        for conn in dead:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


ws_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Endpoints API
# ---------------------------------------------------------------------------

@app.get("/api/stats")
def get_stats():
    """Métriques globales pour les KPI cards et graphiques."""
    conn = get_db()
    c = conn.cursor()

    total_analyses = c.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    total_bots     = c.execute("SELECT COUNT(*) FROM analyses WHERE score_automatisation >= 60").fetchone()[0]
    total_suspects = c.execute("SELECT COUNT(*) FROM analyses WHERE score_automatisation >= 30 AND score_automatisation < 60").fetchone()[0]
    total_humains  = c.execute("SELECT COUNT(*) FROM analyses WHERE score_automatisation < 30").fetchone()[0]
    total_dangers  = c.execute("SELECT COUNT(*) FROM analyses WHERE score_danger > 0").fetchone()[0]

    retours_bots      = c.execute("SELECT COUNT(*) FROM retours WHERE verdict = 'bot'").fetchone()[0]
    retours_humains   = c.execute("SELECT COUNT(*) FROM retours WHERE verdict = 'humain'").fetchone()[0]
    retours_incertains= c.execute("SELECT COUNT(*) FROM retours WHERE verdict = 'incertain'").fetchone()[0]

    total_surveilles  = c.execute("SELECT COUNT(*) FROM surveillances").fetchone()[0]

    avg_row = c.execute("SELECT AVG(score_automatisation), AVG(score_danger) FROM analyses").fetchone()
    avg_auto   = round(avg_row[0] or 0, 1)
    avg_danger = round(avg_row[1] or 0, 1)

    rows_chrono = c.execute("""
        SELECT id, username, first_name, score_automatisation, score_danger, date_analyse
        FROM analyses ORDER BY id ASC LIMIT 50
    """).fetchall()

    timeline = [
        {
            "id": r["id"],
            "nom": r["username"] or r["first_name"] or f"#{r['id']}",
            "auto": r["score_automatisation"],
            "danger": r["score_danger"],
            "date": r["date_analyse"],
        }
        for r in rows_chrono
    ]

    all_rows = c.execute("SELECT signaux_automatisation FROM analyses").fetchall()
    signal_counts: dict = {}
    for r in all_rows:
        for s in parse_safe_list(r["signaux_automatisation"]):
            cleaned = s.split(" : ", 1)[-1] if " : " in s else s
            signal_counts[cleaned] = signal_counts.get(cleaned, 0) + 1

    top_signaux = sorted(
        [{"signal": k, "count": v} for k, v in signal_counts.items()],
        key=lambda x: x["count"], reverse=True
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
        "verdicts": {"bot": retours_bots, "humain": retours_humains, "incertain": retours_incertains},
        "timeline": timeline,
        "top_signaux": top_signaux,
    }


@app.get("/api/analyses")
def get_analyses(limit: int = 50, offset: int = 0):
    """Liste paginée des analyses."""
    conn = get_db()
    c = conn.cursor()
    rows = c.execute("""
        SELECT a.*, r.verdict as retour_verdict
        FROM analyses a
        LEFT JOIN (SELECT analyse_id, verdict FROM retours ORDER BY id DESC) r ON a.id = r.analyse_id
        ORDER BY a.id DESC LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    conn.close()

    return [
        {
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
        }
        for r in rows
    ]


@app.get("/api/analyses/{analyse_id}")
def get_analyse_detail(analyse_id: int):
    """Détail d'une analyse."""
    conn = get_db()
    row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analyse_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Analyse non trouvée")
    return {
        "id": row["id"], "chat_id": row["chat_id"], "username": row["username"],
        "first_name": row["first_name"], "last_name": row["last_name"],
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
    """Enregistre une vérité terrain."""
    if data.verdict not in ("humain", "bot", "incertain"):
        raise HTTPException(status_code=400, detail="Verdict invalide")
    conn = get_db()
    now = datetime.datetime.now().isoformat()
    conn.execute(
        "INSERT INTO retours (analyse_id, verdict, date_retour) VALUES (?, ?, ?)",
        (data.analyse_id, data.verdict, now)
    )
    conn.commit()
    conn.close()

    await ws_manager.broadcast({
        "type": "feedback_added",
        "data": {"analyse_id": data.analyse_id, "verdict": data.verdict, "date": now}
    })
    return {"status": "ok", "message": "Vérité terrain enregistrée"}


@app.get("/api/surveillances")
def get_surveillances():
    """Liste des comptes sous veille comportementale."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM surveillances ORDER BY id DESC").fetchall()
    conn.close()
    return [{"id": r["id"], "chat_id": r["chat_id"], "pseudo": r["pseudo"], "date_debut": r["date_debut"]} for r in rows]


@app.get("/api/parametres")
def get_parametres():
    """Liste tous les paramètres configurables."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM parametres ORDER BY cle").fetchall()
    conn.close()
    return [{"cle": r["cle"], "valeur": r["valeur"], "description": r["description"]} for r in rows]


class ParamUpdate(BaseModel):
    valeur: str


@app.put("/api/parametres/{cle}")
async def update_parametre(cle: str, data: ParamUpdate):
    """Met à jour un paramètre."""
    conn = get_db()
    row = conn.execute("SELECT cle FROM parametres WHERE cle = ?", (cle,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Paramètre inconnu")
    conn.execute("UPDATE parametres SET valeur = ? WHERE cle = ?", (data.valeur, cle))
    conn.commit()
    conn.close()
    await ws_manager.broadcast({"type": "param_updated", "data": {"cle": cle, "valeur": data.valeur}})
    return {"status": "ok", "cle": cle, "valeur": data.valeur}


@app.delete("/api/analyses/{analyse_id}")
def delete_analyse(analyse_id: int):
    """Supprime une analyse (droit à l'oubli RGPD)."""
    conn = get_db()
    conn.execute("DELETE FROM retours WHERE analyse_id = ?", (analyse_id,))
    conn.execute("DELETE FROM analyses WHERE id = ?", (analyse_id,))
    conn.commit()
    conn.close()
    return {"status": "ok", "deleted": analyse_id}


# ---------------------------------------------------------------------------
# WebSocket temps réel
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps({"type": "connected", "message": "Connecté au flux temps réel"}))
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Interface Web statique
# ---------------------------------------------------------------------------
static_dir = os.path.join(os.path.dirname(__file__), "web")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
@app.get("/analyses", response_class=HTMLResponse)
@app.get("/surveillances", response_class=HTMLResponse)
@app.get("/parametres", response_class=HTMLResponse)
def serve_spa():
    """Sert le SPA (Single Page App) pour toutes les routes front-end."""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Initialisation de l'interface en cours...</h1>")
