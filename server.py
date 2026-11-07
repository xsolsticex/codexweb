import json, os, sqlite3, secrets, hashlib, hmac, time, base64, io, re, warnings
from PIL import Image, UnidentifiedImageError
from chat import SCHEMA as CHAT_SCHEMA, handle as handle_chat
from catalog_import import import_once
from photo_catalog import apply_photos, catalog_image_exists, with_photo_credit
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from http.cookies import SimpleCookie

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("DATA_DIR", ROOT / ".data"))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "shop.db"
CATALOG_PATH = ROOT / "static" / "data" / "beers.json"
SESSIONS = {}
MAX_IMAGE_BYTES = 4 * 1024 * 1024


def product_image(data):
    if not isinstance(data, str):
        raise ValueError("Imagen no válida")
    try:
        raw = base64.b64decode(data, validate=True)
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("Imagen demasiado grande")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if (
                    image.format not in ("JPEG", "PNG", "WEBP")
                    or image.width * image.height > 16000000
                ):
                    raise ValueError("Formato o tamaño de imagen no válido")
                image.load()
                image = image.convert("RGBA")
                image.thumbnail((1600, 1600))
                output = io.BytesIO()
                image.save(output, format="WEBP", quality=85)
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError("Imagen no válida") from error
    uploads = DATA / "uploads"
    uploads.mkdir(exist_ok=True)
    name = secrets.token_hex(16) + ".webp"
    (uploads / name).write_bytes(output.getvalue())
    return "/uploads/" + name


