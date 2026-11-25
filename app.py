import os, uuid, secrets
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from database import connect, query_all, query_one
from config import DATABASES

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'cambiar-clave-secreta')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
DELIVERY_COST = Decimal(os.getenv('DELIVERY_COST', '5.00'))


def money(v): return Decimal(str(v or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
def uid(): return str(uuid.uuid4())
def login_required(fn):
    @wraps(fn)
    def wrapped(*a, **kw):
        if not session.get('user_id'):
            flash('Inicia sesión para continuar.', 'warning'); return redirect(url_for('login', next=request.path))
        return fn(*a, **kw)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*a, **kw):
        if not session.get('is_admin'):
            abort(403)
        return fn(*a, **kw)
    return wrapped

@app.context_processor
def globals_template():
    cart = session.get('cart', {})
    return {'current_user': session.get('user_name'), 'cart_count': sum(int(x.get('qty', 0)) for x in cart.values()),
            'is_admin': session.get('is_admin', False), 'money': money}

PRODUCT_SELECT = """
SELECT p.id_producto, p.sku, p.nombre, p.descripcion, p.precio_venta,
       c.nombre AS categoria, sc.nombre AS subcategoria, um.abreviatura,
       COALESCE(st.stock,0) AS stock_disponible,
       img.url_imagen AS imagen,
       promo.nombre AS promocion,
       CASE WHEN promo.id_promocion IS NULL THEN p.precio_venta
            WHEN UPPER(promo.tipo_descuento) IN ('PORCENTAJE','PORCENTUAL','PERCENT')
                 THEN CASE WHEN p.precio_venta-(p.precio_venta*promo.valor_descuento/100)<0 THEN 0 ELSE p.precio_venta-(p.precio_venta*promo.valor_descuento/100) END
            ELSE CASE WHEN p.precio_venta-promo.valor_descuento<0 THEN 0 ELSE p.precio_venta-promo.valor_descuento END END AS precio_final
FROM garyu_catalogo_db.dbo.producto p
LEFT JOIN garyu_catalogo_db.dbo.subcategoria sc ON sc.id_subcategoria=p.subcategoria_id
LEFT JOIN garyu_catalogo_db.dbo.categoria c ON c.id_categoria=sc.categoria_id
LEFT JOIN garyu_catalogo_db.dbo.unidad_medida um ON um.id_unidad_medida=p.unidad_medida_id
OUTER APPLY (SELECT SUM(i.stock_disponible) stock FROM garyu_inventario_db.dbo.inventario i WHERE i.producto_id=p.id_producto) st
OUTER APPLY (SELECT TOP 1 ip.url_imagen FROM garyu_catalogo_db.dbo.imagen_producto ip WHERE ip.producto_id=p.id_producto AND ip.estado=1 ORDER BY ip.es_principal DESC, ip.orden) img
OUTER APPLY (SELECT TOP 1 pr.id_promocion,pr.nombre,pr.tipo_descuento,pr.valor_descuento
             FROM garyu_catalogo_db.dbo.producto_promocion pp
             JOIN garyu_catalogo_db.dbo.promocion pr ON pr.id_promocion=pp.promocion_id
             WHERE pp.producto_id=p.id_producto AND pr.estado=1 AND SYSDATETIME() BETWEEN pr.fecha_inicio AND pr.fecha_fin
             ORDER BY pr.fecha_fin) promo
WHERE p.estado=1
"""

def get_products(search='', category=None, limit=None):
    sql = PRODUCT_SELECT
    params=[]
    if search:
        sql += " AND (p.nombre LIKE ? OR p.descripcion LIKE ? OR p.sku LIKE ? OR c.nombre LIKE ?)"
        term=f'%{search}%'; params += [term,term,term,term]
    if category:
        sql += ' AND c.id_categoria=?'; params.append(category)
    sql += ' ORDER BY CASE WHEN COALESCE(st.stock,0)>0 THEN 0 ELSE 1 END, p.nombre'
    if limit: sql = sql.replace('SELECT p.id_producto', f'SELECT TOP {int(limit)} p.id_producto')
    return query_all('catalogo', sql, params)

@app.route('/')
def home():
    q=request.args.get('q','').strip()
    category=request.args.get('categoria','').strip()
    try:
        products=get_products(q, int(category) if category.isdigit() else None, 24)
        categories=query_all('catalogo', "SELECT id_categoria,nombre FROM dbo.categoria WHERE estado=1 ORDER BY nombre")
        promos=query_all('catalogo', "SELECT TOP 4 nombre,descripcion FROM dbo.promocion WHERE estado=1 AND SYSDATETIME() BETWEEN fecha_inicio AND fecha_fin ORDER BY fecha_fin")
        db_error=None
    except Exception as e:
        products=[]; categories=[]; promos=[]; db_error=str(e)
    return render_template('home.html', products=products, categories=categories, promos=promos, q=q, selected_category=category, db_error=db_error)

@app.route('/producto/<product_id>')
def product_detail(product_id):
    try: p=query_one('catalogo', PRODUCT_SELECT+' AND p.id_producto=?', (product_id,))
    except Exception as e: flash(f'No se pudo cargar el producto: {e}','danger'); return redirect(url_for('home'))
    if not p: abort(404)
    return render_template('product_detail.html', product=p)

@app.post('/carrito/agregar/<product_id>')
def cart_add(product_id):
    try: p=query_one('catalogo', PRODUCT_SELECT+' AND p.id_producto=?', (product_id,))
    except Exception as e: flash(f'No se pudo consultar el producto: {e}','danger'); return redirect(url_for('home'))
    if not p: abort(404)
    if int(p['stock_disponible'] or 0) < 1:
        flash('Este producto no tiene stock disponible.','warning'); return redirect(request.referrer or url_for('home'))
    cart=session.get('cart',{}); key=str(p['id_producto']); old=int(cart.get(key,{}).get('qty',0))
    cart[key]={'qty':min(old+1,int(p['stock_disponible'])), 'name':p['nombre']}
    session['cart']=cart; session.modified=True
    flash(f'{p["nombre"]} se agregó al carrito.','success')
    return redirect(request.referrer or url_for('home'))

@app.route('/carrito', methods=['GET','POST'])
def cart_view():
    cart=session.get('cart',{}); items=[]; subtotal=Decimal('0.00')
    if cart:
        ids=list(cart.keys()); placeholders=','.join('?' for _ in ids)
        try: products=query_all('catalogo', PRODUCT_SELECT+f' AND p.id_producto IN ({placeholders})', ids)
        except Exception as e: products=[]; flash(f'No se pudo actualizar el carrito: {e}','danger')
        current={str(p['id_producto']):p for p in products}
        for pid, entry in list(cart.items()):
            p=current.get(pid)
            if not p: cart.pop(pid,None); continue
            qty=min(max(1,int(entry.get('qty',1))),max(0,int(p['stock_disponible'] or 0)))
            if qty<1: cart.pop(pid,None); continue
            price=money(p['precio_final']); line=price*qty; subtotal+=line
            items.append({'product':p,'qty':qty,'line':line})
            cart[pid]['qty']=qty
        session['cart']=cart
    return render_template('cart.html', items=items, subtotal=subtotal, delivery=DELIVERY_COST, total=subtotal+DELIVERY_COST)

@app.post('/carrito/actualizar')
def cart_update():
    cart=session.get('cart',{}); pid=request.form.get('product_id',''); action=request.form.get('action')
    if pid in cart:
        qty=int(cart[pid].get('qty',1))
        if action=='plus': qty+=1
        elif action=='minus': qty-=1
        elif action=='remove': qty=0
        if qty<=0: cart.pop(pid,None)
        else: cart[pid]['qty']=qty
    session['cart']=cart; session.modified=True
    return redirect(url_for('cart_view'))

@app.route('/registro', methods=['GET','POST'])
def register():
    if request.method=='POST':
        form=request.form
        names=form.get('nombres','').strip(); ap=form.get('apellido_paterno','').strip(); am=form.get('apellido_materno','').strip()
        doc=form.get('documento','').strip(); phone=form.get('telefono','').strip(); email=form.get('correo','').strip().lower()
        username=form.get('usuario','').strip(); password=form.get('password','')
        if not all([names,ap,doc,email,username]) or len(password)<8:
            flash('Completa los campos obligatorios. La contraseña debe tener al menos 8 caracteres.','warning')
            return render_template('register.html')
        try:
            with connect('identidad') as cn:
                cur=cn.cursor()
                dtype=cur.execute("SELECT TOP 1 id_tipo_documento FROM dbo.tipo_documento WHERE codigo='DNI' AND estado=1").fetchone()
                if not dtype: raise ValueError('No existe el tipo de documento DNI. Ejecuta configuracion_inicial.sql.')
                if cur.execute('SELECT 1 FROM dbo.usuario WHERE correo_acceso=? OR nombre_usuario=?',(email,username)).fetchone(): raise ValueError('El correo o nombre de usuario ya está registrado.')
                persona=uid(); cliente=uid(); user=uid()
                cur.execute("""INSERT dbo.persona(id_persona,tipo_documento_id,numero_documento,tipo_persona,nombres,apellido_paterno,apellido_materno,telefono,correo,fecha_registro,estado)
                    VALUES(?,?,?,'NATURAL',?,?,?,?,?,SYSDATETIME(),1)""",persona,dtype[0],doc,names,ap,am or None,phone or None,email)
                cur.execute("INSERT dbo.cliente(id_cliente,persona_id,fecha_alta,estado) VALUES(?,?,SYSDATETIME(),1)",cliente,persona)
                cur.execute("INSERT dbo.usuario(id_usuario,persona_id,nombre_usuario,correo_acceso,password_hash,fecha_registro,estado) VALUES(?,?,?,?,?,SYSDATETIME(),1)",user,persona,username,email,generate_password_hash(password))
                role=cur.execute("SELECT TOP 1 id_rol FROM dbo.rol WHERE nombre='Cliente' AND estado=1").fetchone()
                if role: cur.execute('INSERT dbo.usuario_rol(usuario_id,rol_id,fecha_asignacion) VALUES(?,?,SYSDATETIME())',user,role[0])
                cn.commit()
            session['user_id']=user; session['client_id']=cliente; session['user_name']=f'{names} {ap}'; session['is_admin']=False
            flash('Tu cuenta fue creada correctamente.','success'); return redirect(url_for('checkout'))
        except Exception as e: flash(f'No se pudo crear la cuenta: {e}','danger')
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        login_value=request.form.get('usuario','').strip(); password=request.form.get('password','')
        try:
            user=query_one('identidad',"""SELECT TOP 1 u.id_usuario,u.nombre_usuario,u.password_hash,u.estado,c.id_cliente,
                COALESCE(NULLIF(LTRIM(RTRIM(CONCAT(p.nombres,' ',p.apellido_paterno))),''),p.razon_social,u.nombre_usuario) nombre,
                CASE WHEN EXISTS(SELECT 1 FROM dbo.usuario_rol ur JOIN dbo.rol r ON r.id_rol=ur.rol_id WHERE ur.usuario_id=u.id_usuario AND r.estado=1 AND r.nombre IN ('Administrador','Admin')) THEN 1 ELSE 0 END es_admin
                FROM dbo.usuario u JOIN dbo.persona p ON p.id_persona=u.persona_id LEFT JOIN dbo.cliente c ON c.persona_id=p.id_persona
                WHERE (u.nombre_usuario=? OR u.correo_acceso=?) AND u.estado=1""",(login_value,login_value))
            if user and check_password_hash(user['password_hash'],password):
                session.clear(); session['user_id']=str(user['id_usuario']); session['client_id']=str(user['id_cliente']) if user['id_cliente'] else None
                session['user_name']=user['nombre']; session['is_admin']=bool(user['es_admin'])
                flash('Bienvenido a GARYU MARKET.','success')
                return redirect(url_for('admin_dashboard') if user['es_admin'] else url_for('home'))
            flash('Usuario o contraseña incorrectos.','danger')
        except Exception as e: flash(f'No se pudo iniciar sesión: {e}','danger')
    return render_template('login.html')

@app.route('/salir')
def logout(): session.clear(); flash('Sesión cerrada.','info'); return redirect(url_for('home'))

@app.route('/checkout', methods=['GET','POST'])
@login_required
def checkout():
    if not session.get('client_id'):
        flash('La cuenta actual no tiene un perfil de cliente. Registra una cuenta de cliente para comprar.','warning'); return redirect(url_for('home'))
    cart=session.get('cart',{})
    if not cart: flash('Tu carrito está vacío.','warning'); return redirect(url_for('home'))
    try:
        ids=list(cart.keys()); ph=','.join('?' for _ in ids)
        products=query_all('catalogo',PRODUCT_SELECT+f' AND p.id_producto IN ({ph})',ids)
        methods=query_all('pagos','SELECT id_metodo_pago,codigo,nombre,descripcion FROM dbo.metodo_pago WHERE estado=1 ORDER BY id_metodo_pago')
        addresses=query_all('identidad',"""SELECT d.id_direccion,d.alias,d.direccion,d.referencia,d.distrito,d.provincia,d.departamento,d.es_principal
            FROM dbo.direccion d JOIN dbo.cliente c ON c.persona_id=d.persona_id WHERE c.id_cliente=? AND d.estado=1 ORDER BY d.es_principal DESC,d.fecha_registro DESC""",(session['client_id'],))
    except Exception as e:
        flash(f'No se pudieron cargar los datos de compra: {e}','danger'); return redirect(url_for('cart_view'))
    byid={str(p['id_producto']):p for p in products}; lines=[]; subtotal=Decimal('0.00')
    for pid,item in cart.items():
        p=byid.get(pid)
        if not p: continue
        qty=int(item.get('qty',1)); available=int(p['stock_disponible'] or 0)
        if qty>available: flash(f'Stock insuficiente para {p["nombre"]}. Disponible: {available}.','warning'); return redirect(url_for('cart_view'))
        price=money(p['precio_final']); subtotal+=price*qty; lines.append((p,qty,price))
    if request.method=='POST':
        try:
            client_id=session['client_id']; address_id=request.form.get('direccion_id') or None
            if address_id and not any(str(a['id_direccion'])==address_id for a in addresses): raise ValueError('La dirección seleccionada no pertenece a tu cuenta.')
            if not address_id:
                address=request.form.get('direccion','').strip(); district=request.form.get('distrito','').strip(); province=request.form.get('provincia','').strip(); department=request.form.get('departamento','').strip()
                if not all([address,district,province,department]): raise ValueError('Completa la dirección de entrega, distrito, provincia y departamento.')
            method_id=int(request.form.get('metodo_pago_id','0'))
            if not any(int(m['id_metodo_pago'])==method_id for m in methods): raise ValueError('Selecciona un método de pago válido.')
            delivery=DELIVERY_COST; total=subtotal+delivery; order_id=uid(); cart_id=uid(); sale_id=uid(); payment_id=uid(); delivery_id=uid()
            order_no='PED-'+secrets.token_hex(5).upper(); sale_no='VEN-'+secrets.token_hex(5).upper(); tracking='GYM-'+secrets.token_hex(5).upper()
            # Una sola conexión/transaction distribuida en las seis bases del mismo SQL Server.
            with connect('comercio') as cn:
                cur=cn.cursor()
                pending=cur.execute("SELECT TOP 1 id_estado FROM garyu_comercio_db.dbo.estado_pedido WHERE codigo='PENDIENTE'").fetchone()
                delivery_state=cur.execute("SELECT TOP 1 id_estado FROM garyu_logistica_db.dbo.estado_entrega WHERE codigo='PENDIENTE'").fetchone()
                if not pending or not delivery_state: raise ValueError('Faltan estados iniciales. Ejecuta database_sql/configuracion_inicial.sql en SSMS.')
                if not address_id:
                    person=cur.execute('SELECT persona_id FROM garyu_identidad_db.dbo.cliente WHERE id_cliente=?',(client_id,)).fetchone()
                    address_id=uid()
                    cur.execute("""INSERT garyu_identidad_db.dbo.direccion(id_direccion,persona_id,alias,direccion,referencia,departamento,provincia,distrito,es_principal,estado,fecha_registro)
                        VALUES(?,?, 'Casa',?,?,?,?,?,0,1,SYSDATETIME())""",address_id,person[0],address,request.form.get('referencia','').strip() or None,department,province,district)
                # Carrito persistido en comercio
                cur.execute("INSERT garyu_comercio_db.dbo.carrito(id_carrito,cliente_id,fecha_creacion,estado) VALUES(?,?,SYSDATETIME(),'COMPRADO')",cart_id,client_id)
                for p,qty,price in lines:
                    cur.execute("INSERT garyu_comercio_db.dbo.detalle_carrito(id_detalle_carrito,carrito_id,producto_id,nombre_producto,precio_unitario,cantidad,fecha_agregado) VALUES(NEWID(),?,?,?,?,?,SYSDATETIME())",cart_id,p['id_producto'],p['nombre'],price,qty)
                cur.execute("""INSERT garyu_comercio_db.dbo.pedido(id_pedido,cliente_id,direccion_id,carrito_id,estado_id,numero_pedido,fecha_pedido,subtotal,descuento,costo_envio,igv,total,observacion)
                    VALUES(?,?,?,?,?,?,SYSDATETIME(),?,0,?,0,?,?)""",order_id,client_id,address_id,cart_id,pending[0],order_no,subtotal,delivery,total,request.form.get('observacion','').strip() or None)
                for p,qty,price in lines:
                    detail_id=uid()
                    cur.execute("INSERT garyu_comercio_db.dbo.detalle_pedido(id_detalle_pedido,pedido_id,producto_id,nombre_producto,cantidad,precio_unitario) VALUES(?,?,?,?,?,?)",detail_id,order_id,p['id_producto'],p['nombre'],qty,price)
                    # Reservar stock en uno o varios almacenes sin sobreventa.
                    stocks=cur.execute("""SELECT id_inventario,stock_disponible FROM garyu_inventario_db.dbo.inventario WITH (UPDLOCK,HOLDLOCK)
                        WHERE producto_id=? AND stock_disponible>0 ORDER BY stock_disponible DESC""",p['id_producto']).fetchall()
                    remaining=qty
                    for inv in stocks:
                        if remaining<=0: break
                        take=min(remaining,int(inv[1]))
                        cur.execute("UPDATE garyu_inventario_db.dbo.inventario SET stock_reservado=stock_reservado+?,fecha_actualizacion=SYSDATETIME() WHERE id_inventario=?",take,inv[0])
                        cur.execute("INSERT garyu_inventario_db.dbo.reserva_stock(id_reserva,inventario_id,pedido_id,cantidad,estado,fecha_reserva) VALUES(?,?,?,?,'RESERVADA',SYSDATETIME())",uid(),inv[0],order_id,take)
                        remaining-=take
                    if remaining>0: raise ValueError(f'Stock insuficiente para {p["nombre"]}. Actualiza el inventario e inténtalo otra vez.')
                cur.execute("INSERT garyu_comercio_db.dbo.historial_estado_pedido(pedido_id,estado_id,usuario_id,fecha_cambio,observacion) VALUES(?,?,?,SYSDATETIME(),'Pedido creado desde la tienda web')",order_id, pending[0],session['user_id'])
                cur.execute("INSERT garyu_pagos_db.dbo.pago(id_pago,pedido_id,metodo_pago_id,monto,moneda,estado,fecha_registro,observacion) VALUES(?,?,?,?,'PEN','PENDIENTE',SYSDATETIME(),'Pendiente de confirmación del método seleccionado')",payment_id,order_id,method_id,total)
                # La venta se formaliza al marcar el pedido como ENTREGADO; el pedido y el pago quedan pendientes mientras tanto.
                addr=cur.execute('SELECT direccion,referencia,distrito,provincia,departamento FROM garyu_identidad_db.dbo.direccion WHERE id_direccion=?',(address_id,)).fetchone()
                persondata=cur.execute('SELECT COALESCE(nombres,razon_social),telefono FROM garyu_identidad_db.dbo.persona p JOIN garyu_identidad_db.dbo.cliente c ON c.persona_id=p.id_persona WHERE c.id_cliente=?',(client_id,)).fetchone()
                cur.execute("""INSERT garyu_logistica_db.dbo.delivery(id_delivery,pedido_id,direccion_id,destinatario,telefono_contacto,direccion_entrega,referencia,distrito,provincia,departamento,estado_id,codigo_seguimiento,costo_delivery,fecha_registro)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,SYSDATETIME())""",delivery_id,order_id,address_id,persondata[0],persondata[1] or '',addr[0],addr[1],addr[2],addr[3],addr[4],delivery_state[0],tracking,delivery)
                cur.execute("INSERT garyu_logistica_db.dbo.historial_entrega(delivery_id,estado_id,usuario_id,observacion,fecha_cambio) VALUES(?,?,?,'Orden de entrega creada',SYSDATETIME())",delivery_id,delivery_state[0],session['user_id'])
                cn.commit()
            session['cart']={}; session['last_order']=order_no
            flash(f'Pedido {order_no} registrado correctamente. Seguimiento: {tracking}. Pago pendiente de confirmación.','success')
            return redirect(url_for('order_detail',order_no=order_no))
        except Exception as e:
            flash(f'No se pudo registrar el pedido: {e}','danger')
    return render_template('checkout.html',items=[{'product':p,'qty':q,'price':pr,'line':pr*q} for p,q,pr in lines],subtotal=subtotal,delivery=DELIVERY_COST,total=subtotal+DELIVERY_COST,methods=methods,addresses=addresses)

@app.route('/mis-pedidos')
@login_required
def my_orders():
    if not session.get('client_id'): return redirect(url_for('home'))
    orders=query_all('comercio',"""SELECT p.id_pedido,p.numero_pedido,p.fecha_pedido,p.total,ep.nombre estado,
        d.codigo_seguimiento,d.estado_id delivery_estado
        FROM dbo.pedido p JOIN dbo.estado_pedido ep ON ep.id_estado=p.estado_id
        LEFT JOIN garyu_logistica_db.dbo.delivery d ON d.pedido_id=p.id_pedido
        WHERE p.cliente_id=? ORDER BY p.fecha_pedido DESC""",(session['client_id'],))
    return render_template('my_orders.html',orders=orders)

@app.route('/pedido/<order_no>')
@login_required
def order_detail(order_no):
    order=query_one('comercio',"""SELECT p.*,ep.nombre estado, d.codigo_seguimiento,d.estado_id delivery_estado,ee.nombre entrega_estado,
        pg.estado pago_estado,mp.nombre metodo_pago
        FROM dbo.pedido p JOIN dbo.estado_pedido ep ON ep.id_estado=p.estado_id
        LEFT JOIN garyu_logistica_db.dbo.delivery d ON d.pedido_id=p.id_pedido
        LEFT JOIN garyu_logistica_db.dbo.estado_entrega ee ON ee.id_estado=d.estado_id
        LEFT JOIN garyu_pagos_db.dbo.pago pg ON pg.pedido_id=p.id_pedido
        LEFT JOIN garyu_pagos_db.dbo.metodo_pago mp ON mp.id_metodo_pago=pg.metodo_pago_id
        WHERE p.numero_pedido=? AND (?=1 OR p.cliente_id=?)""",(order_no,1 if session.get('is_admin') else 0,session.get('client_id')))
    if not order: abort(404)
    details=query_all('comercio','SELECT nombre_producto,cantidad,precio_unitario,subtotal FROM dbo.detalle_pedido WHERE pedido_id=?',(order['id_pedido'],))
    return render_template('order_detail.html',order=order,details=details)

# Administración
@app.route('/admin')
@admin_required
def admin_dashboard():
    stats={}
    stats['productos']=query_one('catalogo','SELECT COUNT(*) n FROM dbo.producto WHERE estado=1')['n']
    stats['clientes']=query_one('identidad','SELECT COUNT(*) n FROM dbo.cliente WHERE estado=1')['n']
    stats['pedidos']=query_one('comercio','SELECT COUNT(*) n FROM dbo.pedido')['n']
    stats['ventas']=query_one('comercio',"SELECT COALESCE(SUM(total),0) n FROM dbo.venta WHERE estado<>'ANULADA'")['n']
    stats['stock_bajo']=query_one('inventario','SELECT COUNT(*) n FROM (SELECT producto_id,SUM(stock_disponible) stock FROM dbo.inventario GROUP BY producto_id HAVING SUM(stock_disponible)<=5) x')['n']
    latest=query_all('comercio',"""SELECT TOP 10 p.numero_pedido,p.fecha_pedido,p.total,ep.nombre estado,
        COALESCE(per.razon_social,CONCAT(per.nombres,' ',per.apellido_paterno)) cliente
        FROM dbo.pedido p JOIN dbo.estado_pedido ep ON ep.id_estado=p.estado_id
        JOIN garyu_identidad_db.dbo.cliente c ON c.id_cliente=p.cliente_id
        JOIN garyu_identidad_db.dbo.persona per ON per.id_persona=c.persona_id ORDER BY p.fecha_pedido DESC""")
    return render_template('admin/dashboard.html',stats=stats,latest=latest)

@app.route('/admin/productos')
@admin_required
def admin_products():
    products=get_products()
    return render_template('admin/products.html',products=products)

@app.route('/admin/productos/nuevo', methods=['GET','POST'])
@admin_required
def admin_new_product():
    categories=query_all('catalogo','SELECT id_categoria,nombre FROM dbo.categoria WHERE estado=1 ORDER BY nombre')
    subcategories=query_all('catalogo','SELECT id_subcategoria,categoria_id,nombre FROM dbo.subcategoria WHERE estado=1 ORDER BY nombre')
    units=query_all('catalogo','SELECT id_unidad_medida,nombre,abreviatura FROM dbo.unidad_medida WHERE estado=1 ORDER BY nombre')
    brands=query_all('catalogo','SELECT id_marca,nombre FROM dbo.marca WHERE estado=1 ORDER BY nombre')
    warehouses=query_all('inventario','SELECT id_almacen,nombre,codigo FROM dbo.almacen WHERE estado=1 ORDER BY nombre')
    if request.method=='POST':
        try:
            sku=request.form.get('sku','').strip(); name=request.form.get('nombre','').strip()
            subcat=int(request.form.get('subcategoria_id','0')); unit=int(request.form.get('unidad_medida_id','0'))
            brand=request.form.get('marca_id','').strip() or None; brand=int(brand) if brand else None; price=money(request.form.get('precio_venta','0'))
            stock=int(request.form.get('stock','0') or 0); warehouse=request.form.get('almacen_id','').strip() or None
            if not sku or not name or price<0 or stock<0: raise ValueError('Completa SKU, nombre y un precio/stock válido.')
            if not any(int(x['id_subcategoria'])==subcat for x in subcategories): raise ValueError('Selecciona una subcategoría válida.')
            if not any(int(x['id_unidad_medida'])==unit for x in units): raise ValueError('Selecciona una unidad de medida válida.')
            if stock>0 and not warehouse: raise ValueError('Selecciona un almacén para registrar stock inicial.')
            product_id=uid(); image=request.form.get('url_imagen','').strip()
            with connect('catalogo') as cn:
                cur=cn.cursor()
                cur.execute("INSERT dbo.producto(id_producto,subcategoria_id,marca_id,unidad_medida_id,sku,nombre,descripcion,precio_venta,estado,fecha_registro) VALUES(?,?,?,?,?,?,?,?,1,SYSDATETIME())",product_id,subcat,brand,unit,sku,name,request.form.get('descripcion','').strip() or None,price)
                if image:
                    cur.execute("INSERT dbo.imagen_producto(id_imagen,producto_id,url_imagen,texto_alternativo,es_principal,orden,estado) VALUES(NEWID(),?,?,?,1,1,1)",product_id,image,name)
                if warehouse:
                    cur.execute("INSERT garyu_inventario_db.dbo.inventario(id_inventario,almacen_id,producto_id,stock_fisico,stock_reservado,fecha_actualizacion) VALUES(NEWID(),?,?,?,0,SYSDATETIME())",warehouse,product_id,stock)
                cn.commit()
            flash('Producto registrado en el catálogo.','success'); return redirect(url_for('admin_products'))
        except Exception as e: flash(f'No se pudo registrar el producto: {e}','danger')
    return render_template('admin/new_product.html',categories=categories,subcategories=subcategories,units=units,brands=brands,warehouses=warehouses)

@app.route('/admin/inventario')
@admin_required
def admin_inventory():
    rows=query_all('inventario',"""SELECT p.sku,p.nombre,a.nombre almacen,i.stock_fisico,i.stock_reservado,i.stock_disponible,i.fecha_actualizacion
        FROM dbo.inventario i JOIN dbo.almacen a ON a.id_almacen=i.almacen_id
        JOIN garyu_catalogo_db.dbo.producto p ON p.id_producto=i.producto_id ORDER BY p.nombre,a.nombre""")
    return render_template('admin/inventory.html',rows=rows)

@app.route('/admin/clientes')
@admin_required
def admin_customers():
    rows=query_all('identidad',"""SELECT p.numero_documento,p.nombres,p.apellido_paterno,p.apellido_materno,p.telefono,p.correo,c.fecha_alta
        FROM dbo.cliente c JOIN dbo.persona p ON p.id_persona=c.persona_id ORDER BY c.fecha_alta DESC""")
    return render_template('admin/customers.html',rows=rows)

@app.route('/admin/pedidos')
@admin_required
def admin_orders():
    rows=query_all('comercio',"""SELECT p.numero_pedido,p.id_pedido,p.fecha_pedido,p.total,ep.nombre estado,
        COALESCE(per.razon_social,CONCAT(per.nombres,' ',per.apellido_paterno)) cliente,pg.estado pago_estado
        FROM dbo.pedido p JOIN dbo.estado_pedido ep ON ep.id_estado=p.estado_id
        JOIN garyu_identidad_db.dbo.cliente c ON c.id_cliente=p.cliente_id JOIN garyu_identidad_db.dbo.persona per ON per.id_persona=c.persona_id
        LEFT JOIN garyu_pagos_db.dbo.pago pg ON pg.pedido_id=p.id_pedido
        ORDER BY p.fecha_pedido DESC""")
    states=query_all('comercio','SELECT id_estado,codigo,nombre FROM dbo.estado_pedido ORDER BY id_estado')
    return render_template('admin/orders.html',rows=rows,states=states)

@app.post('/admin/pedido/<order_no>/estado')
@admin_required
def update_order_state(order_no):
    new_state=int(request.form.get('estado_id','0'))
    try:
        with connect('comercio') as cn:
            cur=cn.cursor()
            order=cur.execute('SELECT p.id_pedido,p.estado_id,e.codigo FROM dbo.pedido p JOIN dbo.estado_pedido e ON e.id_estado=p.estado_id WHERE p.numero_pedido=?',(order_no,)).fetchone()
            state=cur.execute('SELECT id_estado,codigo FROM dbo.estado_pedido WHERE id_estado=?',(new_state,)).fetchone()
            if not order or not state: raise ValueError('Pedido o estado no válido.')
            order_id=order[0]; code=state[1]
            if order[2] in ('ENTREGADO','CANCELADO') and order[2] != code:
                raise ValueError('Un pedido entregado o cancelado no puede reabrirse ni cambiarse de estado desde este panel.')
            cur.execute('UPDATE dbo.pedido SET estado_id=?,fecha_actualizacion=SYSDATETIME() WHERE id_pedido=?',new_state,order_id)
            cur.execute("INSERT dbo.historial_estado_pedido(pedido_id,estado_id,usuario_id,fecha_cambio,observacion) VALUES(?,?,?,SYSDATETIME(),?)",order_id,new_state,session['user_id'],'Actualización desde administración')
            if code=='CANCELADO':
                reservations=cur.execute("SELECT inventario_id,cantidad FROM garyu_inventario_db.dbo.reserva_stock WITH (UPDLOCK) WHERE pedido_id=? AND estado='RESERVADA'",order_id).fetchall()
                for inv_id,qty in reservations:
                    cur.execute('UPDATE garyu_inventario_db.dbo.inventario SET stock_reservado=CASE WHEN stock_reservado>=? THEN stock_reservado-? ELSE 0 END,fecha_actualizacion=SYSDATETIME() WHERE id_inventario=?',qty,qty,inv_id)
                cur.execute("UPDATE garyu_inventario_db.dbo.reserva_stock SET estado='LIBERADA' WHERE pedido_id=? AND estado='RESERVADA'",order_id)
                cur.execute("UPDATE dbo.venta SET estado='ANULADA' WHERE pedido_id=?",order_id)
            elif code=='ENTREGADO':
                pay_state=cur.execute("SELECT TOP 1 estado FROM garyu_pagos_db.dbo.pago WHERE pedido_id=? ORDER BY fecha_registro DESC",(order_id,)).fetchone()
                if not pay_state or pay_state[0] != 'APROBADO':
                    raise ValueError('Antes de entregar el pedido, confirma el pago desde la columna Pago.')
                reservations=cur.execute("SELECT inventario_id,cantidad FROM garyu_inventario_db.dbo.reserva_stock WITH (UPDLOCK) WHERE pedido_id=? AND estado='RESERVADA'",order_id).fetchall()
                for inv_id,qty in reservations:
                    cur.execute('UPDATE garyu_inventario_db.dbo.inventario SET stock_fisico=CASE WHEN stock_fisico>=? THEN stock_fisico-? ELSE 0 END,stock_reservado=CASE WHEN stock_reservado>=? THEN stock_reservado-? ELSE 0 END,fecha_actualizacion=SYSDATETIME() WHERE id_inventario=?',qty,qty,qty,qty,inv_id)
                cur.execute("UPDATE garyu_inventario_db.dbo.reserva_stock SET estado='CONFIRMADA',fecha_confirmacion=SYSDATETIME() WHERE pedido_id=? AND estado='RESERVADA'",order_id)
                existing_sale=cur.execute('SELECT id_venta FROM dbo.venta WHERE pedido_id=?',(order_id,)).fetchone()
                if existing_sale:
                    cur.execute("UPDATE dbo.venta SET estado='COMPLETADA' WHERE pedido_id=?",order_id)
                else:
                    sale_id=uid(); sale_no='VEN-'+secrets.token_hex(5).upper()
                    order_data=cur.execute('SELECT cliente_id,subtotal,descuento,igv,total FROM dbo.pedido WHERE id_pedido=?',(order_id,)).fetchone()
                    cur.execute("INSERT dbo.venta(id_venta,pedido_id,cliente_id,numero_venta,fecha_venta,subtotal,descuento,igv,total,estado) VALUES(?,?,?,?,SYSDATETIME(),?,?,?,?, 'COMPLETADA')",sale_id,order_id,order_data[0],sale_no,order_data[1],order_data[2],order_data[3],order_data[4])
                    detail_rows=cur.execute('SELECT id_detalle_pedido,producto_id,nombre_producto,cantidad,precio_unitario FROM dbo.detalle_pedido WHERE pedido_id=?',(order_id,)).fetchall()
                    for row in detail_rows:
                        cur.execute("INSERT dbo.detalle_venta(id_detalle_venta,venta_id,detalle_pedido_id,producto_id,nombre_producto,cantidad,precio_unitario) VALUES(NEWID(),?,?,?,?,?,?)",sale_id,row[0],row[1],row[2],row[3],row[4])
            delivery=cur.execute("SELECT id_delivery FROM garyu_logistica_db.dbo.delivery WHERE pedido_id=?",order_id).fetchone()
            if delivery:
                dstate=cur.execute('SELECT id_estado FROM garyu_logistica_db.dbo.estado_entrega WHERE codigo=?',(code,)).fetchone()
                if dstate:
                    cur.execute('UPDATE garyu_logistica_db.dbo.delivery SET estado_id=?,fecha_entrega=CASE WHEN ?=\'ENTREGADO\' THEN SYSDATETIME() ELSE fecha_entrega END WHERE id_delivery=?',dstate[0],code,delivery[0])
                    cur.execute("INSERT garyu_logistica_db.dbo.historial_entrega(delivery_id,estado_id,usuario_id,observacion,fecha_cambio) VALUES(?,?,?, ?,SYSDATETIME())",delivery[0],dstate[0],session['user_id'],'Estado actualizado desde administración')
            cn.commit()
        flash('Estado del pedido actualizado.','success')
    except Exception as e: flash(f'No se pudo actualizar el pedido: {e}','danger')
    return redirect(url_for('admin_orders'))

@app.post('/admin/pago/<order_no>/confirmar')
@admin_required
def confirm_payment(order_no):
    try:
        with connect('pagos') as cn:
            cur=cn.cursor()
            order=cur.execute('SELECT id_pedido FROM garyu_comercio_db.dbo.pedido WHERE numero_pedido=?',(order_no,)).fetchone()
            if not order: raise ValueError('No existe ese pedido.')
            payment=cur.execute("SELECT TOP 1 id_pago,monto,moneda,estado FROM dbo.pago WHERE pedido_id=? ORDER BY fecha_registro DESC",(order[0],)).fetchone()
            if not payment: raise ValueError('No existe un pago para este pedido.')
            if payment[3]=='APROBADO': raise ValueError('El pago ya está confirmado.')
            if payment[3] not in ('PENDIENTE','PROCESANDO'): raise ValueError('El pago no se encuentra en un estado confirmable.')
            reference='MANUAL-'+secrets.token_hex(8).upper()
            cur.execute("UPDATE dbo.pago SET estado='APROBADO',fecha_pago=SYSDATETIME(),observacion='Confirmado manualmente por administración' WHERE id_pago=?",payment[0])
            cur.execute("INSERT dbo.transaccion_pago(id_transaccion,pago_id,proveedor,referencia_proveedor,tipo_transaccion,monto,moneda,estado,fecha_transaccion,respuesta_proveedor) VALUES(?,?, 'VALIDACION_MANUAL',?,'COBRO',?,?,'APROBADA',SYSDATETIME(),'Confirmación manual en GARYU MARKET')",uid(),payment[0],reference,payment[1],payment[2])
            cn.commit()
        flash('Pago confirmado y registrado en el módulo de pagos.','success')
    except Exception as e: flash(f'No se pudo confirmar el pago: {e}','danger')
    return redirect(url_for('admin_orders'))

@app.route('/admin/ventas')
@admin_required
def admin_sales():
    rows=query_all('comercio',"""SELECT v.numero_venta,v.fecha_venta,v.subtotal,v.total,v.estado,p.numero_pedido,
        COALESCE(per.razon_social,CONCAT(per.nombres,' ',per.apellido_paterno)) cliente
        FROM dbo.venta v JOIN dbo.pedido p ON p.id_pedido=v.pedido_id
        JOIN garyu_identidad_db.dbo.cliente c ON c.id_cliente=v.cliente_id JOIN garyu_identidad_db.dbo.persona per ON per.id_persona=c.persona_id
        ORDER BY v.fecha_venta DESC""")
    return render_template('admin/sales.html',rows=rows)

@app.route('/admin/diagnostico')
@admin_required
def diagnostic():
    results={}
    for key,db in DATABASES.items():
        try:
            row=query_one(key,'SELECT DB_NAME() base_actual,COUNT(*) tablas FROM sys.tables')
            results[key]={'database':row['base_actual'],'tables':row['tablas'],'ok':True}
        except Exception as e: results[key]={'database':db,'error':str(e),'ok':False}
    return render_template('admin/diagnostic.html',results=results)

@app.errorhandler(403)
def forbidden(_): return render_template('error.html',code=403,message='No tienes permisos para acceder a esta sección.'),403
@app.errorhandler(404)
def not_found(_): return render_template('error.html',code=404,message='No encontramos la página solicitada.'),404

if __name__=='__main__':
    app.run(host='127.0.0.1',port=int(os.getenv('PORT','5000')),debug=os.getenv('FLASK_DEBUG','0')=='1')
