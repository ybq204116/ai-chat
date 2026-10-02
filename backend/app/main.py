from fastapi import FastAPI

app = FastAPI(title="AI Chat", version="0.1.0")


@app.get("/api/health")
async def get_health():
    return {"status": "ok", "version": app.version}
