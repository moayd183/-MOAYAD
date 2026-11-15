FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 SKYSHIFT_DATA_DIR=/app/local_data
WORKDIR /app
COPY requirements.txt requirements-science.txt ./
RUN pip install --no-cache-dir -r requirements-science.txt
COPY backend ./backend
COPY frontend ./frontend
COPY docs ./docs
COPY README.md README_AR.md ./
RUN mkdir -p /app/local_data
EXPOSE 8000
HEALTHCHECK --interval=45s --timeout=5s --start-period=90s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4)" || exit 1
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
