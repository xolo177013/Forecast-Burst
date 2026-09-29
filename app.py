import spaces
import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from dashboard.api import app as fastapi_app


@spaces.GPU
def _gpu_ping():
    # Required by ZeroGPU.
    # The SIH dashboard itself does not use this function.
    return "ok"


with gr.Blocks() as demo:
    gr.Markdown(
        "### Reliability Intelligence\n"
        "SIH 26079 — Forecast Bust Detection"
    )

    output = gr.Textbox(label="GPU Status")

    gr.Button("Test GPU").click(
        fn=_gpu_ping,
        inputs=None,
        outputs=output,
    )


# Keep the FastAPI dashboard at /
# Gradio is available at /gradio
app = gr.mount_gradio_app(
    fastapi_app,
    demo,
    path="/gradio",
)