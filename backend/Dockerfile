FROM python:3.12-slim

WORKDIR /app

# Node.js LTS + Claude Code CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates gnupg \
    ffmpeg espeak-ng \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
