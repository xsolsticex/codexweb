"""Locally retained, reviewed product photographs and their source credits."""

import hashlib
import json
import re
from pathlib import Path

STATIC = Path(__file__).parent / "static"
MANIFEST = STATIC / "data" / "product-images.json"


def photos():
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else []


def catalog_image_exists(url):
    return (
        isinstance(url, str)
        and bool(re.fullmatch(r"/images/products/[a-z0-9-]+\.(?:png|jpg|webp)", url))
        and (STATIC / url.lstrip("/")).is_file()
    )


def apply_photos(connection):
    applied = 0
    # Migrate only bundled photo paths; retain administrator uploads and removals.
    for photo in photos():
        legacy = photo["image"].replace("/images/products/", "/product-images/", 1)
        connection.execute("UPDATE products SET image=? WHERE image=?", (photo["image"], legacy))
    for photo in photos():
        key = "catalog-photo:" + hashlib.sha256(photo["name"].encode()).hexdigest()
        if connection.execute("SELECT 1 FROM settings WHERE key=?", (key,)).fetchone():
            continue
        row = connection.execute(
            "SELECT id,image FROM products WHERE name=?", (photo["name"],)
        ).fetchone()
        if row is None:
            continue
        if not catalog_image_exists(photo["image"]):
            raise ValueError("Fotografía del catálogo ausente: " + photo["name"])
        path = STATIC / photo["image"].lstrip("/")
        if hashlib.sha256(path.read_bytes()).hexdigest() != photo["sha256"]:
            raise ValueError("La fotografía no coincide con su registro: " + photo["name"])
        if not row["image"]:
            connection.execute(
                "UPDATE products SET image=? WHERE id=?", (photo["image"], row["id"])
            )
            applied += 1
        # Preserve replacements and removals made by the administrator on later starts.
        connection.execute("INSERT INTO settings(key,value) VALUES(?,?)", (key, photo["image"]))
    return applied


def with_photo_credit(product):
    photo = next((p for p in photos() if p["image"] == product.get("image")), None)
    if photo:
        product.update(
            image_credit=photo["credit"],
            image_source=photo["source_page"],
            image_license=photo["license"],
            image_license_url=photo["license_url"],
        )
    return product
