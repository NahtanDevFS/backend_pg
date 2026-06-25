from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import (
    String, Integer, Numeric, ForeignKey, DateTime, Date,
    Boolean, Text, func, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Rol(Base):
    __tablename__ = "rol"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    usuarios: Mapped[List["Usuario"]] = relationship(back_populates="rol", foreign_keys="[Usuario.rol_id]")


class EstadoConteo(Base):
    __tablename__ = "estado_conteo"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    conteos: Mapped[List["Conteo"]] = relationship(back_populates="estado", foreign_keys="[Conteo.estado_id]")


class EstadoProcesamiento(Base):
    __tablename__ = "estado_procesamiento"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    procesamientos: Mapped[List["ProcesamientoVideo"]] = relationship(back_populates="estado", foreign_keys="[ProcesamientoVideo.estado_id]")


class VariedadMelon(Base):
    __tablename__ = "variedad_melon"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    calibres: Mapped[List["VariedadMelonCalibre"]] = relationship(back_populates="variedad", foreign_keys="[VariedadMelonCalibre.variedad_id]")
    conteos: Mapped[List["Conteo"]] = relationship(back_populates="variedad", foreign_keys="[Conteo.variedad_id]")


class CalibreMelon(Base):
    __tablename__ = "calibre_melon"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    descripcion: Mapped[Optional[str]] = mapped_column(String(255))
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    variedades: Mapped[List["VariedadMelonCalibre"]] = relationship(back_populates="calibre", foreign_keys="[VariedadMelonCalibre.calibre_id]")
    clasificaciones: Mapped[List["ClasificacionCalibreConteo"]] = relationship(back_populates="calibre", foreign_keys="[ClasificacionCalibreConteo.calibre_id]")


class VariedadMelonCalibre(Base):
    __tablename__ = "variedad_melon_calibre"
    __table_args__ = (UniqueConstraint("variedad_id", "calibre_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    variedad_id: Mapped[int] = mapped_column(ForeignKey("variedad_melon.id"), nullable=False)
    calibre_id: Mapped[int] = mapped_column(ForeignKey("calibre_melon.id"), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    variedad: Mapped["VariedadMelon"] = relationship(back_populates="calibres", foreign_keys="[VariedadMelonCalibre.variedad_id]")
    calibre:  Mapped["CalibreMelon"]  = relationship(back_populates="variedades", foreign_keys="[VariedadMelonCalibre.calibre_id]")


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rol_id: Mapped[int] = mapped_column(ForeignKey("rol.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    rol: Mapped["Rol"] = relationship(back_populates="usuarios", foreign_keys="[Usuario.rol_id]")
    # cultivos_creados: campos de cultivo donde este usuario figura como creador (auditoría)
    cultivos_creados: Mapped[List["CampoCultivo"]] = relationship(back_populates="creador", foreign_keys="[CampoCultivo.usuario_id]")
    # cultivos_asignados: campos de cultivo a los que tiene acceso como operador
    cultivos_asignados: Mapped[List["CampoCultivoOperador"]] = relationship(back_populates="operador", foreign_keys="[CampoCultivoOperador.usuario_id]")

class Departamento(Base):
    __tablename__ = "departamento"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    municipios: Mapped[List["Municipio"]] = relationship(back_populates="departamento", foreign_keys="[Municipio.departamento_id]")


class Municipio(Base):
    __tablename__ = "municipio"
    __table_args__ = (UniqueConstraint("nombre", "departamento_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    departamento_id: Mapped[int] = mapped_column(ForeignKey("departamento.id"), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    departamento: Mapped["Departamento"] = relationship(back_populates="municipios", foreign_keys="[Municipio.departamento_id]")
    campos: Mapped[List["CampoCultivo"]] = relationship(back_populates="municipio", foreign_keys="[CampoCultivo.municipio_id]")

class CampoCultivo(Base):
    __tablename__ = "campo_cultivo"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # usuario_id: auditoría quién creó el campo de cultivo
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    municipio_id: Mapped[int] = mapped_column(ForeignKey("municipio.id"), nullable=False)
    # ubicacion: dirección/referencia libre dentro del municipio (sector, parcela, km). Opcional.
    ubicacion: Mapped[Optional[str]] = mapped_column(String(255))
    hectareas: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    total_surcos: Mapped[int] = mapped_column(Integer, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    creador: Mapped["Usuario"] = relationship(back_populates="cultivos_creados", foreign_keys="[CampoCultivo.usuario_id]")
    municipio: Mapped["Municipio"] = relationship(back_populates="campos", foreign_keys="[CampoCultivo.municipio_id]")
    operadores: Mapped[List["CampoCultivoOperador"]] = relationship(back_populates="cultivo", foreign_keys="[CampoCultivoOperador.campo_cultivo_id]", cascade="all, delete-orphan")
    conteos: Mapped[List["Conteo"]] = relationship(back_populates="cultivo", foreign_keys="[Conteo.campo_cultivo_id]", cascade="all, delete-orphan")


class CampoCultivoOperador(Base):
    __tablename__ = "campo_cultivo_operador"
    __table_args__ = (UniqueConstraint("campo_cultivo_id", "usuario_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campo_cultivo_id: Mapped[int] = mapped_column(ForeignKey("campo_cultivo.id", ondelete="CASCADE"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    desactivado_por_campo_cultivo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    cultivo: Mapped["CampoCultivo"] = relationship(back_populates="operadores", foreign_keys="[CampoCultivoOperador.campo_cultivo_id]")
    operador: Mapped["Usuario"] = relationship(back_populates="cultivos_asignados", foreign_keys="[CampoCultivoOperador.usuario_id]")


class Conteo(Base):
    __tablename__ = "conteo"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campo_cultivo_id: Mapped[int] = mapped_column(ForeignKey("campo_cultivo.id", ondelete="CASCADE"), nullable=False)
    variedad_id: Mapped[int] = mapped_column(ForeignKey("variedad_melon.id"), nullable=False)
    estado_id: Mapped[int] = mapped_column(ForeignKey("estado_conteo.id"), nullable=False)
    fecha_conteo: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())
    conteo_total_acumulado: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observaciones: Mapped[Optional[str]] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    desactivado_por_campo_cultivo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    total_surcos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    promedio_confianza_sesion: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    porcentaje_baja_confianza_sesion: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))

    cultivo: Mapped["CampoCultivo"] = relationship(back_populates="conteos", foreign_keys="[Conteo.campo_cultivo_id]")
    variedad: Mapped["VariedadMelon"] = relationship(back_populates="conteos", foreign_keys="[Conteo.variedad_id]")
    estado: Mapped["EstadoConteo"] = relationship(back_populates="conteos", foreign_keys="[Conteo.estado_id]")
    procesamientos: Mapped[List["ProcesamientoVideo"]]   = relationship(back_populates="conteo", foreign_keys="[ProcesamientoVideo.conteo_id]", cascade="all, delete-orphan")
    clasificaciones: Mapped[List["ClasificacionCalibreConteo"]] = relationship(back_populates="conteo", foreign_keys="[ClasificacionCalibreConteo.conteo_id]", cascade="all, delete-orphan")


class ProcesamientoVideo(Base):
    __tablename__ = "procesamiento_video"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conteo_id: Mapped[int] = mapped_column(ForeignKey("conteo.id", ondelete="CASCADE"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    estado_id: Mapped[int] = mapped_column(ForeignKey("estado_procesamiento.id"), nullable=False)
    surco_inicio: Mapped[int] = mapped_column(Integer, nullable=False)
    surco_fin: Mapped[int] = mapped_column(Integer, nullable=False)
    video_original_url: Mapped[str] = mapped_column(String, nullable=False)
    video_anotado_url: Mapped[Optional[str]] = mapped_column(String)
    fecha_grabacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    desactivado_por_campo_cultivo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    conteo: Mapped["Conteo"] = relationship(back_populates="procesamientos", foreign_keys="[ProcesamientoVideo.conteo_id]")
    estado: Mapped["EstadoProcesamiento"] = relationship(back_populates="procesamientos", foreign_keys="[ProcesamientoVideo.estado_id]")
    resultado: Mapped[Optional["ResultadoIa"]] = relationship(back_populates="procesamiento",  foreign_keys="[ResultadoIa.procesamiento_id]", uselist=False, cascade="all, delete-orphan")


class ResultadoIa(Base):
    __tablename__ = "resultado_ia"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    procesamiento_id: Mapped[int] = mapped_column(ForeignKey("procesamiento_video.id", ondelete="CASCADE"), unique=True, nullable=False)
    conteo_ia: Mapped[int] = mapped_column(Integer, nullable=False)
    conteo_ajustado: Mapped[Optional[int]] = mapped_column(Integer)
    observaciones_ajuste: Mapped[Optional[str]] = mapped_column(Text)
    tiempo_procesamiento_seg: Mapped[Optional[float]] = mapped_column(Numeric(8, 2))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    promedio_confianza: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    porcentaje_baja_confianza: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    total_frames_procesados: Mapped[Optional[int]] = mapped_column(Integer)

    procesamiento: Mapped["ProcesamientoVideo"] = relationship(back_populates="resultado", foreign_keys="[ResultadoIa.procesamiento_id]")


class ClasificacionCalibreConteo(Base):
    __tablename__ = "clasificacion_calibre_conteo"
    __table_args__ = (UniqueConstraint("conteo_id", "calibre_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conteo_id: Mapped[int] = mapped_column(ForeignKey("conteo.id", ondelete="CASCADE"), nullable=False)
    calibre_id: Mapped[int] = mapped_column(ForeignKey("calibre_melon.id"), nullable=False)
    cantidad_muestreo: Mapped[int] = mapped_column(Integer, nullable=False)
    total_muestreo: Mapped[int] = mapped_column(Integer, nullable=False)
    porcentaje: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    cantidad_extrapolada: Mapped[int] = mapped_column(Integer, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    desactivado_por_campo_cultivo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    conteo:  Mapped["Conteo"]  = relationship(back_populates="clasificaciones", foreign_keys="[ClasificacionCalibreConteo.conteo_id]")
    calibre: Mapped["CalibreMelon"] = relationship(back_populates="clasificaciones", foreign_keys="[ClasificacionCalibreConteo.calibre_id]")