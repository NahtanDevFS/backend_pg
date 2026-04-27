from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.models import Usuario, Rol

db = SessionLocal()

try:
    rol_admin = db.query(Rol).filter(Rol.nombre == "Administrador").first()
    if not rol_admin:
        print("ERROR: El rol 'Administrador' no existe. ¿Corriste el SQL seed?")
        exit(1)

    admin = Usuario(
        rol_id=rol_admin.id,
        nombre="jonathan",
        password_hash=get_password_hash("franco04"),
        activo=True,
        created_by=None
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    # El admin se referencia a sí mismo en created_by
    admin.created_by = admin.id
    db.commit()

    print(f"✓ Usuario administrador creado correctamente.")
    print(f"  Usuario: jonathan")
    print(f"  Contraseña: franco04")
    print(f"  ID: {admin.id}")

except Exception as e:
    db.rollback()
    print(f"ERROR: {e}")
finally:
    db.close()