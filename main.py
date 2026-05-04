import os
from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
import uvicorn

from sms import router as sms_router
from gmail_monitor import router as gmail_router
from gmail_poller import start_poller


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(start_poller())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
app.include_router(sms_router, prefix="/sms")
app.include_router(gmail_router, prefix="/gmail")


@app.get("/health")
def health():
    return {"status": "Dodo is alive 🦤"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
