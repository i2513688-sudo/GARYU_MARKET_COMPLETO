from getpass import getpass
from database import connect
from werkzeug.security import generate_password_hash
import uuid

def main():
    print('=== Crear administrador GARYU MARKET ===')
    nombre=input('Nombres: ').strip(); apellido=input('Apellido paterno: ').strip()
    correo=input('Correo: ').strip().lower(); usuario=input('Nombre de usuario: ').strip()
    documento=input('DNI: ').strip() or ('ADM'+uuid.uuid4().hex[:8].upper())
    password=getpass('Contraseña (mínimo 8 caracteres): ')
    if not all([nombre,apellido,correo,usuario]) or len(password)<8:
        raise SystemExit('Completa los datos y usa una contraseña de al menos 8 caracteres.')
    with connect('identidad') as cn:
        cur=cn.cursor()
        dtype=cur.execute("SELECT TOP 1 id_tipo_documento FROM dbo.tipo_documento WHERE codigo='DNI'").fetchone()
        role=cur.execute("SELECT TOP 1 id_rol FROM dbo.rol WHERE nombre='Administrador'").fetchone()
        if not dtype or not role: raise SystemExit('Ejecuta database_sql/07_configuracion_inicial.sql primero.')
        if cur.execute('SELECT 1 FROM dbo.usuario WHERE correo_acceso=? OR nombre_usuario=?',(correo,usuario)).fetchone():
            raise SystemExit('Ya existe ese correo o nombre de usuario.')
        persona=str(uuid.uuid4()); user=str(uuid.uuid4())
        cur.execute("""INSERT dbo.persona(id_persona,tipo_documento_id,numero_documento,tipo_persona,nombres,apellido_paterno,correo,fecha_registro,estado)
            VALUES(?,?,?,'NATURAL',?,?,?,SYSDATETIME(),1)""",persona,dtype[0],documento,nombre,apellido,correo)
        cur.execute("INSERT dbo.usuario(id_usuario,persona_id,nombre_usuario,correo_acceso,password_hash,fecha_registro,estado) VALUES(?,?,?,?,?,SYSDATETIME(),1)",user,persona,usuario,correo,generate_password_hash(password))
        cur.execute('INSERT dbo.usuario_rol(usuario_id,rol_id,fecha_asignacion) VALUES(?,?,SYSDATETIME())',user,role[0])
        cn.commit()
    print('Administrador creado. Inicia sesión desde /login.')

if __name__=='__main__': main()
