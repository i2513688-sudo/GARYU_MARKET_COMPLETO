# GARYU MARKET — Sistema web de ventas

Aplicación Flask + SQL Server. La interfaz toma como referencia el estilo de navegación de apps de delivery como Rappi (buscador, categorías, promociones, tarjetas de productos y carrito), manteniendo los productos que existan realmente en el catálogo de GARYU MARKET.

## Módulos conectados

- **Identidad:** registro, inicio de sesión, clientes, direcciones y roles.
- **Catálogo:** productos, categorías, subcategorías, marcas, unidades, imágenes y promociones activas.
- **Inventario:** stock disponible, reservas por almacén y liberación/consumo de reservas.
- **Comercio:** carrito persistido, pedidos, detalles, ventas e historial de estados.
- **Pagos:** métodos de pago y registro de pagos pendientes.
- **Logística:** delivery, código de seguimiento e historial de entrega.

## Requisitos

- Windows 10/11, Python 3.10+ (recomendado Python 3.13; para Python 3.14 instala una versión de pyodbc con wheel compatible).
- SQL Server y SSMS.
- ODBC Driver 18 for SQL Server (o ajusta `DB_DRIVER` en `.env`).
- Una cuenta SQL Server con permisos de lectura y escritura en las seis bases. Las seis bases deben estar en la misma instancia porque el proceso de compra usa consultas entre bases.

## 1. Crear bases y tablas

En SSMS, conecta a tu instancia y ejecuta en este orden:

1. `database_sql/00_crear_bases.sql`
2. `database_sql/identidad.sql`
3. `database_sql/catalogo.sql`
4. `database_sql/inventario.sql`
5. `database_sql/comercio.sql`
6. `database_sql/pagos.sql`
7. `database_sql/logistica.sql`
8. `database_sql/07_configuracion_inicial.sql`

Los seis scripts originales están incluidos sin modificar. El último script agrega estados, roles y métodos de pago mínimos que utiliza la aplicación.

**Importante sobre los productos:** los seis archivos SQL originales definen estructura, claves y restricciones; no incluyen registros de productos, imágenes ni existencias. La tienda muestra únicamente los productos reales registrados en `garyu_catalogo_db.dbo.producto` y el stock de `garyu_inventario_db.dbo.inventario`. No se inventaron nombres ni precios. Si las tablas están vacías, primero registra categorías, subcategorías, unidades, almacenes y productos. El panel web permite registrar productos cuando ya existen las subcategorías, unidades y almacenes.

## 2. Configurar conexión

1. Copia `.env.example` como `.env`.
2. Configura `DB_SERVER` con el nombre de tu instancia (por ejemplo `localhost` o `SERVIDOR\SQLEXPRESS`).
3. Para autenticación de Windows deja `DB_AUTH=windows`. Para autenticación SQL usa `DB_AUTH=sql` y completa `DB_USERNAME` y `DB_PASSWORD`.
4. Confirma que `DB_DRIVER` coincide con el controlador ODBC instalado.
5. Cambia `SECRET_KEY` por una clave privada larga.

Ejemplo:

```env
DB_DRIVER=ODBC Driver 18 for SQL Server
DB_SERVER=.\SQLEXPRESS
DB_AUTH=windows
DB_ENCRYPT=no
DB_TRUST_SERVER_CERTIFICATE=yes
SECRET_KEY=coloca-aqui-una-clave-larga-y-privada
```

## 3. Instalar y ejecutar

En PowerShell, desde la carpeta del proyecto:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install --only-binary=:all: -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` y ejecuta:

```powershell
python crear_admin.py
python app.py
```

Abre `http://127.0.0.1:5000`.

Si PowerShell bloquea la activación:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

## 4. Primer uso

1. Ejecuta `python crear_admin.py` para crear el administrador.
2. Inicia sesión en el sitio.
3. Si aún no existen, crea categorías, subcategorías, unidades de medida, marcas y almacenes en SQL Server.
4. Desde **Administración → Productos → Nuevo producto**, registra el SKU, nombre, subcategoría, unidad, precio, imagen opcional y stock inicial asociado a un almacén.
5. Los clientes crean su cuenta desde **Ingresar → Regístrate aquí**.
6. El cliente agrega productos al carrito, registra/selecciona dirección, elige método de pago y confirma el pedido.
7. El administrador actualiza los estados en **Administración → Pedidos**. Al marcar ENTREGADO se consume el stock reservado; al marcar CANCELADO se libera.

## 5. Límites importantes

- Yape/Plin y transferencia se registran como **PENDIENTE** y requieren validación manual desde Administración → Pedidos. No se realiza cobro electrónico automático.
- El costo de envío se configura con `DELIVERY_COST` (por defecto S/ 5.00).
- La compra se procesa en una transacción SQL Server entre las seis bases de la misma instancia. No funciona si están distribuidas en instancias diferentes.
- No emite comprobantes electrónicos SUNAT. Las tablas de comprobantes existen en la base comercio, pero emitirlos requiere integración tributaria autorizada.
- Configura HTTPS, clave secreta segura, backups y permisos mínimos antes de publicar en internet.

## 6. Diagnóstico

Entra como administrador y abre **Conexiones BD**. Se comprueba cada una de las seis bases y se muestra el número de tablas detectadas.
