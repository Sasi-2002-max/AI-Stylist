from fastapi import FastAPI
from sqlalchemy import text

from backend.database.connection import engine

app = FastAPI(title="AI Fashion Stylist API")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/db-test")
def database_test():
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))

            return {
                "status": "success",
                "database": "connected",
                "result": result.scalar(),
            }

    except Exception as e:
        return {
            "status": "error",
            "database": "connection_failed",
            "error": str(e),
        }