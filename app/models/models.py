from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, Numeric, ForeignKey, DateTime, Boolean, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Rol(Base):
    __tablename__ = "rol"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    usuarios: Mapped[List["Usuario"]] = relationship(back_populates="rol")


class VariedadMelon(Base):
    __tablename__ = "variedad_melon"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


class CatalogoCalibre(Base):
    __tablename__ = "catalogo_calibre"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)


class Usuario(Base):
    __tablename__ = "usuario"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rol_id: Mapped[int] = mapped_column(ForeignKey("rol.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    rol: Mapped["Rol"] = relationship(back_populates="usuarios")
    cultivos: Mapped[List["Cultivo"]] = relationship(back_populates="usuario", cascade="all, delete-orphan")


class Cultivo(Base):
    __tablename__ = "cultivo"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    ubicacion: Mapped[Optional[str]] = mapped_column(String(255))
    hectareas: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    usuario: Mapped["Usuario"] = relationship(back_populates="cultivos")
    procesamientos: Mapped[List["ProcesamientoVideo"]] = relationship(back_populates="cultivo",
                                                                      cascade="all, delete-orphan")


class ProcesamientoVideo(Base):
    __tablename__ = "procesamiento_video"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cultivo_id: Mapped[int] = mapped_column(ForeignKey("cultivo.id", ondelete="CASCADE"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    variedad_id: Mapped[int] = mapped_column(ForeignKey("variedad_melon.id"), nullable=False)
    video_original_url: Mapped[str] = mapped_column(String, nullable=False)
    video_anotado_url: Mapped[Optional[str]] = mapped_column(String)
    estado: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha_grabacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cultivo: Mapped["Cultivo"] = relationship(back_populates="procesamientos")
    resultado: Mapped[Optional["Resultado"]] = relationship(back_populates="procesamiento", uselist=False,
                                                            cascade="all, delete-orphan")


class Resultado(Base):
    __tablename__ = "resultado"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    procesamiento_id: Mapped[int] = mapped_column(ForeignKey("procesamiento_video.id", ondelete="CASCADE"), unique=True,
                                                  nullable=False)
    conteo_ia: Mapped[int] = mapped_column(Integer, nullable=False)
    conteo_final_ajustado: Mapped[Optional[int]] = mapped_column(Integer)
    observaciones_ajuste: Mapped[Optional[str]] = mapped_column(Text)
    tiempo_procesamiento_seg: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))

    procesamiento: Mapped["ProcesamientoVideo"] = relationship(back_populates="resultado")
    calibres: Mapped[List["ResultadoCalibre"]] = relationship(back_populates="resultado", cascade="all, delete-orphan")


class ResultadoCalibre(Base):
    __tablename__ = "resultado_calibre"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    resultado_id: Mapped[int] = mapped_column(ForeignKey("resultado.id", ondelete="CASCADE"), nullable=False)
    calibre_id: Mapped[int] = mapped_column(ForeignKey("catalogo_calibre.id"), nullable=False)
    porcentaje_muestreo: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    cantidad_calculada: Mapped[int] = mapped_column(Integer, nullable=False)

    resultado: Mapped["Resultado"] = relationship(back_populates="calibres")