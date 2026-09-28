import gradio as gr

from dashboard.api import app as fastapi_app

demo = gr.Interface(
    fn=lambda: "Forecast Bust Detection API",
    inputs=[],
    outputs="text",
)

app = gr.mount_gradio_app(
    fastapi_app,
    demo,
    path="/gradio",
)