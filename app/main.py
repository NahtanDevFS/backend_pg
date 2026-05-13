from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routers import usuarios, auth, cultivos, procesamientos, conteos, catalogos

app = FastAPI(title=settings.PROJECT_NAME)

# Orígenes permitidos:
# localhost:3000  app web (Next.js) en desarrollo
# frontend Vercel app web en producción
# * para app móvil (React Native / Expo no tiene origen fijo)
# En producción debo reemplazar "*" por los dominios exactos
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://frontend-pg.vercel.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",  # cubre previews de Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(cultivos.router)
app.include_router(conteos.router)
app.include_router(procesamientos.router)
app.include_router(catalogos.router)

# Archivos de video servidos estáticamente (solo para compatibilidad con la web existente). Los videos anotados para la app móvil se sirven a través del endpoint autenticado /procesamientos/{id}/video-anotado
app.mount("/videos", StaticFiles(directory="uploads"), name="videos")


@app.get("/health")
def health_check():
    return {"status": "ok"}


# comando para levantar el servidor
# uvicorn app.main:app --reload

# comando del tunnel de ngrok
# ngrok http --domain=reluctant-smartly-muppet.ngrok-free.dev 8000
# https://reluctant-smartly-muppet.ngrok-free.dev