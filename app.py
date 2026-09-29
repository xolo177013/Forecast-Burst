import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from dashboard.api import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))