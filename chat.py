"""Persistent customer support conversations, isolated by an anonymous cookie."""

import secrets
import time
import re
from http.cookies import SimpleCookie

SCHEMA = """CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, created INTEGER NOT NULL, closed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY, conversation TEXT NOT NULL, sender TEXT NOT NULL, text TEXT NOT NULL, created INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS chat_messages_conversation ON chat_messages(conversation, id);"""


def handle(handler, route, connect):
    admin_route = route.startswith("/api/admin/chats")
    if admin_route and not handler.admin():
        handler.send_json(401, {"error": "Inicia sesión"})
        return
    cookie = SimpleCookie(handler.headers.get("Cookie", ""))
    token = cookie.get("support")
    cid = token.value if token and re.fullmatch(r"[a-f0-9]{64}", token.value) else None
    with connect() as c:
        if admin_route:
            if route == "/api/admin/chats" and handler.command == "GET":
                rows = c.execute(
                    """SELECT c.id,c.created,c.closed,(SELECT text FROM chat_messages WHERE conversation=c.id ORDER BY id DESC LIMIT 1) AS preview,
                (SELECT sender FROM chat_messages WHERE conversation=c.id ORDER BY id DESC LIMIT 1) AS last_sender
                FROM conversations c ORDER BY (SELECT max(id) FROM chat_messages WHERE conversation=c.id) DESC LIMIT 100"""
                )
                return handler.send_json(200, [dict(r) for r in rows])
            cid = route.removeprefix("/api/admin/chats/")
        elif route != "/api/chat":
            return handler.send_json(404, {"error": "No encontrado"})
        exists = cid and c.execute("SELECT closed FROM conversations WHERE id=?", (cid,)).fetchone()
        if admin_route and not exists:
            return handler.send_json(404, {"error": "Conversación no encontrada"})
        if handler.command == "DELETE":
            if not admin_route:
                return handler.send_json(405, {"error": "Método no permitido"})
            c.execute("BEGIN IMMEDIATE")
            current = c.execute("SELECT closed FROM conversations WHERE id=?", (cid,)).fetchone()
            if not current or not current["closed"]:
                return handler.send_json(
                    409, {"error": "Solo se pueden eliminar conversaciones finalizadas."}
                )
            c.execute("DELETE FROM chat_messages WHERE conversation=?", (cid,))
            c.execute("DELETE FROM conversations WHERE id=?", (cid,))
            c.commit()
            return handler.send_json(200, {"ok": True})
        if handler.command == "GET":
            rows = c.execute(
                "SELECT id,sender,text,created FROM chat_messages WHERE conversation=? ORDER BY id DESC LIMIT 200",
                (cid,),
            )
            return handler.send_json(
                200,
                {
                    "messages": list(reversed([dict(r) for r in rows])),
                    "closed": bool(exists and exists["closed"]),
                },
            )
        if handler.command != "POST":
            return handler.send_json(405, {"error": "Método no permitido"})
        data = handler.body()
        action = data.get("action")
        if action == "close":
            if not exists:
                return handler.send_json(404, {"error": "Conversación no encontrada"})
            c.execute("UPDATE conversations SET closed=1 WHERE id=?", (cid,))
            c.commit()
            return handler.send_json(200, {"ok": True})
        if action == "new":
            if admin_route or (exists and not exists["closed"]):
                return handler.send_json(409, {"error": "Finaliza primero la conversación actual."})
            cid = secrets.token_hex(32)
            c.execute("INSERT INTO conversations(id,created) VALUES(?,?)", (cid, int(time.time())))
            c.commit()
            return handler.send_json(201, {"ok": True}, cookie=support_cookie(cid))
        if exists and exists["closed"]:
            return handler.send_json(
                409, {"error": "Esta conversación ha finalizado. Inicia una nueva consulta."}
            )
        text = data.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            return handler.send_json(400, {"error": "Escribe un mensaje de hasta 2000 caracteres."})
        c.execute("BEGIN IMMEDIATE")
        if not admin_route and exists:
            last = c.execute(
                "SELECT max(created) FROM chat_messages WHERE conversation=? AND sender='customer'",
                (cid,),
            ).fetchone()[0]
            if last and time.time() - last < 2:
                return handler.send_json(
                    429, {"error": "Espera unos segundos antes de enviar otro mensaje."}
                )
        new_cookie = None
        if not exists:
            cid = secrets.token_hex(32)
            c.execute("INSERT INTO conversations(id,created) VALUES(?,?)", (cid, int(time.time())))
            new_cookie = support_cookie(cid)
        c.execute(
            "INSERT INTO chat_messages(conversation,sender,text,created) VALUES(?,?,?,?)",
            (cid, "admin" if admin_route else "customer", text.strip(), int(time.time())),
        )
    handler.send_json(201, {"ok": True}, cookie=new_cookie)


def support_cookie(cid):
    import os

    return f"support={cid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000" + (
        "; Secure" if os.environ.get("COOKIE_SECURE") == "1" else ""
    )
