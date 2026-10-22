# app/main.py
from fastapi import FastAPI

from app.apis.practice_apis import router as practice_router

app = FastAPI(title="Practice API")

app.include_router(practice_router)
