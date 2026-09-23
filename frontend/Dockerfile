FROM python:3.11-slim
WORKDIR /app
COPY frontend/requirements.txt frontend/requirements.txt
RUN pip install --no-cache-dir -r frontend/requirements.txt
COPY frontend/app.py frontend/app.py
CMD ["streamlit", "run", "frontend/app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--browser.gatherUsageStats", "false"]
