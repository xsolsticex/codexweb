import json
import os
import smtplib
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import order_email


class OrderEmailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "receipts.db"
        self.env = patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.gmail.com",
                "SMTP_PORT": "587",
                "SMTP_SECURITY": "starttls",
                "SMTP_USERNAME": "shop@gmail.com",
                "SMTP_PASSWORD": "test-app-password",
                "MAIL_FROM": "The Beer Codex <shop@gmail.com>",
                "MAIL_REPLY_TO": "shop@gmail.com",
            },
        )
        self.env.start()
        self.order = {
            "id": "BC-TEST1234",
            "created": 1794038400,
            "total": 1290,
            "customer": json.dumps(
                {
                    "name": "Ana <Prueba>",
                    "email": "customer@example.com",
                    "address": "Calle Uno 2",
                    "postal": "28001",
                    "city": "Madrid",
                }
            ),
            "items": json.dumps(
                [{"id": 1, "name": "Cerveza <Lager>", "quantity": 2, "price": 400}]
            ),
            "status": "pending_payment",
        }
        with self.connect() as c:
            c.executescript(order_email.SCHEMA)
            c.execute(
                "CREATE TABLE orders(id TEXT PRIMARY KEY,created INTEGER,customer TEXT,items TEXT,total INTEGER,status TEXT)"
            )
            c.execute(
                "INSERT INTO orders VALUES(:id,:created,:customer,:items,:total,:status)",
                self.order,
            )
            c.execute("INSERT INTO order_email_outbox(order_id) VALUES(?)", (self.order["id"],))

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def connect(self):
        c = sqlite3.connect(self.db)
        c.row_factory = sqlite3.Row
        return c

    def test_receipt_has_reference_items_totals_contact_and_escaped_html(self):
        message = order_email.receipt(self.order)
        self.assertEqual(message["To"], "customer@example.com")
        self.assertEqual(message["Reply-To"], "shop@gmail.com")
        self.assertIn(self.order["id"], message["Subject"])
        text = message.get_body(preferencelist=("plain",)).get_content()
        for detail in [
            "BC-TEST1234",
            "2 × Cerveza <Lager>",
            "8,00 €",
            "4,90 €",
            "12,90 €",
            "Calle Uno 2",
            "28001 Madrid",
            "Pendiente de pago",
            "no una factura",
        ]:
            self.assertIn(detail, text)
        html = message.get_body(preferencelist=("html",)).get_content()
        self.assertIn("Ana &lt;Prueba&gt;", html)
        self.assertIn("Cerveza &lt;Lager&gt;", html)
        self.assertNotIn("Cerveza <Lager>", html)

    def test_smtp_uses_gmail_starttls_and_app_credentials(self):
        with patch("order_email.smtplib.SMTP") as smtp:
            order_email.send_receipt(self.order)
            smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
            client = smtp.return_value
            client.starttls.assert_called_once()
            client.login.assert_called_once_with("shop@gmail.com", "test-app-password")
            message = client.send_message.call_args.args[0]
            self.assertEqual(message["To"], "customer@example.com")

    def test_retry_is_durable_then_sent_receipts_are_not_sent_again(self):
        def fail(order):
            raise smtplib.SMTPException("Secret SMTP detail must not be stored")

        self.assertTrue(order_email.process_one(self.connect, fail))
        with self.connect() as c:
            state = c.execute("SELECT * FROM order_email_outbox").fetchone()
            self.assertEqual(state["status"], "pending")
            self.assertEqual(state["attempts"], 1)
            self.assertEqual(state["last_error"], "SMTPException")
            self.assertGreater(state["next_attempt"], int(time.time()))
            c.execute("UPDATE order_email_outbox SET next_attempt=0")
        sent = []
        self.assertTrue(order_email.process_one(self.connect, sent.append))
        self.assertFalse(order_email.process_one(self.connect, sent.append))
        self.assertEqual(len(sent), 1)
        with self.connect() as c:
            row = c.execute("SELECT * FROM order_email_outbox").fetchone()
            self.assertEqual(row["status"], "sent")
            self.assertEqual(row["attempts"], 2)
            self.assertTrue(row["sent_at"])

    def test_missing_configuration_preserves_queued_receipt(self):
        with patch.dict(os.environ, {"SMTP_HOST": "", "MAIL_FROM": ""}):
            with patch("order_email.send_receipt") as send:
                self.assertFalse(order_email.process_one(self.connect))
                send.assert_not_called()
        with self.connect() as c:
            self.assertEqual(c.execute("SELECT attempts FROM order_email_outbox").fetchone()[0], 0)

    def test_invalid_recipient_and_header_injection_rejected(self):
        for value in ["not-an-email", "a@example.com\nBcc:other@example.com", "a b@example.com"]:
            self.assertFalse(order_email.valid_email(value))
        with patch.dict(os.environ, {"MAIL_REPLY_TO": "bad\nBcc:other@example.com"}):
            with self.assertRaises(ValueError):
                order_email.receipt(self.order)
