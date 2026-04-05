from fastapi import FastAPI

from .routes.repos import router as repos_router


app = FastAPI(title="GitHub Cloud Connector")
app.include_router(repos_router)


@app.get("/health")
async def health():
    return {"status": "ok"}

