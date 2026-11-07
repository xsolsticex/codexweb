"""Durable order receipts sent through the shop's configured SMTP account."""

import json
import logging
import os
import re
import smtplib
import ssl
import threading
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, parseaddr
from html import escape
from zoneinfo import ZoneInfo

SCHEMA = """CREATE TABLE IF NOT EXISTS order_email_outbox(
    order_id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0, next_attempt INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '', sent_at INTEGER
);"""


def valid_email(value):
    return (
        isinstance(value, str)
        and len(value) <= 254
        and bool(
            re.fullmatch(
                r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}",
                value,
            )
        )
    )


def configured():
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("MAIL_FROM"))


def euros(cents):
    return f"{cents // 100},{cents % 100:02d} €"


def receipt(order):
    customer, items = json.loads(order["customer"]), json.loads(order["items"])
    sender = os.environ["MAIL_FROM"]
    _, sender_address = parseaddr(sender)
    if not valid_email(sender_address) or "\n" in sender or "\r" in sender:
        raise ValueError("MAIL_FROM no válido")
    if not valid_email(customer["email"]):
        raise ValueError("Correo del cliente no válido")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = customer["email"]
    message["Subject"] = f"Tu pedido {order['id']} · The Beer Codex"
    message["Date"] = formatdate(order["created"], localtime=False)
    message["Message-ID"] = f"<order-{order['id']}@{sender_address.split('@')[1]}>"
    reply_to = os.environ.get("MAIL_REPLY_TO") or sender_address
    if not valid_email(reply_to):
        raise ValueError("MAIL_REPLY_TO no válido")
    message["Reply-To"] = reply_to
    subtotal = sum(item["quantity"] * item["price"] for item in items)
    shipping = order["total"] - subtotal
    date = datetime.fromtimestamp(order["created"], ZoneInfo("Europe/Madrid")).strftime(
        "%d/%m/%Y %H:%M"
    )
    lines = [
        f"{i['quantity']} × {i['name']} — {euros(i['price'])}/ud. — {euros(i['quantity'] * i['price'])}"
        for i in items
    ]
    address = f"{customer['address']}, {customer['postal']} {customer['city']}, España"
    notice = "Pendiente de pago. No se ha realizado ningún cobro. El envío se gestionará tras acordar el pago con la tienda."
    message.set_content(
        "\n".join(
            [
                "THE BEER CODEX",
                f"Hola, {customer['name']}:",
                "",
                f"Hemos registrado tu pedido {order['id']}.",
                f"Fecha: {date} (hora de Madrid)",
                "",
                *lines,
                "",
                f"Subtotal: {euros(subtotal)}",
                f"Envío: {euros(shipping)}",
                f"Total: {euros(order['total'])}",
                "",
                "DATOS DE ENTREGA",
                customer["name"],
                address,
                customer["email"],
                "",
                notice,
                "",
                "Conserva este correo. Para cualquier gestión, responde a este mensaje e indica la referencia del pedido.",
                "Este correo es un justificante del pedido, no una factura ni una confirmación de pago.",
            ]
        )
    )
    rows = "".join(
        f'<tr><td style="padding:12px 0;border-bottom:1px solid #ddd">{escape(line)}</td></tr>'
        for line in lines
    )
    message.add_alternative(
        f"""<!doctype html><html lang="es"><body style="margin:0;background:#eeece6;font-family:Arial,sans-serif;color:#242020"><main style="max-width:600px;margin:24px auto;background:#fff;padding:32px"><div style="background:#111;color:#eee;padding:22px;border-top:5px solid #c52329;font-size:22px;font-weight:bold">THE BEER CODEX</div><h1 style="font-size:25px">Tu pedido está registrado.</h1><p>Hola, {escape(customer['name'])}:</p><p>Referencia: <strong>{escape(order['id'])}</strong><br>Fecha: {date} (Madrid)</p><table style="width:100%;border-collapse:collapse">{rows}</table><p>Subtotal: {euros(subtotal)}<br>Envío: {euros(shipping)}<br><strong>Total: {euros(order['total'])}</strong></p><h2 style="font-size:18px">Datos de entrega</h2><p>{escape(customer['name'])}<br>{escape(address)}<br>{escape(customer['email'])}</p><p style="padding:16px;background:#f5e7e5">{notice}</p><p>Conserva este correo. Para cualquier gestión, responde a este mensaje e indica la referencia del pedido.</p><small>Este correo es un justificante del pedido, no una factura ni una confirmación de pago.</small></main></body></html>""",
        subtype="html",
    )
    return message


def send_receipt(order):
    message = receipt(order)
    security = os.environ.get("SMTP_SECURITY", "starttls")
    if security not in ("starttls", "ssl"):
        raise ValueError("SMTP_SECURITY debe ser starttls o ssl")
    port = int(os.environ.get("SMTP_PORT", "465" if security == "ssl" else "587"))
    username, password = os.environ.get("SMTP_USERNAME"), os.environ.get("SMTP_PASSWORD")
    if bool(username) != bool(password):
        raise ValueError("Configura usuario y contraseña SMTP juntos")
    context = ssl.create_default_context()
    if security == "ssl":
        client = smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, timeout=15, context=context)
    else:
        client = smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=15)
    with client:
        if security == "starttls":
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        if username:
            client.login(username, password)
        client.send_message(message)


def process_one(connect, transport=None):
    """Claim one queued receipt; retry later without rolling back its order."""
    if transport is None and not configured():
        return False
    now = int(time.time())
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            """SELECT o.*,q.attempts FROM order_email_outbox q JOIN orders o ON o.id=q.order_id
            WHERE q.status IN ('pending','processing') AND q.next_attempt<=?
            ORDER BY o.created,o.id LIMIT 1""",
            (now,),
        ).fetchone()
        if not row:
            return False
        order = dict(row)
        c.execute(
            "UPDATE order_email_outbox SET status='processing',next_attempt=?,attempts=attempts+1 WHERE order_id=?",
            (now + 120, order["id"]),
        )
    try:
        (transport or send_receipt)(order)
    except Exception as error:
        # Do not persist SMTP responses, credentials, or customer data in errors/logs.
        delay = min(3600, 30 * 2 ** min(order["attempts"], 7))
        with connect() as c:
            c.execute(
                "UPDATE order_email_outbox SET status='pending',next_attempt=?,last_error=? WHERE order_id=?",
                (int(time.time()) + delay, type(error).__name__, order["id"]),
            )
        logging.warning("Order receipt delivery failed (%s); retry scheduled", type(error).__name__)
    else:
        with connect() as c:
            c.execute(
                "UPDATE order_email_outbox SET status='sent',sent_at=?,last_error='' WHERE order_id=?",
                (int(time.time()), order["id"]),
            )
    return True


def start_worker(connect):
    stop = threading.Event()

    def run():
        while not stop.is_set():
            try:
                worked = process_one(connect)
            except Exception as error:
                logging.warning("Receipt worker failed (%s)", type(error).__name__)
                worked = False
            stop.wait(1 if worked else 10)

    thread = threading.Thread(target=run, name="order-receipts", daemon=True)
    thread.start()
    return stop, thread
