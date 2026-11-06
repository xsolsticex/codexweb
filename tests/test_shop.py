import unittest, tempfile, threading, json, urllib.request, urllib.error, http.cookiejar, os, io, base64
from pathlib import Path
import server

class ShopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.CATALOG_PATH=Path('/nonexistent/test-catalog.json')
        cls.tmp=tempfile.TemporaryDirectory();server.DATA=Path(cls.tmp.name);server.DB=server.DATA/'test.db';server.initialize()
        os.environ['ADMIN_PASSWORD']='test-only-password'
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.url='http://127.0.0.1:'+str(cls.http.server_port)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
        cls.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    @classmethod
    def tearDownClass(cls): cls.http.shutdown();cls.http.server_close();cls.tmp.cleanup()
    def request(self,path,method='GET',data=None,client=None):
        req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,method=method,headers={'Content-Type':'application/json'})
        try:
            with (client or urllib.request.build_opener()).open(req) as r:
                raw=r.read();return r.status,json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
    def test_store_serves(self):
        with urllib.request.urlopen(self.url) as r:self.assertIn(b'THE BEER',r.read())
        code,products=self.request('/api/products');self.assertEqual(code,200);self.assertEqual(len(products),6)
    def test_admin_crud_and_auth(self):
        p={'name':'Prueba','brewery':'Test','style':'IPA','price':400,'stock':10,'abv':5.5,'volume':330,'description':'Cerveza de prueba','color':'#aa8822'}
        self.assertEqual(self.request('/api/products','POST',p)[0],401)
        self.assertEqual(self.request('/api/login','POST',{'password':'wrong'},self.client)[0],401)
        self.assertEqual(self.request('/api/login','POST',{'password':'test-only-password'},self.client)[0],200)
        self.assertEqual(self.request('/api/products','POST',p,self.client)[0],200)
        product=self.request('/api/products')[1][-1];p['stock']=7
        self.assertEqual(self.request('/api/products/'+str(product['id']),'PUT',p,self.client)[0],200)
        self.assertEqual(self.request('/api/products')[1][-1]['stock'],7)
        self.assertEqual(self.request('/api/products/'+str(product['id']),'DELETE',client=self.client)[0],200)
        self.assertEqual(self.request('/api/logout','POST',client=self.client)[0],200)
        self.assertEqual(self.request('/api/orders',client=self.client)[0],401)
    def test_order_prices_stock_and_rollback(self):
        p=self.request('/api/products')[1][0]
        order={'adult':True,'customer':{'name':'Cliente','email':'cliente@example.com','address':'Calle Prueba 1','postal':'28001','city':'Madrid'},'items':[{'id':p['id'],'quantity':2,'price':1}],'total':1}
        code,result=self.request('/api/orders','POST',order);self.assertEqual(code,201);self.assertEqual(result['total'],p['price']*2+490);self.assertEqual(result['status'],'pending_payment')
        self.assertEqual(self.request('/api/products')[1][0]['stock'],p['stock']-2)
        order['items']=[{'id':p['id'],'quantity':1},{'id':9999,'quantity':1}]
        self.assertEqual(self.request('/api/orders','POST',order)[0],400)
        self.assertEqual(self.request('/api/products')[1][0]['stock'],p['stock']-2)
        order['adult']=False;self.assertEqual(self.request('/api/orders','POST',order)[0],400)
    def test_seed_not_recreated(self):
        with server.connect() as c:before=c.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        server.initialize()
        with server.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM products').fetchone()[0],before)

    def test_image_upload_validation_and_removal(self):
        client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.request('/api/login','POST',{'password':'test-only-password'},client)
        p={'name':'Foto','brewery':'Test','style':'IPA','price':400,'stock':10,'abv':5.5,'volume':330,'description':'Foto de prueba','color':'#aa8822'}
        output=io.BytesIO();server.Image.new('RGB',(30,50),'brown').save(output,format='PNG')
        p['image_data']=base64.b64encode(output.getvalue()).decode()
        self.assertEqual(self.request('/api/products','POST',p)[0],401)
        self.assertEqual(self.request('/api/products','POST',p,client)[0],200)
        product=self.request('/api/products')[1][-1]
        self.assertTrue(product['image'].endswith('.webp'))
        with urllib.request.urlopen(self.url+product['image']) as r:
            self.assertEqual(r.headers['Content-Type'],'image/webp')
            self.assertEqual(server.Image.open(io.BytesIO(r.read())).size,(30,50))
        p['image_data']=base64.b64encode(b'<svg>not an image</svg>').decode()
        self.assertEqual(self.request('/api/products/'+str(product['id']),'PUT',p,client)[0],400)
        self.assertEqual(self.request('/api/products')[1][-1]['image'],product['image'])
        del p['image_data']
        p['image']='../server.py'
        self.assertEqual(self.request('/api/products/'+str(product['id']),'PUT',p,client)[0],400)
        p['image']=''
        self.assertEqual(self.request('/api/products/'+str(product['id']),'PUT',p,client)[0],200)
        self.assertEqual(self.request('/api/products')[1][-1]['image'],'')
        self.request('/api/products/'+str(product['id']),'DELETE',client=client)

if __name__=='__main__':unittest.main()
