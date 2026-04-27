from fastapi import FastAPI
from app.core.config import settings
from app.api.routers import usuarios, auth, cultivos, procesamientos, sesiones, catalogos
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3002", "https://frontend-pg.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"], #permite GET, POST, PUT, DELETE
    allow_headers=["*"], #permite enviar tokens de autorización
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(cultivos.router)
app.include_router(sesiones.router)
app.include_router(procesamientos.router)
app.include_router(catalogos.router)

app.mount("/videos", StaticFiles(directory="uploads"), name="videos")


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "El backend está funcionando"}

#comando para levantar el servidor
#uvicorn app.main:app --reload

#comando del tunnel de ngrok
#ngrok http --domain=reluctant-smartly-muppet.ngrok-free.dev 8000