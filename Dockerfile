FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_BACKEND=firestore \
    SESSION_COOKIE_SECURE=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py game_rules.py firestore_store.py ./
COPY public ./public

EXPOSE 8080
CMD ["sh", "-c", "python server.py --host 0.0.0.0 --port ${PORT:-8080}"]
