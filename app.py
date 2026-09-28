import gradio as gr
from dashboard.api import app as fastapi_app


# Gradio interface required by Hugging Face
demo = gr.Interface(
    fn=lambda: "Forecast Bust Detection API",
    inputs=[],
    outputs="text",
)


# Mount Gradio without replacing the FastAPI root
app = gr.mount_gradio_app(
    fastapi_app,
    demo,
    path="/gradio",
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7860,
    )