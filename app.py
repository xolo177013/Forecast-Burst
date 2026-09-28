import os
import gradio as gr
from dotenv import load_dotenv

load_dotenv()

def get_status():
    return {
        "status": "online",
        "service": "Forecast Bust Detection API",
        "project": "SIH 26079",
        "model_dir": os.getenv("MODEL_DIR", "/app/models")
    }

# Pass ssr=False directly into gr.Blocks initialization
with gr.Blocks(title="Forecast Bust Detection", ssr=False) as demo:
    gr.Markdown("# SIH 26079 — Forecast Bust Detection API")
    gr.Markdown("Reliability Intelligence Dashboard & API Interface")
    
    with gr.Row():
        check_btn = gr.Button("Check API Status", variant="primary")
        status_output = gr.JSON(label="System Response")
        
    check_btn.click(fn=get_status, inputs=[], outputs=status_output)

# Only launch locally during local testing; HF Space hosts `demo` automatically
if __name__ == "__main__":
    demo.launch()