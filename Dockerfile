# Data Gate — read-only PostgreSQL schema verifier.
# Small, self-contained image usable directly in any CI/CD pipeline.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY datagate ./datagate

# Install the package, then create an unprivileged user and a writable workdir
# where contracts are mounted and the JSON report is written.
RUN pip install . \
    && useradd --create-home --uid 10001 datagate \
    && mkdir -p /work \
    && chown datagate /work

WORKDIR /work
USER datagate

# The tool is strictly read-only against the database and runs as a non-root
# user inside the container.
ENTRYPOINT ["datagate"]
CMD ["--help"]
