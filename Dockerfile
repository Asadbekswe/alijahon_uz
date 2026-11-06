# syntax=docker/dockerfile:1.7

# ---------- build stage: compile wheels (mysqlclient needs headers + a compiler) ----------
FROM python:3.12-slim AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /wheels
COPY requirements.txt requirements-dev.txt ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt -r requirements-dev.txt

# ---------- runtime base ----------
FROM python:3.12-slim AS base
ARG APP_UID=1000
ARG APP_GID=1000
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmariadb3 gettext curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid ${APP_GID} app && useradd --uid ${APP_UID} --gid app --home /app --no-create-home app
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt requirements-dev.txt ./
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["entrypoint.sh"]

# ---------- development image (source is bind-mounted by compose) ----------
FROM base AS dev
RUN pip install --no-index --find-links=/wheels -r requirements.txt -r requirements-dev.txt && rm -rf /wheels
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---------- production image ----------
FROM base AS prod
RUN pip install --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels
COPY --chown=app:app . .
RUN mkdir -p /app/media /app/static && chown app:app /app && chown -R app:app /app/media /app/static
USER app
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput -v0
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz/ || exit 1
CMD ["gunicorn", "root.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
