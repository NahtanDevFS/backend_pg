from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, Numeric, ForeignKey, DateTime, Computed, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[str] = mapped_column(String(50), default="operador")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cultivos: Mapped[List["Cultivo"]] = relationship(back_populates="usuario", cascade="all, delete-orphan")


class Cultivo(Base):
    __tablename__ = "cultivos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    ubicacion: Mapped[Optional[str]] = mapped_column(String(255))
    hectareas: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    usuario: Mapped["Usuario"] = relationship(back_populates="cultivos")
    procesamientos: Mapped[List["ProcesamientoVideo"]] = relationship(back_populates="cultivo",
                                                                      cascade="all, delete-orphan")


class CatalogoCalibre(Base):
    __tablename__ = "catalogo_calibres"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False)
    unidades_por_caja: Mapped[int] = mapped_column(Integer, nullable=False)
    peso_promedio_caja_kg: Mapped[float] = mapped_column(Numeric(5, 2))


class ProcesamientoVideo(Base):
    __tablename__ = "procesamientos_video"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cultivo_id: Mapped[int] = mapped_column(ForeignKey("cultivos.id", ondelete="CASCADE"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    video_original_url: Mapped[str] = mapped_column(String, nullable=False)
    video_anotado_url: Mapped[Optional[str]] = mapped_column(String)
    estado: Mapped[str] = mapped_column(String(50), default="pendiente")
    fecha_grabacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cultivo: Mapped["Cultivo"] = relationship(back_populates="procesamientos")
    resultado_ia: Mapped[Optional["ResultadoIA"]] = relationship(back_populates="procesamiento", uselist=False,
                                                                 cascade="all, delete-orphan")


class ResultadoIA(Base):
    __tablename__ = "resultados_ia"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    procesamiento_id: Mapped[int] = mapped_column(ForeignKey("procesamientos_video.id", ondelete="CASCADE"),
                                                  unique=True)
    conteo_maduros: Mapped[int] = mapped_column(Integer, default=0)
    conteo_inmaduros: Mapped[int] = mapped_column(Integer, default=0)
    tiempo_procesamiento_seg: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))

    procesamiento: Mapped["ProcesamientoVideo"] = relationship(back_populates="resultado_ia")


class ClasificacionManual(Base):
    __tablename__ = "clasificaciones_manuales"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    procesamiento_id: Mapped[int] = mapped_column(ForeignKey("procesamientos_video.id", ondelete="CASCADE"))
    calibre_id: Mapped[int] = mapped_column(ForeignKey("catalogo_calibres.id"))
    estado_madurez: Mapped[str] = mapped_column(String(50))  # 'maduro' o 'inmaduro'
    cantidad_melones: Mapped[int] = mapped_column(Integer, nullable=False)
    cajas_calculadas: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    precio_por_caja_aplicado: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    valor_total: Mapped[float] = mapped_column(
        Numeric(12, 2),
        Computed("cajas_calculadas * precio_por_caja_aplicado", persisted=True)
    )
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())