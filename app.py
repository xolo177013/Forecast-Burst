import gradio as gr


def status():
    return "Forecast Bust Detection API"


demo = gr.Interface(
    fn=status,
    inputs=[],
    outputs=gr.Textbox(label="Status"),
    title="Forecast Bust Detection",
    description="AI-Based Forecast Bust Detection — SIH 26079",
)


if __name__ == "__main__":
    demo.launch()