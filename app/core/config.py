import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PROJECT_NAME: str = "Tesis Melones API"

    DATABASE_URL: str = os.environ.get("DATABASE_URL")
    SECRET_KEY: str = os.environ.get("SECRET_KEY")

    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7)
    )

    STORAGE_PATH: str = os.getenv("STORAGE_PATH", "./uploads")

    # Secreto compartido con Modal para autenticar el callback de resultados
    MODAL_CALLBACK_SECRET: str = os.environ.get("MODAL_CALLBACK_SECRET")

    # URL pública base del backend, para construir las URLs firmadas que Modal usará para descargar el video original
    PUBLIC_BASE_URL: str = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")

    MODAL_ENDPOINT_URL: str = os.environ.get("MODAL_ENDPOINT_URL", "")

    # Orígenes CORS separados por coma, en producción solo el dominio real
    CORS_ORIGINS: list[str] = [
        origen.strip()
        for origen in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origen.strip()
    ]

    def validar(self):
        faltantes = []
        if not self.DATABASE_URL:
            faltantes.append("DATABASE_URL")
        if not self.SECRET_KEY:
            faltantes.append("SECRET_KEY")
        if not self.MODAL_CALLBACK_SECRET:
            faltantes.append("MODAL_CALLBACK_SECRET")
        if faltantes:
            raise RuntimeError(
                f"Faltan variables de entorno obligatorias: {', '.join(faltantes)}. "
                "Revisar el archivo .env."
            )
        if len(self.SECRET_KEY) < 32:
            raise RuntimeError(
                "SECRET_KEY es demasiado corta, generar una segura con: openssl rand -hex 32"
            )


settings = Settings()
settings.validar()