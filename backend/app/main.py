from fastapi import FastAPI

app = FastAPI(title="AI Chat Title", version="0.1.0")


@app.get("/api/health")
def get_version():
    return {"status": "ok", "version": app.version}
