import gradio as gr
from dashboard.api import app as fastapi_app

# Define your Gradio Interface/Blocks
with gr.Blocks(title="Forecast Bust Detection") as demo:
    gr.Markdown("# SIH 26079 — Forecast Bust Detection API")
    
    status_output = gr.Textbox(label="System Status", value="API & Dashboard Active")
    
    # Add your interactive inputs, buttons, and endpoints here
    # Example: UI components calling backend logic directly from dashboard.api

# Launch directly if executed as main script, otherwise expose `demo` for HF SDK
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)