FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System tooling required for uv, npm, and building common wheels during installs.
RUN apt-get update && \
	apt-get install -y --no-install-recommends bash build-essential curl ca-certificates git nodejs npm && \
	rm -rf /var/lib/apt/lists/*

# Install uv globally.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
	ln -s /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY . /app

# Install helper deps and uvbump so the CLI is available.
RUN uv pip install --system --no-cache-dir Jinja2 && \
	uv pip install --system --no-cache-dir -e .

RUN chmod +x scripts/docker-entrypoint.sh

ENV VERSION_ENV=/app/test/version.env
ENV ROOT_DIR=/app

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["python", "-m", "uvbump", "--root", "test"]
