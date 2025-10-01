#!/usr/bin/env python3
import uvicorn
from fastapi import FastAPI

import fastapi_structured_logging

# Set output to text if stdout is a tty, structured json if not
fastapi_structured_logging.setup_logging()

logger = fastapi_structured_logging.get_logger()

app = FastAPI()

app.add_middleware(fastapi_structured_logging.AccessLogMiddleware)


@app.get("/")
async def root():
    logger.info("Handling root endpoint accessed")
    return {"message": "Hello World"}


@app.get("/hello")
def hello(who: str):
    logger.info(
        "log line message",
        context_info1="value1",
        context_info2="value2",
    )
    return {"message": f"Hello {who}"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
