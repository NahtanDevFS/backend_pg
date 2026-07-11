import getpass
from app.core.database import SessionLocal
from app.core.security import get_password_hash, validar_password
from app.models.models import Usuario, Rol

# crea un usuario admin pidiendo las credenciales a mano al correrlo

db = SessionLocal()

try:
    rol_admin = db.query(Rol).filter(Rol.nombre == "Administrador").first()
    if not rol_admin:
        print("ERROR: El rol 'Administrador' no existe. ¿Corriste el SQL seed?")
        exit(1)

    nombre = input("Nombre de usuario del nuevo administrador: ").strip()
    if not nombre:
        print("ERROR: El nombre de usuario no puede estar vacío.")
        exit(1)

    existente = db.query(Usuario).filter(Usuario.nombre == nombre).first()
    if existente:
        print(f"ERROR: Ya existe un usuario con el nombre '{nombre}'.")
        exit(1)

    password = getpass.getpass("Contraseña: ")
    password_confirmacion = getpass.getpass("Confirma la contraseña: ")
    if password != password_confirmacion:
        print("ERROR: Las contraseñas no coinciden.")
        exit(1)

    validar_password(password)

    admin = Usuario(
        rol_id=rol_admin.id,
        nombre=nombre,
        password_hash=get_password_hash(password),
        activo=True,
        created_by=None,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    # el admin se apunta a si mismo en created_by
    admin.created_by = admin.id
    db.commit()

    print(f"\nUsuario administrador '{nombre}' creado correctamente (ID: {admin.id}).")

except Exception as e:
    db.rollback()
    print(f"ERROR: {e}")
finally:
    db.close()