def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def initialize():
    with connect() as c:
        c.executescript(CHAT_SCHEMA)
        if "closed" not in [r["name"] for r in c.execute("PRAGMA table_info(conversations)")]:
            c.execute("ALTER TABLE conversations ADD COLUMN closed INTEGER NOT NULL DEFAULT 0")
        c.executescript(
            """CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, brewery TEXT NOT NULL, style TEXT NOT NULL, price INTEGER NOT NULL, stock INTEGER NOT NULL, abv REAL NOT NULL, volume INTEGER NOT NULL, description TEXT NOT NULL, color TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, created INTEGER, customer TEXT, items TEXT, total INTEGER, status TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);"""
        )
        if "image" not in [r["name"] for r in c.execute("PRAGMA table_info(products)")]:
            c.execute("ALTER TABLE products ADD COLUMN image TEXT NOT NULL DEFAULT ''")
        if "abv_label" not in [r["name"] for r in c.execute("PRAGMA table_info(products)")]:
            c.execute("ALTER TABLE products ADD COLUMN abv_label TEXT NOT NULL DEFAULT ''")
        if not c.execute("SELECT 1 FROM settings WHERE key='seeded'").fetchone():
            beers = [
                (
                    "Bruma Atlántica",
                    "Costa Norte",
                    "IPA",
                    395,
                    48,
                    6.2,
                    330,
                    "Cítrica, aromática y con un final fresco. Lúpulos que saben a escapada al norte.",
                    "#d79b36",
                ),
                (
                    "Trigo de Sol",
                    "La Huerta",
                    "Weissbier",
                    320,
                    32,
                    5.1,
                    500,
                    "Trigo suave, notas de plátano y un toque de clavo. El sol, en una botella.",
                    "#edbd61",
                ),
                (
                    "Medianoche",
                    "Malta Negra",
                    "Stout",
                    450,
                    24,
                    7.0,
                    330,
                    "Malta tostada, cacao y café. Una cerveza para disfrutar sin mirar el reloj.",
                    "#47302a",
                ),
                (
                    "La de Siempre",
                    "Sierra Clara",
                    "Lager",
                    280,
                    60,
                    4.8,
                    330,
                    "Dorada, ligera y honesta. Tu nueva favorita para las pequeñas celebraciones.",
                    "#d9ae4c",
                ),
                (
                    "Bosque Adentro",
                    "Lúpulo Salvaje",
                    "Pale Ale",
                    375,
                    36,
                    5.5,
                    330,
                    "Pino, fruta de hueso y el equilibrio perfecto entre malta y lúpulo.",
                    "#b76c36",
                ),
                (
                    "Roja de Otoño",
                    "Tierra Roja",
                    "Amber Ale",
                    390,
                    18,
                    5.8,
                    330,
                    "Caramelo, pan recién hecho y un bonito color cobrizo. Puro confort.",
                    "#a54c2e",
                ),
            ]
            c.executemany(
                "INSERT INTO products(name,brewery,style,price,stock,abv,volume,description,color) VALUES(?,?,?,?,?,?,?,?,?)",
                beers,
            )
            c.execute("INSERT INTO settings VALUES('seeded','1')")
        import_once(c, CATALOG_PATH)
        apply_photos(c)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "static"), **kw)

    def send_json(self, status, value, cookie=None):
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size < 0 or size > 6 * 1024 * 1024:
            raise ValueError("Solicitud demasiado grande")
        return json.loads(self.rfile.read(size))

    def admin(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookie.get("session")
        return token and SESSIONS.get(token.value, 0) > time.time()

    def do_GET(self):
        route = self.path.split("?")[0]
        if route == "/api/chat" or route.startswith("/api/admin/chats"):
            return handle_chat(self, route, connect)
        if route.startswith("/uploads/"):
            if not re.fullmatch(r"/uploads/[a-f0-9]{32}\.webp", route):
                return self.send_error(404)
            path = DATA / "uploads" / route.rsplit("/", 1)[-1]
            if not path.is_file():
                return self.send_error(404)
            raw = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/webp")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if route == "/api/products":
            with connect() as c:
                products = [
                    with_photo_credit(dict(r))
                    for r in c.execute("SELECT * FROM products ORDER BY id")
                ]
            return self.send_json(200, products)
        if route == "/api/session":
            return self.send_json(
                200,
                {
                    "authenticated": bool(self.admin()),
                    "configured": bool(os.environ.get("ADMIN_PASSWORD")),
                },
            )
        if route == "/api/orders":
            if not self.admin():
                return self.send_json(401, {"error": "Inicia sesión"})
            with connect() as c:
                rows = [dict(r) for r in c.execute("SELECT * FROM orders ORDER BY created DESC")]
            return self.send_json(200, rows)
        if route.startswith("/api/"):
            return self.send_json(404, {"error": "No encontrado"})
        if route in ("/", "/admin", "/index.html"):
            self.path = "/html/index.html"
        return super().do_GET()

    def do_POST(self):
        self.mutate()

    def do_PUT(self):
        self.mutate()

    def do_DELETE(self):
        self.mutate()

    def mutate(self):
        origin = self.headers.get("Origin")
        if origin and origin.split("://")[-1] != self.headers.get("Host"):
            return self.send_json(403, {"error": "Origen no permitido"})
        try:
            route = self.path
            if route == "/api/chat" or route.startswith("/api/admin/chats"):
                return handle_chat(self, route, connect)
            if route == "/api/login" and self.command == "POST":
                data = self.body()
                expected = os.environ.get("ADMIN_PASSWORD", "")
                if not expected:
                    return self.send_json(
                        503,
                        {
                            "error": "Configura ADMIN_PASSWORD en el servidor para activar la administración."
                        },
                    )
                if not hmac.compare_digest(str(data.get("password", "")), expected):
                    time.sleep(0.5)
                    return self.send_json(401, {"error": "Contraseña incorrecta"})
                token = secrets.token_urlsafe(32)
                SESSIONS[token] = time.time() + 28800
                self.send_response(200)
                self.send_header(
                    "Set-Cookie",
                    f"session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800"
                    + ("; Secure" if os.environ.get("COOKIE_SECURE") == "1" else ""),
                )
                self.end_headers()
                return
            if route == "/api/logout":
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
                if cookie.get("session"):
                    SESSIONS.pop(cookie["session"].value, None)
                self.send_response(200)
                self.send_header(
                    "Set-Cookie", "session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
                )
                self.end_headers()
                return
            if route == "/api/orders" and self.command == "POST":
                d = self.body()
                customer = d.get("customer", {})
                items = d.get("items", [])
                if d.get("adult") is not True:
                    raise ValueError("Debes confirmar que eres mayor de 18 años")
                if any(
                    not isinstance(customer.get(k), str)
                    or not customer[k].strip()
                    or len(customer[k]) > 300
                    for k in ["name", "email", "address", "city", "postal"]
                ):
                    raise ValueError("Completa tus datos de envío")
                if (
                    "@" not in customer["email"]
                    or not customer["postal"].isdigit()
                    or len(customer["postal"]) != 5
                ):
                    raise ValueError("Revisa el correo y el código postal")
                if not isinstance(items, list) or not items or len(items) > 100:
                    raise ValueError("El carrito está vacío o es demasiado grande")
                quantities = {}
                for i in items:
                    pid = int(i["id"])
                    qty = i["quantity"]
                    if type(qty) != int or qty < 1 or qty > 99:
                        raise ValueError("Cantidad no válida")
                    quantities[pid] = quantities.get(pid, 0) + qty
                with connect() as c:
                    c.execute("BEGIN IMMEDIATE")
                    lines = []
                    subtotal = 0
                    for pid, qty in quantities.items():
                        p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
                        if not p or p["stock"] < qty:
                            raise ValueError("Stock insuficiente. Revisa el carrito.")
                        lines.append(
                            {"id": pid, "name": p["name"], "quantity": qty, "price": p["price"]}
                        )
                        subtotal += p["price"] * qty
                        c.execute("UPDATE products SET stock=stock-? WHERE id=?", (qty, pid))
                    total = subtotal + (0 if subtotal >= 6000 else 490)
                    oid = "BC-" + secrets.token_hex(4).upper()
                    c.execute(
                        "INSERT INTO orders VALUES(?,?,?,?,?,?)",
                        (
                            oid,
                            int(time.time()),
                            json.dumps(customer),
                            json.dumps(lines),
                            total,
                            "pending_payment",
                        ),
                    )
                return self.send_json(201, {"id": oid, "total": total, "status": "pending_payment"})
            if not self.admin():
                return self.send_json(401, {"error": "Inicia sesión"})
            if route.startswith("/api/orders/") and self.command == "DELETE":
                oid = route.removeprefix("/api/orders/")
                with connect() as c:
                    c.execute("BEGIN IMMEDIATE")
                    order = c.execute(
                        "SELECT items,status FROM orders WHERE id=?", (oid,)
                    ).fetchone()
                    if not order:
                        return self.send_json(404, {"error": "Pedido no encontrado"})
                    if order["status"] != "pending_payment":
                        return self.send_json(
                            409, {"error": "Solo se pueden eliminar pedidos pendientes de pago."}
                        )
                    for item in json.loads(order["items"]):
                        c.execute(
                            "UPDATE products SET stock=stock+? WHERE id=?",
                            (item["quantity"], item["id"]),
                        )
                    c.execute("DELETE FROM orders WHERE id=?", (oid,))
                return self.send_json(200, {"ok": True})
            if route.startswith("/api/products"):
                pid = int(route.rsplit("/", 1)[-1]) if route != "/api/products" else None
                with connect() as c:
                    if self.command == "DELETE" and pid:
                        if not c.execute("DELETE FROM products WHERE id=?", (pid,)).rowcount:
                            return self.send_json(404, {"error": "Producto no encontrado"})
                    elif self.command in ["POST", "PUT"]:
                        d = self.body()
                        for k in ["name", "brewery", "style", "description", "color"]:
                            if (
                                not isinstance(d.get(k), str)
                                or not d[k].strip()
                                or len(d[k]) > 2000
                            ):
                                raise ValueError("Revisa los campos del producto")
                        for k in ["price", "stock", "volume"]:
                            if type(d.get(k)) != int or d[k] < 0 or d[k] > 1000000:
                                raise ValueError("Precio, stock o volumen no válido")
                        if (
                            d["price"] == 0
                            or (d["stock"] > 0 and d["volume"] == 0)
                            or not 0 <= float(d.get("abv", -1)) <= 30
                        ):
                            raise ValueError("Revisa precio, volumen y graduación")
                        keys = [
                            "name",
                            "brewery",
                            "style",
                            "price",
                            "stock",
                            "abv",
                            "volume",
                            "description",
                            "color",
                        ]
                        values = [d[k] for k in keys]
                        if "abv_label" in d:
                            if not isinstance(d["abv_label"], str) or len(d["abv_label"]) > 60:
                                raise ValueError("Graduación no válida")
                            keys.append("abv_label")
                            values.append(d["abv_label"])
                        if "image_data" in d or "image" in d:
                            image = d.get("image", "")
                            if not isinstance(image, str) or (
                                image
                                and not catalog_image_exists(image)
                                and (
                                    not re.fullmatch(r"/uploads/[a-f0-9]{32}\.webp", image)
                                    or not (DATA / "uploads" / image.rsplit("/", 1)[-1]).is_file()
                                )
                            ):
                                raise ValueError("Imagen no válida")
                            if d.get("image_data"):
                                image = product_image(d["image_data"])
                            keys.append("image")
                            values.append(image)
                        if pid:
                            if not c.execute(
                                "UPDATE products SET "
                                + ",".join(k + "=?" for k in keys)
                                + " WHERE id=?",
                                values + [pid],
                            ).rowcount:
                                return self.send_json(404, {"error": "Producto no encontrado"})
                        else:
                            c.execute(
                                "INSERT INTO products("
                                + ",".join(keys)
                                + ") VALUES("
                                + ",".join("?" for _ in keys)
                                + ")",
                                values,
                            )
                    else:
                        return self.send_json(405, {"error": "Método no permitido"})
                return self.send_json(200, {"ok": True})
            return self.send_json(404, {"error": "No encontrado"})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.send_json(400, {"error": "Datos no válidos. Revisa los campos y las existencias."})


if __name__ == "__main__":
    initialize()
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "3000"))), Handler).serve_forever()
