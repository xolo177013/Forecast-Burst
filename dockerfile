FROM python:3.11-slim
RUN apt-get update && apt-get install -y libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV MODEL_DIR=/app/models
EXPOSE 7860
CMD ["uvicorn","dashboard.api:app","--host","0.0.0.0","--port","7860"]