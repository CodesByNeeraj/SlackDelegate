from fastapi import FastAPI
from api.routers import auth, monitor

app = FastAPI(title="Delegate API")

app.include_router(auth.router)
app.include_router(monitor.router)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "delegate-api"}