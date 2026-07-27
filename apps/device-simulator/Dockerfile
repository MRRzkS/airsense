FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system simulator && useradd --system --gid simulator --home-dir /app simulator

COPY pyproject.toml ./
COPY src ./src
COPY data ./data

RUN pip install -e . && chown -R simulator:simulator /app

USER simulator
EXPOSE 8001

CMD ["python", "-m", "simulator.main"]
