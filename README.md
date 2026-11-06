# The Beer Codex

Tienda de cervezas para España, en euros. Catálogo filtrable, búsqueda, carrito persistente, registro de pedidos y administración de productos. Python 3.12+, SQLite y Pillow para validar y optimizar las fotos.

## Ejecutar

```sh
cd /workspace/codexweb
python3 -m pip install -r requirements.txt
python3 server.py
```

Puerto 3000 por defecto (`PORT` permite cambiarlo). Para habilitar `/admin`, configura `ADMIN_PASSWORD` con una contraseña segura en el entorno del proceso. No hay credenciales predeterminadas. Por ejemplo, en una terminal Bash puedes introducirla sin mostrarla ni guardarla en el historial:

```sh
read -rsp 'Contraseña de administración: ' ADMIN_PASSWORD
export ADMIN_PASSWORD
python3 server.py
```

En producción usa HTTPS y `COOKIE_SECURE=1`. Las sesiones caducan a las 8 horas y se invalidan al reiniciar el servidor. El servidor incluido es para desarrollo: antes de exponerlo públicamente, despliega detrás de un servidor de producción con HTTPS y limitación de intentos de acceso.

## Datos y pedidos

SQLite se guarda en `.data/shop.db` (ignorado por Git). `DATA_DIR` permite elegir otra ubicación; haz copias de seguridad. El primer arranque carga seis cervezas de ejemplo y nunca vuelve a sembrarlas, incluso si se vacía el catálogo. En el editor puedes subir fotos JPG, PNG o WebP de hasta 4 MB y 16 megapíxeles, con vista previa y opción de quitarlas. El servidor valida y convierte las fotos a WebP (máximo 1600 × 1600), elimina sus metadatos y las conserva en `.data/uploads/`. Incluye esa carpeta en las copias de seguridad. Las cervezas sin foto usan una ilustración local. Al reemplazar o quitar una foto, el archivo anterior se conserva en disco para no romper otras referencias; su limpieza es manual.

Los precios se calculan en el servidor en céntimos. Registrar un pedido descuenta existencias dentro de una transacción y lo guarda como `pending_payment`. Envío: 4,90 €, gratis desde 60 €. Estas tarifas son provisionales; no incorporan restricciones territoriales del transportista.

**No hay cobro online, envío de correo ni facturación.** El checkout indica que el pedido queda pendiente de pago. El administrador puede consultar referencia, cliente, dirección, productos y total. Antes del lanzamiento comercial hay que elegir e integrar la pasarela (con webhooks de confirmación), definir liberación de reservas/cancelaciones, transportista, condiciones de venta y textos de privacidad. No introduzcas datos de tarjeta en esta versión.

La web solicita confirmación de mayoría de edad; no verifica identidad. El nombre, país y moneda corresponden a The Beer Codex, España y EUR. El catálogo inicial y los nombres de cerveceras son ejemplos que debes sustituir.

## Validación

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```
