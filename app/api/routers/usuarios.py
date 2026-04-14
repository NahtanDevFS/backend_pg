from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas import usuario as schemas
from app.services import usuario_service
from app.api.deps import obtener_usuario_actual
from app.models.models import Usuario

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

@router.post("/", response_model=schemas.UsuarioResponse, status_code=status.HTTP_201_CREATED)
def registrar_usuario(
    usuario_in: schemas.UsuarioCreate,
    db: Session = Depends(get_db)
):

    return usuario_service.crear_usuario(db=db, usuario_in=usuario_in)

@router.get("/me", response_model=schemas.UsuarioResponse)
def leer_usuario_actual(usuario_actual: Usuario = Depends(obtener_usuario_actual)):
    return usuario_actual