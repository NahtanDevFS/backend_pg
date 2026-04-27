from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import (
    String, Integer, Numeric, ForeignKey, DateTime, Date,
    Boolean, Text, func, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


# ─────────────────────────────────────────────
# CATÁLOGOS BASE
# ─────────────────────────────────────────────

class Rol(Base):
    __tablename__ = "rol"

    id:         Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    nombre:     Mapped[str]           = mapped_column(String(50), nullable=False, unique=True)
    activo:     Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    usuarios: Mapped[List["Usuario"]] = relationship(back_populates="rol", foreign_keys="[Usuario.rol_id]")


class EstadoConteo(Base):
    __tablename__ = "estado_conteo"

    id:         Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    nombre:     Mapped[str]           = mapped_column(String(50), nullable=False, unique=True)
    activo:     Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    conteos: Mapped[List["Conteo"]] = relationship(back_populates="estado", foreign_keys="[Conteo.estado_id]")


class EstadoProcesamiento(Base):
    __tablename__ = "estado_procesamiento"

    id:         Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    nombre:     Mapped[str]           = mapped_column(String(50), nullable=False, unique=True)
    activo:     Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    procesamientos: Mapped[List["ProcesamientoVideo"]] = relationship(back_populates="estado", foreign_keys="[ProcesamientoVideo.estado_id]")


class Variedad(Base):
    __tablename__ = "variedad"

    id:          Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    nombre:      Mapped[str]           = mapped_column(String(100), nullable=False, unique=True)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    activo:      Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    created_at:  Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:  Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by:  Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by:  Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    calibres: Mapped[List["VariedadCalibre"]] = relationship(back_populates="variedad", foreign_keys="[VariedadCalibre.variedad_id]")
    conteos:  Mapped[List["Conteo"]]          = relationship(back_populates="variedad",  foreign_keys="[Conteo.variedad_id]")


class Calibre(Base):
    __tablename__ = "calibre"

    id:          Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    nombre:      Mapped[str]           = mapped_column(String(20), nullable=False, unique=True)
    descripcion: Mapped[Optional[str]] = mapped_column(String(255))
    orden:       Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    activo:      Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    created_at:  Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:  Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by:  Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by:  Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    variedades:      Mapped[List["VariedadCalibre"]]    = relationship(back_populates="calibre",    foreign_keys="[VariedadCalibre.calibre_id]")
    clasificaciones: Mapped[List["ClasificacionCalibre"]] = relationship(back_populates="calibre", foreign_keys="[ClasificacionCalibre.calibre_id]")


class VariedadCalibre(Base):
    __tablename__ = "variedad_calibre"
    __table_args__ = (UniqueConstraint("variedad_id", "calibre_id"),)

    id:          Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    variedad_id: Mapped[int]           = mapped_column(ForeignKey("variedad.id"), nullable=False)
    calibre_id:  Mapped[int]           = mapped_column(ForeignKey("calibre.id"), nullable=False)
    activo:      Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    created_at:  Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:  Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by:  Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by:  Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    variedad: Mapped["Variedad"] = relationship(back_populates="calibres", foreign_keys="[VariedadCalibre.variedad_id]")
    calibre:  Mapped["Calibre"]  = relationship(back_populates="variedades", foreign_keys="[VariedadCalibre.calibre_id]")


# ─────────────────────────────────────────────
# USUARIOS
# ─────────────────────────────────────────────

class Usuario(Base):
    __tablename__ = "usuario"

    id:            Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    rol_id:        Mapped[int]           = mapped_column(ForeignKey("rol.id"), nullable=False)
    nombre:        Mapped[str]           = mapped_column(String(100), nullable=False, unique=True)
    password_hash: Mapped[str]           = mapped_column(String(255), nullable=False)
    activo:        Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    created_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by:    Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by:    Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    rol:     Mapped["Rol"]          = relationship(back_populates="usuarios", foreign_keys="[Usuario.rol_id]")
    cultivos: Mapped[List["Cultivo"]] = relationship(back_populates="usuario", foreign_keys="[Cultivo.usuario_id]", cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# CULTIVO
# ─────────────────────────────────────────────

class Cultivo(Base):
    __tablename__ = "cultivo"

    id:           Mapped[int]             = mapped_column(primary_key=True, autoincrement=True)
    usuario_id:   Mapped[int]             = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    nombre:       Mapped[str]             = mapped_column(String(150), nullable=False)
    ubicacion:    Mapped[Optional[str]]   = mapped_column(String(255))
    hectareas:    Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    total_surcos: Mapped[int]             = mapped_column(Integer, nullable=False)
    activo:       Mapped[bool]            = mapped_column(Boolean, nullable=False, default=True)
    created_at:   Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:   Mapped[datetime]        = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by:   Mapped[int]             = mapped_column(ForeignKey("usuario.id"), nullable=False)
    updated_by:   Mapped[Optional[int]]   = mapped_column(ForeignKey("usuario.id"), nullable=True)

    usuario: Mapped["Usuario"]      = relationship(back_populates="cultivos", foreign_keys="[Cultivo.usuario_id]")
    conteos: Mapped[List["Conteo"]] = relationship(back_populates="cultivo", foreign_keys="[Conteo.cultivo_id]", cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# CONTEO
# ─────────────────────────────────────────────

class Conteo(Base):
    __tablename__ = "conteo"

    id:                     Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    cultivo_id:             Mapped[int]           = mapped_column(ForeignKey("cultivo.id", ondelete="CASCADE"), nullable=False)
    variedad_id:            Mapped[int]           = mapped_column(ForeignKey("variedad.id"), nullable=False)
    estado_id:              Mapped[int]           = mapped_column(ForeignKey("estado_conteo.id"), nullable=False)
    fecha_conteo:           Mapped[date]          = mapped_column(Date, nullable=False, server_default=func.current_date())
    conteo_total_acumulado: Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    observaciones:          Mapped[Optional[str]] = mapped_column(Text)
    activo:                 Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    created_at:             Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:             Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by:             Mapped[int]           = mapped_column(ForeignKey("usuario.id"), nullable=False)
    updated_by:             Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    cultivo:          Mapped["Cultivo"]                    = relationship(back_populates="conteos",        foreign_keys="[Conteo.cultivo_id]")
    variedad:         Mapped["Variedad"]                   = relationship(back_populates="conteos",        foreign_keys="[Conteo.variedad_id]")
    estado:           Mapped["EstadoConteo"]               = relationship(back_populates="conteos",        foreign_keys="[Conteo.estado_id]")
    procesamientos:   Mapped[List["ProcesamientoVideo"]]   = relationship(back_populates="conteo",         foreign_keys="[ProcesamientoVideo.conteo_id]", cascade="all, delete-orphan")
    clasificaciones:  Mapped[List["ClasificacionCalibre"]] = relationship(back_populates="conteo",         foreign_keys="[ClasificacionCalibre.conteo_id]", cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# PROCESAMIENTO DE VIDEO
# ─────────────────────────────────────────────

class ProcesamientoVideo(Base):
    __tablename__ = "procesamiento_video"

    id:                 Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    conteo_id:          Mapped[int]           = mapped_column(ForeignKey("conteo.id", ondelete="CASCADE"), nullable=False)
    usuario_id:         Mapped[int]           = mapped_column(ForeignKey("usuario.id"), nullable=False)
    estado_id:          Mapped[int]           = mapped_column(ForeignKey("estado_procesamiento.id"), nullable=False)
    surco_inicio:       Mapped[int]           = mapped_column(Integer, nullable=False)
    surco_fin:          Mapped[int]           = mapped_column(Integer, nullable=False)
    video_original_url: Mapped[str]           = mapped_column(String, nullable=False)
    video_anotado_url:  Mapped[Optional[str]] = mapped_column(String)
    fecha_grabacion:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), nullable=False)
    activo:             Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    created_at:         Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:         Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by:         Mapped[int]           = mapped_column(ForeignKey("usuario.id"), nullable=False)
    updated_by:         Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    conteo:    Mapped["Conteo"]              = relationship(back_populates="procesamientos",  foreign_keys="[ProcesamientoVideo.conteo_id]")
    estado:    Mapped["EstadoProcesamiento"] = relationship(back_populates="procesamientos",  foreign_keys="[ProcesamientoVideo.estado_id]")
    resultado: Mapped[Optional["ResultadoIa"]] = relationship(back_populates="procesamiento", foreign_keys="[ResultadoIa.procesamiento_id]", uselist=False, cascade="all, delete-orphan")


# ─────────────────────────────────────────────
# RESULTADO DE IA
# ─────────────────────────────────────────────

class ResultadoIa(Base):
    __tablename__ = "resultado_ia"

    id:                       Mapped[int]            = mapped_column(primary_key=True, autoincrement=True)
    procesamiento_id:         Mapped[int]            = mapped_column(ForeignKey("procesamiento_video.id", ondelete="CASCADE"), unique=True, nullable=False)
    conteo_ia:                Mapped[int]            = mapped_column(Integer, nullable=False)
    conteo_ajustado:          Mapped[Optional[int]]  = mapped_column(Integer)
    observaciones_ajuste:     Mapped[Optional[str]]  = mapped_column(Text)
    tiempo_procesamiento_seg: Mapped[Optional[float]]= mapped_column(Numeric(8, 2))
    activo:                   Mapped[bool]           = mapped_column(Boolean, nullable=False, default=True)
    created_at:               Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:               Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by:               Mapped[int]            = mapped_column(ForeignKey("usuario.id"), nullable=False)
    updated_by:               Mapped[Optional[int]]  = mapped_column(ForeignKey("usuario.id"), nullable=True)

    procesamiento: Mapped["ProcesamientoVideo"] = relationship(back_populates="resultado", foreign_keys="[ResultadoIa.procesamiento_id]")


# ─────────────────────────────────────────────
# CLASIFICACIÓN POR CALIBRE
# A nivel de conteo, basada en muestreo manual
# ─────────────────────────────────────────────

class ClasificacionCalibre(Base):
    __tablename__ = "clasificacion_calibre"
    __table_args__ = (UniqueConstraint("conteo_id", "calibre_id"),)

    id:                   Mapped[int]   = mapped_column(primary_key=True, autoincrement=True)
    conteo_id:            Mapped[int]   = mapped_column(ForeignKey("conteo.id", ondelete="CASCADE"), nullable=False)
    calibre_id:           Mapped[int]   = mapped_column(ForeignKey("calibre.id"), nullable=False)
    cantidad_muestreo:    Mapped[int]   = mapped_column(Integer, nullable=False)
    total_muestreo:       Mapped[int]   = mapped_column(Integer, nullable=False)
    porcentaje:           Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    cantidad_extrapolada: Mapped[int]   = mapped_column(Integer, nullable=False)
    activo:               Mapped[bool]  = mapped_column(Boolean, nullable=False, default=True)
    created_at:           Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:           Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by:           Mapped[int]           = mapped_column(ForeignKey("usuario.id"), nullable=False)
    updated_by:           Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    conteo:  Mapped["Conteo"]  = relationship(back_populates="clasificaciones", foreign_keys="[ClasificacionCalibre.conteo_id]")
    calibre: Mapped["Calibre"] = relationship(back_populates="clasificaciones", foreign_keys="[ClasificacionCalibre.calibre_id]")