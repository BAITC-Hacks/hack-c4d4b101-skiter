FROM node:20-alpine
WORKDIR /app
COPY frontend/package*.json frontend/
RUN cd frontend && npm ci
COPY frontend frontend
CMD ["npm", "run", "dev", "--prefix", "frontend", "--", "--host", "0.0.0.0", "--port", "8501"]
