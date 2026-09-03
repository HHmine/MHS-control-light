"""Start the lamp device gateway without loading the legacy or web Agent."""
from __future__ import annotations

import os

from dotenv import load_dotenv
import uvicorn

load_dotenv()


if __name__ == "__main__":
    uvicorn.run(
        "device_gateway.api:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
