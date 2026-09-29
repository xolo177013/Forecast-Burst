import os
import spaces
import gradio as gr
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from dashboard.api import app as fastapi_app


@spaces.GPU
def _gpu_ping():
    # Never used by the dashboard. ZeroGPU only requires that one exists.
    return "ok"


with gr.Blocks() as demo:
    gr.Markdown("Reliability Intelligence: open the main page at `/`.")
    gr.Button("ping").click(_gpu_ping, None, gr.Textbox())

# Gradio lives at /gradio, so your dashboard at "/" and all API routes stay untouched
app = gr.mount_gradio_app(fastapi_app, demo, path="/gradio")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))