# jobhunt server image: the web app plus a real (headed) Chromium on a virtual display,
# shared over VNC to the in-page take-over view. Playwright's image pins browser + OS deps and is multi-arch,
# so the same file builds on x86 (Hetzner) and ARM (Oracle Cloud's free Ampere servers).
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    JOBHUNT_DATA=/data DISPLAY=:99 NOVNC_DIR=/usr/share/novnc
RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb x11vnc novnc fonts-liberation fonts-noto-color-emoji tini sqlite3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY jobhunt ./jobhunt
RUN pip install --no-cache-dir --break-system-packages .

COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /data && chown pwuser:pwuser /data
USER pwuser
EXPOSE 8765
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
