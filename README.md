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

**No hay cobro online ni facturación.** El checkout indica que el pedido queda pendiente de pago. El administrador puede consultar referencia, cliente, dirección, productos y total. Antes del lanzamiento comercial hay que elegir e integrar la pasarela (con webhooks de confirmación), definir liberación de reservas/cancelaciones, transportista, condiciones de venta y textos de privacidad. No introduzcas datos de tarjeta en esta versión.

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

## Correos de confirmación de pedidos

Cada pedido nuevo guarda, en la misma transacción que reserva el stock, un correo pendiente en SQLite. El servidor lo envía en segundo plano usando SMTP con TLS. Incluye referencia, fecha de Madrid, productos, unidades, precios, subtotal, envío, total y dirección de entrega. Aclara que el pedido está pendiente de pago y permite responder al remitente para gestionar la compra. Incluye versiones HTML y texto.

Configura estas variables en el archivo `.env` de la raíz del proyecto o en el entorno del servidor, usando los datos de tu proveedor de correo:

- `SMTP_HOST`: servidor SMTP.
- `SMTP_PORT`: 587 para STARTTLS (predeterminado) o 465 para SSL.
- `SMTP_SECURITY`: `starttls` (predeterminado) o `ssl`; ambos verifican el certificado TLS.
- `SMTP_USERNAME` y `SMTP_PASSWORD`: usuario y contraseña del proveedor, si requiere autenticación. Guárdalos como secretos, sin añadirlos al repositorio.
- `MAIL_FROM`: remitente autorizado, por ejemplo `The Beer Codex <pedidos@tu-dominio.es>`.
- `MAIL_REPLY_TO`: dirección para gestiones; por defecto usa la dirección de `MAIL_FROM`.

El remitente/dominio debe estar verificado en el proveedor (SPF/DKIM según sus instrucciones). Reinicia el servidor tras configurar las variables. Sin SMTP no se afirma que el correo haya sido enviado: el pedido se conserva, la confirmación solicita guardar su referencia y administración indica que falta configurar el correo.

Los fallos de envío se reintentan automáticamente con espera progresiva de 30 segundos a una hora; la cola sobrevive a reinicios. Administración muestra si el correo está pendiente, enviándose o enviado. «Enviado» significa aceptado por el servidor SMTP; no garantiza entrega en la bandeja de entrada. Una interrupción justo después de la aceptación SMTP puede causar un reenvío: se conserva el mismo Message-ID para facilitar la detección de duplicados. Al eliminar un pedido se elimina también su correo pendiente; un correo ya enviado no se puede retirar. Los pedidos anteriores a esta función no generan correos retroactivos. No se envían correos por el chat ni por cancelación de pedidos.

### Configuración con Gmail

1. En la cuenta Gmail que enviará los pedidos, activa la verificación en dos pasos y genera una **contraseña de aplicación** en la cuenta de Google. Algunas cuentas de empresa o con restricciones no permiten contraseñas de aplicación; en ese caso consulta al administrador de Google Workspace.
2. En las variables/secretos del alojamiento configura `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_SECURITY=starttls` y `SMTP_USERNAME` con la dirección Gmail completa.
3. Guarda la contraseña de aplicación como secreto `SMTP_PASSWORD`. No uses la contraseña habitual de Google.
4. Configura `MAIL_FROM` con esa misma dirección (`The Beer Codex <tu-cuenta@gmail.com>`) y `MAIL_REPLY_TO` con el correo donde atenderás las consultas.
5. Reinicia el servidor y realiza un pedido de prueba con una dirección tuya. Comprueba su recepción y el estado del correo en administración. Gmail aplica sus límites de envío y puede filtrar mensajes como spam.

El envío SMTP utiliza la biblioteca estándar de Python. `python-dotenv`, incluido en `requirements.txt`, permite cargar la configuración local.

### Archivo local de configuración

El servidor carga automáticamente `.env` desde la raíz del proyecto, independientemente del directorio de ejecución. Las variables definidas en el entorno del alojamiento tienen prioridad. Para preparar una instalación nueva:

```sh
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Completa `.env` con tu cuenta Gmail y su contraseña de aplicación y reinicia el servidor. `MAIL_REPLY_TO` se puede omitir para usar la dirección remitente; si se configura, debe ser un correo válido. `.env` y sus variantes locales están excluidos en `.gitignore`; `.env.example` es una plantilla pública sin credenciales que sí se versiona. Nunca añadas datos reales a la plantilla ni fuerces la inclusión de `.env` con `git add -f`.
