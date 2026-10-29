"""Take-over view: the server's auto-apply browser, live in your web page (noVNC).

On the server, Chromium runs headed on a virtual display (Xvfb :99) and x11vnc shares that display on
127.0.0.1:5900, never exposed outside the container. This module bridges the page's WebSocket to that
port, only for a logged-in session from this site's own origin. Off the server (no noVNC installed)
the routes say so instead.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import HTMLResponse

from . import auth

NOVNC_DIR = Path(os.environ.get("NOVNC_DIR", "/usr/share/novnc"))
VNC_HOST, VNC_PORT = "127.0.0.1", int(os.environ.get("VNC_PORT", "5900"))

router = APIRouter()


def available() -> bool:
    return (NOVNC_DIR / "vnc.html").exists()


@router.websocket("/vnc/ws")
async def vnc_ws(ws: WebSocket):
    # HTTP middleware doesn't run for WebSockets, so check the session and origin here.
    origin = ws.headers.get("origin", "")
    host = ws.headers.get("x-forwarded-host") or ws.headers.get("host", "")
    if not auth.valid_session(ws.cookies.get(auth.COOKIE)) or not origin.split("://", 1)[-1] == host:
        await ws.close(code=1008)
        return
    try:
        reader, writer = await asyncio.open_connection(VNC_HOST, VNC_PORT)
    except OSError:
        await ws.close(code=1011, reason="browser display not running")
        return
    await ws.accept(subprotocol="binary" if "binary" in ws.headers.get("sec-websocket-protocol", "") else None)

    async def up():
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                data = msg.get("bytes") or (msg.get("text") or "").encode()
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()

    async def down():
        try:
            while data := await reader.read(65536):
                await ws.send_bytes(data)
        finally:
            await ws.close()

    tasks = [asyncio.create_task(up()), asyncio.create_task(down())]
    _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()


def page(request: Request, render) -> HTMLResponse:
    return render(request, "takeover.html", available=available())
