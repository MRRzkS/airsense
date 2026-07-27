# Build context is the repository root, not this directory: the service needs
# the trained artifacts from ml/, and a context rooted here cannot reach them.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system airsense && useradd --system --gid airsense --home-dir /app airsense

COPY apps/ingest-api/pyproject.toml apps/ingest-api/alembic.ini ./
COPY apps/ingest-api/src ./src
COPY apps/ingest-api/migrations ./migrations
COPY ml/artifacts/compressor_degradation.onnx ml/artifacts/feature_spec.json ./models/

# Editable so the compose bind mount over /app/src takes effect and --reload
# picks up edits without a rebuild. The production image in deploy/ installs
# normally.
RUN pip install -e . && chown -R airsense:airsense /app

USER airsense
EXPOSE 8000

CMD ["python", "-m", "airsense.main"]
