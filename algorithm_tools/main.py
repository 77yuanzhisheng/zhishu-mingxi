from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from algorithm_tools.router import router as extended_tools_router


app = FastAPI(title="Discrete Math Algorithm Tools API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(extended_tools_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
