"""One-time import of the supplied Spanish beer catalogue, preserving admin edits."""

import json
import re
from decimal import Decimal, InvalidOperation

DEMO_NAMES = (
    "Bruma Atlántica",
    "Trigo de Sol",
    "Medianoche",
    "La de Siempre",
    "Bosque Adentro",
    "Roja de Otoño",
)


def read_catalog(path):
    source = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(source, list) or not source:
        raise ValueError("beers.json debe contener una lista de cervezas")
    products = []
    seen = set()
    for row in source:
        name, style = row["nombre"].strip(), row["tipo"].strip()
        if not name or not style or name in seen:
            raise ValueError("Nombre o estilo vacío, o cerveza duplicada")
        seen.add(name)
        price_match = re.match(r"^\s*(\d+(?:[.,]\d{1,2})?)\s*€", row["precio"])
        abv_match = re.fullmatch(
            r"\s*(\d+(?:[.,]\d+)?)[%°](?:\s*-\s*(\d+(?:[.,]\d+)?)[%°])?\s*", row["graduacion"]
        )
        if not price_match or not abv_match:
            raise ValueError("Precio o graduación no reconocidos: " + name)
        price = int(Decimal(price_match[1].replace(",", ".")) * 100)
        abv = float(abv_match[1].replace(",", "."))
        if not 0 < price <= 1000000 or not 0 <= abv <= 30:
            raise ValueError("Precio o graduación fuera de rango")
        volume_match = re.search(r"\((\d+)\s*cl\)", name, re.I)
        volume = int(volume_match[1]) * 10 if volume_match else 0
        abv_label = row["graduacion"].strip() if abv_match[2] else ""
        description = style + ". Datos del catálogo de The Beer Codex."
        if abv_label:
            description += (
                " Graduación según variedad: "
                + abv_label
                + ". Especifica la variedad antes de ponerla a la venta."
            )
        if "frambuesa" in name.lower():
            description += " Entrada agrupada: confirmar la variedad antes de la venta."
        description += " Existencias pendientes de confirmar."
        products.append(
            dict(
                name=name,
                brewery="No indicada",
                style=style,
                price=price,
                stock=0,
                abv=abv,
                abv_label=abv_label,
                volume=volume,
                description=description,
                color="#a52329",
            )
        )
    return products


def import_once(connection, path):
    if (
        not path.is_file()
        or connection.execute("SELECT 1 FROM settings WHERE key='beers_json_imported'").fetchone()
    ):
        return 0
    products = read_catalog(path)
    # Only discard the original demo catalogue; retain user-created products and orders.
    connection.execute(
        "DELETE FROM products WHERE name IN (" + ",".join("?" for _ in DEMO_NAMES) + ")", DEMO_NAMES
    )
    fields = list(products[0])
    for product in products:
        if not connection.execute(
            "SELECT 1 FROM products WHERE name=?", (product["name"],)
        ).fetchone():
            connection.execute(
                "INSERT INTO products("
                + ",".join(fields)
                + ") VALUES("
                + ",".join("?" for _ in fields)
                + ")",
                [product[k] for k in fields],
            )
    connection.execute("INSERT INTO settings(key,value) VALUES('beers_json_imported','1')")
    return len(products)
