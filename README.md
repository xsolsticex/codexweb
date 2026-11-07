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

SQLite se guarda en `.data/shop.db` (ignorado por Git). `DATA_DIR` permite elegir otra ubicación; haz copias de seguridad. El primer arranque importa las 40 entradas de `static/data/beers.json`, tanto en bases nuevas como en instalaciones existentes. Sustituye los seis productos originales de demostración y conserva otros productos y los pedidos. La importación se ejecuta una sola vez: los siguientes arranques conservan los cambios de administración. No sincroniza automáticamente futuras modificaciones del JSON.

El importador convierte los precios a céntimos, conserva rangos de graduación y usa el precio ordinario cuando una nota contiene una promoción. Stock inicial: 0. Volumen desconocido: 0 (se muestra «Formato por confirmar»); el formato de 75 cl de Chimay se importa como 750 ml. Completa el formato y las existencias en administración antes de vender. Las entradas con varios sabores siguen agrupadas como en el archivo original y deben concretarse antes de activar stock. No se inventan fotografías, descripciones de cata ni fabricantes. En el editor puedes subir fotos JPG, PNG o WebP de hasta 4 MB y 16 megapíxeles, con vista previa y opción de quitarlas. El servidor valida y convierte las fotos a WebP (máximo 1600 × 1600), elimina sus metadatos y las conserva en `.data/uploads/`. Incluye esa carpeta en las copias de seguridad. Las cervezas sin foto usan una ilustración local. Al reemplazar o quitar una foto, el archivo anterior se conserva en disco para no romper otras referencias; su limpieza es manual.

Los precios se calculan en el servidor en céntimos. Registrar un pedido descuenta existencias dentro de una transacción y lo guarda como `pending_payment`. Envío: 4,90 €, gratis desde 60 €. Estas tarifas son provisionales; no incorporan restricciones territoriales del transportista.

**No hay cobro online, envío de correo ni facturación.** El checkout indica que el pedido queda pendiente de pago. El administrador puede consultar referencia, cliente, dirección, productos y total. Antes del lanzamiento comercial hay que elegir e integrar la pasarela (con webhooks de confirmación), definir liberación de reservas/cancelaciones, transportista, condiciones de venta y textos de privacidad. No introduzcas datos de tarjeta en esta versión.

La web solicita confirmación de mayoría de edad; no verifica identidad. El nombre, país y moneda corresponden a The Beer Codex, España y EUR. El catálogo inicial y los nombres de cerveceras son ejemplos que debes sustituir.

## Validación

```sh
python3 -m unittest discover -s tests -v
node --check static/js/app.js
```

## Fotografías del catálogo

Se incluyen 19 fotos verificadas con fuentes y créditos en [PRODUCT_PHOTOS.md](PRODUCT_PHOTOS.md). El servidor las asigna una sola vez a los productos con el mismo nombre y sin foto. Se conservan las fotos subidas por administración; reemplazar o quitar una foto no se deshace al reiniciar. Los archivos forman parte del repositorio, por lo que no se necesita acceso externo al servirlas. Las 21 entradas restantes mantienen la ilustración provisional.

## Chat de atención al cliente

El botón inferior derecho abre una conversación con el administrador. Los mensajes se guardan en SQLite, y una cookie HttpOnly identifica la conversación de cada navegador durante 30 días. En `/admin`, «Consultas de clientes» permite leer y responder tras iniciar sesión. Las conversaciones se actualizan cada 5 segundos mientras la página está visible; el cliente consulta respuestas al abrir el chat. No se envían correos ni notificaciones externas, ni se promete atención inmediata. Al borrar las cookies o cambiar de navegador no se recupera la conversación anterior. Incluye la base de datos en las copias de seguridad.

El cliente y el administrador pueden finalizar una conversación. Las conversaciones finalizadas conservan su historial y no admiten nuevos mensajes; el cliente puede pulsar «Nueva consulta» para comenzar otra. La bandeja de administración distingue las consultas finalizadas de las pendientes.

El administrador puede eliminar definitivamente un chat finalizado y sus mensajes desde la conversación, previa confirmación. Las conversaciones abiertas no se pueden eliminar.

En administración, «Cancelar y eliminar pedido» elimina definitivamente un pedido pendiente de pago tras confirmar y devuelve sus cantidades al stock de los productos que sigan existiendo. La operación es atómica y no admite pedidos con otro estado. No realiza reembolsos ni envía avisos al cliente.
