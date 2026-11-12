FROM node:24.18.0-bookworm-slim AS node-runtime

FROM python:3.12.8-slim-bookworm

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -sf /usr/local/bin/node /usr/bin/node

ENV LANG=C.UTF-8 \
    TZ=Asia/Shanghai \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONHASHSEED=2 \
    HOME=/runtime/home \
    XDG_CONFIG_HOME=/runtime/home/.config \
    XDG_CACHE_HOME=/runtime/home/.cache \
    DAILY_BRIEFING_CLOUD=1 \
    DAILY_BRIEFING_DATA_DIR=/runtime/data \
    BRIEFING_OUTPUT_DIR=/runtime/reports \
    ROTATION_MODEL_DIR=/runtime/models/sw_rotation_model

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg fonts-noto-cjk passwd tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/daily-briefing-pro
COPY deploy/cloud/requirements-cloud.txt /tmp/requirements-cloud.txt

RUN python -m pip install --no-cache-dir -r /tmp/requirements-cloud.txt \
    && if [ "$(dpkg --print-architecture)" = "arm64" ]; then \
        python -m pip install --no-cache-dir --no-deps "akracer==0.0.14"; \
    elif [ "$(dpkg --print-architecture)" = "amd64" ]; then \
        python -m pip install --no-cache-dir --no-deps "py-mini-racer==0.6.0"; \
    else \
        echo "Unsupported architecture: $(dpkg --print-architecture)" >&2; \
        exit 1; \
    fi \
    && python -m pip install --no-cache-dir --no-deps "akshare==1.18.46" \
    && python -c "from py_mini_racer import MiniRacer; assert MiniRacer().eval('1+1') == 2" \
    && npm install --global --no-audit --no-fund @hithink-tech/hithink-finance-cli@0.1.13 \
    && npm cache clean --force \
    && python -m playwright install --with-deps chromium \
    && node --version \
    && rm -rf /var/lib/apt/lists/*

# The runtime home is mounted as a volume, so keep Playwright's browser cache
# in the immutable image tree instead of under $HOME.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

RUN mkdir -p /opt/playwright-browsers \
    && cp -a /runtime/home/.cache/ms-playwright/. /opt/playwright-browsers/ \
    && chmod -R a+rX /opt/playwright-browsers

COPY . /opt/daily-briefing-pro/

RUN mkdir -p /runtime/data /runtime/models /runtime/reports /runtime/home/.codex /runtime/home/.config /runtime/home/.cache \
    && find /opt/daily-briefing-pro -type f -name '*.sh' -exec sed -i 's/\r$//' {} + \
    && groupadd --gid 10001 briefing \
    && useradd --uid 10001 --gid 10001 --home-dir /runtime/home --no-create-home --shell /usr/sbin/nologin briefing \
    && chown -R 10001:10001 /runtime \
    && chmod 755 /opt/daily-briefing-pro/deploy/cloud/entrypoint.sh

WORKDIR /opt/daily-briefing-pro/skills/daily-briefing-pro
USER 10001:10001
ENTRYPOINT ["/opt/daily-briefing-pro/deploy/cloud/entrypoint.sh"]
CMD ["python", "scripts/run_all.py"]
