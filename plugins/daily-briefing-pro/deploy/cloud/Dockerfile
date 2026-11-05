FROM node:24.18.0-bookworm-slim AS node-runtime

FROM python:3.12.8-slim-bookworm

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/bin/npm /usr/local/bin/npm
COPY --from=node-runtime /usr/local/bin/npx /usr/local/bin/npx
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

ENV LANG=C.UTF-8 \
    TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONHASHSEED=2 \
    HOME=/runtime/home \
    XDG_CONFIG_HOME=/runtime/home/.config \
    XDG_CACHE_HOME=/runtime/home/.cache \
    DAILY_BRIEFING_DATA_DIR=/runtime/data \
    BRIEFING_OUTPUT_DIR=/runtime/reports \
    ROTATION_MODEL_DIR=/runtime/models/sw_rotation_model

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg fonts-noto-cjk passwd tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/daily-briefing-pro
COPY deploy/cloud/requirements-cloud.txt /tmp/requirements-cloud.txt

# CPU-only Torch keeps the Whisper fallback usable without a CUDA host.
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.5.1" \
    && python -m pip install --no-cache-dir -r /tmp/requirements-cloud.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global --no-audit --no-fund @hithink-tech/hithink-finance-cli@0.1.13 \
    && npm cache clean --force

COPY . /opt/daily-briefing-pro/

RUN mkdir -p /runtime/data /runtime/models /runtime/reports /runtime/home/.codex /runtime/home/.config /runtime/home/.cache \
    && groupadd --gid 10001 briefing \
    && useradd --uid 10001 --gid 10001 --home-dir /runtime/home --no-create-home --shell /usr/sbin/nologin briefing \
    && chown -R 10001:10001 /runtime \
    && chmod 755 /opt/daily-briefing-pro/deploy/cloud/entrypoint.sh

WORKDIR /opt/daily-briefing-pro/skills/daily-briefing-pro
USER 10001:10001
ENTRYPOINT ["/opt/daily-briefing-pro/deploy/cloud/entrypoint.sh"]
CMD ["python", "scripts/run_all.py"]
