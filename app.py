import gradio as gr

from dashboard.api import app as fastapi_app


def status():
    return "Forecast Bust Detection API"


demo = gr.Interface(
    fn=status,
    inputs=[],
    outputs="text",
)

app = gr.mount_gradio_app(
    fastapi_app,
    demo,
    path="/gradio",
)