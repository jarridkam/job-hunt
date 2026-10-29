#!/bin/sh
# Virtual screen for the auto-apply browser, VNC on localhost only (the app proxies it behind login),
# then the web app. Xvfb/x11vnc restart themselves if they die.
set -e
(while true; do Xvfb :99 -screen 0 1280x1000x24 -nolisten tcp >/dev/null 2>&1; sleep 1; done) &
sleep 1
(while true; do x11vnc -display :99 -localhost -rfbport 5900 -forever -shared -nopw -quiet >/dev/null 2>&1; sleep 1; done) &
exec python -m jobhunt.cli serve --host 0.0.0.0 --port 8765 --no-browser
