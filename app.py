import gradio as gr
import os
from dotenv import load_dotenv

load_dotenv()

def get_status():
    return {
        "status": "online",
        "service": "Forecast Bust Detection API",
        "project": "SIH 26079",
        "model_dir": os.getenv("MODEL_DIR", "/app/models")
    }

with gr.Blocks(title="Forecast Bust Detection") as demo:
    gr.Markdown("# SIH 26079 — Forecast Bust Detection API")
    gr.Markdown("Reliability Intelligence Dashboard & API Interface")
    
    with gr.Row():
        check_btn = gr.Button("Check API Status", variant="primary")
        status_output = gr.JSON(label="System Response")
        
    check_btn.click(fn=get_status, inputs=[], outputs=status_output)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)