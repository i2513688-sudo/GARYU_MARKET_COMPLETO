/* Ejecutar después de los seis scripts originales. Idempotente. */
USE garyu_identidad_db;
GO
IF NOT EXISTS(SELECT 1 FROM dbo.tipo_documento WHERE codigo='DNI') INSERT dbo.tipo_documento(codigo,nombre,estado) VALUES('DNI','Documento Nacional de Identidad',1);
IF NOT EXISTS(SELECT 1 FROM dbo.tipo_documento WHERE codigo='CE') INSERT dbo.tipo_documento(codigo,nombre,estado) VALUES('CE','Carné de Extranjería',1);
IF NOT EXISTS(SELECT 1 FROM dbo.rol WHERE nombre='Administrador') INSERT dbo.rol(nombre,descripcion,estado) VALUES('Administrador','Acceso administrativo',1);
IF NOT EXISTS(SELECT 1 FROM dbo.rol WHERE nombre='Cliente') INSERT dbo.rol(nombre,descripcion,estado) VALUES('Cliente','Cliente de la tienda virtual',1);
GO
USE garyu_comercio_db;
GO
IF NOT EXISTS(SELECT 1 FROM dbo.estado_pedido WHERE codigo='PENDIENTE') INSERT dbo.estado_pedido(codigo,nombre,descripcion) VALUES('PENDIENTE','Pendiente','Pedido registrado');
IF NOT EXISTS(SELECT 1 FROM dbo.estado_pedido WHERE codigo='CONFIRMADO') INSERT dbo.estado_pedido(codigo,nombre,descripcion) VALUES('CONFIRMADO','Confirmado','Pedido confirmado');
IF NOT EXISTS(SELECT 1 FROM dbo.estado_pedido WHERE codigo='EN_PREPARACION') INSERT dbo.estado_pedido(codigo,nombre,descripcion) VALUES('EN_PREPARACION','En preparación','Pedido en preparación');
IF NOT EXISTS(SELECT 1 FROM dbo.estado_pedido WHERE codigo='EN_CAMINO') INSERT dbo.estado_pedido(codigo,nombre,descripcion) VALUES('EN_CAMINO','En camino','Pedido enviado');
IF NOT EXISTS(SELECT 1 FROM dbo.estado_pedido WHERE codigo='ENTREGADO') INSERT dbo.estado_pedido(codigo,nombre,descripcion) VALUES('ENTREGADO','Entregado','Pedido entregado');
IF NOT EXISTS(SELECT 1 FROM dbo.estado_pedido WHERE codigo='CANCELADO') INSERT dbo.estado_pedido(codigo,nombre,descripcion) VALUES('CANCELADO','Cancelado','Pedido cancelado');
GO
USE garyu_pagos_db;
GO
IF NOT EXISTS(SELECT 1 FROM dbo.metodo_pago WHERE codigo='EFECTIVO') INSERT dbo.metodo_pago(codigo,nombre,descripcion,requiere_proveedor,estado) VALUES('EFECTIVO','Efectivo contra entrega','Pago en efectivo al recibir',0,1);
IF NOT EXISTS(SELECT 1 FROM dbo.metodo_pago WHERE codigo='TRANSFERENCIA') INSERT dbo.metodo_pago(codigo,nombre,descripcion,requiere_proveedor,estado) VALUES('TRANSFERENCIA','Transferencia bancaria','Validación manual de transferencia',0,1);
IF NOT EXISTS(SELECT 1 FROM dbo.metodo_pago WHERE codigo='YAPE_PLIN') INSERT dbo.metodo_pago(codigo,nombre,descripcion,requiere_proveedor,estado) VALUES('YAPE_PLIN','Yape / Plin','Validación manual del pago móvil',0,1);
GO
USE garyu_logistica_db;
GO
IF NOT EXISTS(SELECT 1 FROM dbo.estado_entrega WHERE codigo='PENDIENTE') INSERT dbo.estado_entrega(codigo,nombre,descripcion) VALUES('PENDIENTE','Pendiente','Entrega pendiente');
IF NOT EXISTS(SELECT 1 FROM dbo.estado_entrega WHERE codigo='ASIGNADO') INSERT dbo.estado_entrega(codigo,nombre,descripcion) VALUES('ASIGNADO','Asignado','Repartidor asignado');
IF NOT EXISTS(SELECT 1 FROM dbo.estado_entrega WHERE codigo='EN_CAMINO') INSERT dbo.estado_entrega(codigo,nombre,descripcion) VALUES('EN_CAMINO','En camino','Pedido en ruta');
IF NOT EXISTS(SELECT 1 FROM dbo.estado_entrega WHERE codigo='ENTREGADO') INSERT dbo.estado_entrega(codigo,nombre,descripcion) VALUES('ENTREGADO','Entregado','Pedido entregado');
IF NOT EXISTS(SELECT 1 FROM dbo.estado_entrega WHERE codigo='INCIDENCIA') INSERT dbo.estado_entrega(codigo,nombre,descripcion) VALUES('INCIDENCIA','Incidencia','Incidencia en entrega');
GO
