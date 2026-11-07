import hashlib
import sqlite3
import unittest
from PIL import Image
from photo_catalog import STATIC, photos, apply_photos, catalog_image_exists, with_photo_credit

class PhotoCatalogTest(unittest.TestCase):
    def test_assets_are_valid_and_have_sources(self):
        entries=photos()
        self.assertEqual(len(entries),19)
        self.assertEqual(len({p['name'] for p in entries}),19)
        for p in entries:
            self.assertTrue(catalog_image_exists(p['image']))
            file=STATIC/p['image'].lstrip('/')
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),p['sha256'])
            with Image.open(file) as image:
                self.assertEqual(image.size,(p['width'],p['height']))
                image.verify()
            self.assertTrue(p['source_page'].startswith('https://'))
            self.assertTrue(p['credit'])
        self.assertFalse(catalog_image_exists('/images/products/../../server.py'))
        self.assertFalse(catalog_image_exists('https://example.com/photo.jpg'))

    def test_assign_once_preserving_admin_images_and_removals(self):
        first,second=photos()[:2]
        with sqlite3.connect(':memory:') as c:
            c.row_factory=sqlite3.Row
            c.executescript('CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT,image TEXT);CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);')
            c.execute('INSERT INTO products(name,image) VALUES(?,?)',(first['name'],''))
            c.execute('INSERT INTO products(name,image) VALUES(?,?)',(second['name'],'/uploads/custom.webp'))
            self.assertEqual(apply_photos(c),1)
            self.assertEqual(c.execute('SELECT image FROM products WHERE name=?',(first['name'],)).fetchone()[0],first['image'])
            self.assertEqual(c.execute('SELECT image FROM products WHERE name=?',(second['name'],)).fetchone()[0],'/uploads/custom.webp')
            c.execute("UPDATE products SET image=''")
            self.assertEqual(apply_photos(c),0)
            self.assertEqual(c.execute("SELECT count(*) FROM products WHERE image!=''").fetchone()[0],0)

    def test_legacy_photo_path_is_migrated_after_assignment(self):
        photo = photos()[0]
        legacy = photo['image'].replace('/images/products/', '/product-images/', 1)
        with sqlite3.connect(':memory:') as c:
            c.row_factory = sqlite3.Row
            c.executescript('CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT,image TEXT);CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);')
            c.execute('INSERT INTO products(name,image) VALUES(?,?)', (photo['name'], ''))
            apply_photos(c)
            c.execute('UPDATE products SET image=?', (legacy,))
            self.assertEqual(apply_photos(c), 0)
            self.assertEqual(c.execute('SELECT image FROM products').fetchone()[0], photo['image'])

    def test_credit_follows_the_photo_not_the_product_name(self):
        photo=photos()[0]
        result=with_photo_credit({'name':'Renombrada','image':photo['image']})
        self.assertEqual(result['image_credit'],photo['credit'])
        self.assertNotIn('image_credit',with_photo_credit({'image':'/uploads/replacement.webp'}))
