FROM python:3.12-slim

ENV DJANGO_ALLOWED_HOSTS=0.0.0.0,127.0.0.1,localhost \
    DJANGO_DEBUG=1 \
    DJANGO_STATIC_ROOT=/app/staticfiles \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:${PORT:-8000}"]
