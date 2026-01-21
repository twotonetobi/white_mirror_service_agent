#!/usr/bin/env python3
import os
from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Example Service")


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/echo")
def echo(message: str = "Hello"):
    return {"echo": message}


if __name__ == "__main__":
    port = int(os.getenv("SERVICE_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
