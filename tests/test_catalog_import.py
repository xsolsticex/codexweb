import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from catalog_import import read_catalog, import_once

SOURCE = Path(__file__).resolve().parents[1] / 'static' / 'beers.json'

class CatalogImportTest(unittest.TestCase):
    def test_prices_ranges_and_known_volume(self):
        rows = read_catalog(SOURCE)
        self.assertEqual(len(rows), 40)
        self.assertEqual(rows[0]['price'], 450)
        self.assertTrue(all(p['stock'] == 0 for p in rows))
        self.assertEqual(next(p for p in rows if p['name'].startswith('Delirium'))['price'], 450)
        self.assertEqual(next(p for p in rows if p['name'].startswith('Chimay'))['volume'], 750)
        self.assertEqual(next(p for p in rows if p['name'].startswith('Lindemans'))['abv_label'], '2.5%-3.5%')
        self.assertEqual(next(p for p in rows if p['name'].startswith('Maredsous 6'))['abv'], 6)
        self.assertEqual(rows[0]['volume'], 0)

    def test_import_replaces_demo_but_preserves_user_work(self):
        with sqlite3.connect(':memory:') as c:
            c.executescript('''CREATE TABLE products(id INTEGER PRIMARY KEY,name TEXT,brewery TEXT,style TEXT,price INTEGER,stock INTEGER,abv REAL,abv_label TEXT,volume INTEGER,description TEXT,color TEXT);
                CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE orders(id TEXT PRIMARY KEY,items TEXT);''')
            c.execute("INSERT INTO products(name) VALUES('Bruma Atlántica')")
            c.execute("INSERT INTO products(name) VALUES('Mi cerveza propia')")
            c.execute("INSERT INTO orders VALUES('pedido-anterior','histórico')")
            self.assertEqual(import_once(c, SOURCE), 40)
            self.assertEqual(c.execute('SELECT count(*) FROM products').fetchone()[0], 41)
            self.assertEqual(c.execute('SELECT items FROM orders').fetchone()[0], 'histórico')
            c.execute("UPDATE products SET stock=12,price=999 WHERE name=?", (read_catalog(SOURCE)[0]['name'],))
            self.assertEqual(import_once(c, SOURCE), 0)
            self.assertEqual(c.execute('SELECT stock,price FROM products WHERE name=?',(read_catalog(SOURCE)[0]['name'],)).fetchone(), (12,999))

    def test_invalid_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.json'
            path.write_text(json.dumps([{'nombre':'Prueba','tipo':'IPA','precio':'sin precio','graduacion':'5%'}]))
            with self.assertRaises(ValueError): read_catalog(path)

if __name__ == '__main__': unittest.main()
