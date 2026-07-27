FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system airsense && useradd --system --gid airsense --home-dir /app airsense

COPY pyproject.toml alembic.ini ./
COPY src ./src
COPY migrations ./migrations

# Editable so the compose bind mount over /app/src takes effect and --reload
# picks up edits without a rebuild. The production image in deploy/ installs
# normally.
RUN pip install -e . && chown -R airsense:airsense /app

USER airsense
EXPOSE 8000

CMD ["python", "-m", "airsense.main"]
