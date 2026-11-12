"""Start the caption server:  python run.py   (PORT env var changes the port, default 8000)."""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), log_level="info")
