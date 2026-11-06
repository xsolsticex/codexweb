# The Beer Codex

Tienda de cervezas para España, en euros. Catálogo filtrable, búsqueda, carrito persistente, registro de pedidos y administración de productos. Python 3.12+ y SQLite, sin dependencias externas.

## Ejecutar

```sh
cd /workspace/codexweb
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

SQLite se guarda en `.data/shop.db` (ignorado por Git). `DATA_DIR` permite elegir otra ubicación; haz copias de seguridad. El primer arranque carga seis cervezas de ejemplo y nunca vuelve a sembrarlas, incluso si se vacía el catálogo. Las ilustraciones son gráficas locales; aún no existe carga de fotografías de producto.

Los precios se calculan en el servidor en céntimos. Registrar un pedido descuenta existencias dentro de una transacción y lo guarda como `pending_payment`. Envío: 4,90 €, gratis desde 60 €. Estas tarifas son provisionales; no incorporan restricciones territoriales del transportista.

**No hay cobro online, envío de correo ni facturación.** El checkout indica que el pedido queda pendiente de pago. El administrador puede consultar referencia, cliente, dirección, productos y total. Antes del lanzamiento comercial hay que elegir e integrar la pasarela (con webhooks de confirmación), definir liberación de reservas/cancelaciones, transportista, condiciones de venta y textos de privacidad. No introduzcas datos de tarjeta en esta versión.

La web solicita confirmación de mayoría de edad; no verifica identidad. El nombre, país y moneda corresponden a The Beer Codex, España y EUR. El catálogo inicial y los nombres de cerveceras son ejemplos que debes sustituir.

## Validación

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```
