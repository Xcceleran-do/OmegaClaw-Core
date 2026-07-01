# src/control.py — OmegaClaw shutdown control + startup cleanup
import os
import re
import signal
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

_auth_secret = os.environ.get("OMEGACLAW_AUTH_SECRET", "")
_pid = os.getpid()
_HALT_FLAG_PATH = "/tmp/omegaclaw_halt.flag"
_HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "../memory/history.metta"
)


def _cleanup_noop_history():
    try:
        if not os.path.exists(_HISTORY_PATH):
            return
        with open(_HISTORY_PATH, 'r') as f:
            content = f.read()
        cleaned = re.sub(
            r'\("[^"]+"\s*\n\s*\(\(noop\)\)\s*\n\)',
            '',
            content
        )
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        with open(_HISTORY_PATH, 'w') as f:
            f.write(cleaned)
        print("[control] noop history cleanup done")
    except Exception as e:
        print(f"[control] noop cleanup error: {e}")


def _do_halt():
    print("[control] HALT — writing flag")
    with open(_HALT_FLAG_PATH, "w") as f:
        f.write("halt")


def _do_shutdown():
    print("[control] SHUTDOWN — sending SIGKILL")
    os.kill(_pid, signal.SIGKILL)


class ControlHandler(BaseHTTPRequestHandler):

    def _check_auth(self):
        return self.headers.get("X-Auth-Secret", "") == _auth_secret

    def do_POST(self):
        if not self._check_auth():
            self._respond(401, "unauthorized")
            return
        if self.path == "/halt":
            self._respond(200, "halting after current loop")
            threading.Thread(target=_do_halt, daemon=True).start()
        elif self.path == "/shutdown":
            self._respond(200, "shutting down immediately")
            threading.Thread(target=_do_shutdown, daemon=True).start()
        else:
            self._respond(404, "unknown")

    def do_GET(self):
        if self.path == "/status":
            body = "halting" if os.path.exists(_HALT_FLAG_PATH) else "running"
            self._respond(200, body)
        else:
            self._respond(404, "not found")

    def _respond(self, code, msg):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(msg.encode())

    def log_message(self, *args):
        pass


def start_control(port=7979):
    print(f"[control] start_control called, port={port}")
    print(f"[control] history path: {_HISTORY_PATH}")
    print(f"[control] history exists: {os.path.exists(_HISTORY_PATH)}")
    # Clean stale halt flag
    if os.path.exists(_HALT_FLAG_PATH):
        os.remove(_HALT_FLAG_PATH)
        print("[control] cleared stale halt flag")

    # Clean noop entries from history
    _cleanup_noop_history()

    server = HTTPServer(("0.0.0.0", int(port)), ControlHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[control] API listening on port {port}")


def getLastMessage():
    return ""


def send_message(msg):
    pass

def check_halt_flag() -> str:
    exists = os.path.exists(_HALT_FLAG_PATH)
    print(f"[control] check_halt_flag={exists}")
    return 1 if exists else 0

def halt_agent():
    print("[control] halt_agent called — exiting process")
    os.kill(_pid, signal.SIGTERM)