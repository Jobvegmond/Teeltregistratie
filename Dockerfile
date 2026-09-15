FROM python:3.12-slim

WORKDIR /app

# Eerst alleen requirements: dan hoeft pip niet opnieuw te draaien
# bij elke codewijziging.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Streamlit meldt zelf of hij gezond is; compose wacht daarop.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
