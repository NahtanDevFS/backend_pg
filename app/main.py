from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routers import usuarios, auth, cultivos, procesamientos, conteos, catalogos

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://frontend-pg.vercel.app"],
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

app.mount("/videos", StaticFiles(directory="uploads"), name="videos")


@app.get("/health")
def health_check():
    return {"status": "ok"}

#comando para levantar el servidor
#uvicorn app.main:app --reload


#comando del tunnel de ngrok
#ngrok http --domain=reluctant-smartly-muppet.ngrok-free.dev 8000
#https://reluctant-smartly-muppet.ngrok-free.dev