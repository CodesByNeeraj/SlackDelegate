from fastapi import FastAPI
from api.routers import auth

app = FastAPI(title="Delegate API")

app.include_router(auth.router)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "delegate-api"}