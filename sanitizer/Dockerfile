FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn
COPY app.py .
RUN mkdir -p data
EXPOSE 6100
CMD ["python", "app.py"]
