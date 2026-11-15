# Hosted Painmelo backend. The static frontend is deployed separately (see vercel.json).
# Mount a volume at /data: it holds the profile, the downloaded datasets and the temporary job store.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git nodejs npm libgl1 libglib2.0-0 libxkbcommon0 libfontconfig1 libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt
COPY leo/package.json leo/package-lock.json leo/
RUN npm --prefix leo ci --omit=dev
COPY . .

ENV GENSHIN_TOOLS_CONFIG=/data/scriptconfig.json \
    PAINMELO_HOSTED=1 \
    PAINMELO_JOBS_DIR=/data/hosted-jobs \
    QT_QPA_PLATFORM=offscreen \
    PYTHONUNBUFFERED=1 \
    PORT=8000
VOLUME /data
EXPOSE 8000

# Create a remote-data profile on first start; the admin then runs `python setupData.py --keep-versions 2` (see README, "Deploying").
CMD ["sh", "-c", "mkdir -p /data && [ -f \"$GENSHIN_TOOLS_CONFIG\" ] || printf '{\\n  \"DataSource\": \"remote\",\\n  \"OutputPath\": \"/data/output\"\\n}\\n' > \"$GENSHIN_TOOLS_CONFIG\"; exec python -m webui --hosted --host 0.0.0.0"]
