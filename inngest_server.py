#!/usr/bin/env python3
"""Inngest event subscription server for OmegaPlex engagement agent.

Run it:
  .venv39/bin/python3 inngest_server.py

Register with Inngest Dev Server (local testing):
  npx inngest-cli@latest dev
  Then open http://localhost:8288 and add http://localhost:8788/api/inngest

Register with Inngest Cloud / self-hosted (production):
  Expose publicly (e.g. ngrok http 8788), set INNGEST_IS_PRODUCTION=true in .env,
  then register https://your-url/api/inngest in the Inngest dashboard.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Load .env - try standalone checkout (../.env) then PeTTa-nested checkout (../../.env)
for _env_path in [Path(__file__).parent.parent / ".env",
                   Path(__file__).parent.parent.parent / ".env"]:
    if _env_path.exists():
        for _line in _env_path.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())
        break

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))
import agentverse
import inngest
from inngest._internal.comm_lib import CommHandler, CommRequest

PORT = int(os.environ.get("INNGEST_PORT", "8788"))
AUTHOR_ID = int(os.environ.get("MINDPLEX_AUTHOR_ID", "4"))
SERVE_PATH = "/api/inngest"
SERVE_ORIGIN = os.environ.get("INNGEST_SERVE_ORIGIN", f"http://host.docker.internal:{PORT}")

client = inngest.Inngest(
    app_id="omegaplex",
    event_key=os.environ.get("INNGEST_EVENT_KEY"),
    signing_key=os.environ.get("INNGEST_SIGNING_KEY"),
    is_production=os.environ.get("INNGEST_IS_PRODUCTION", "false").lower() == "true",
    api_base_url=os.environ.get("INNGEST_API_BASE_URL"),
    event_api_base_url=os.environ.get("INNGEST_EVENT_API_BASE_URL"),
)


@client.create_function(
    fn_id="handle-comment-created",
    trigger=inngest.TriggerEvent(event="mindplex/comment.created"),
)
def handle_comment_created(ctx: inngest.Context, step: inngest.StepSync) -> dict:
    event_data = ctx.event.data
    post_id = event_data["payload"]["postId"]
    comment_id = event_data["subject"]["id"]
    actor_id = event_data["actor"]["id"]

    if actor_id == AUTHOR_ID:
        print(f"[handle_comment_created] skipping self-comment from actor {actor_id}")
        return {"status": "skipped", "reason": "self-comment"}

    result = step.run(
        "draft-and-post-reply",
        lambda: agentverse.handle_comment(post_id, comment_id),
    )
    return {"status": "handled", "result": result}


comm = CommHandler(
    client=client,
    framework=inngest._internal.server_lib.Framework.FLASK,
    functions=[handle_comment_created],
)


class InngestHandler(BaseHTTPRequestHandler):
    def _build_comm_request(self, body: bytes = b"") -> CommRequest:
        parsed = urlparse(self.path)
        query = {k: v[0] if len(v) == 1 else v
                 for k, v in parse_qs(parsed.query).items()}
        headers = {k.lower(): v for k, v in self.headers.items()}
        return CommRequest(
            body=body,
            headers=headers,
            query_params=query,
            raw_request=self,
            request_url=f"http://localhost:{PORT}{self.path}",
            serve_origin=SERVE_ORIGIN,
            serve_path=SERVE_PATH,
        )

    def _send_comm_response(self, resp):
        self.send_response(resp.status_code)
        for k, v in resp.headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp.body_bytes())

    def do_GET(self):
        if not self.path.startswith(SERVE_PATH):
            self.send_response(404); self.end_headers(); return
        self._send_comm_response(comm.get_sync(self._build_comm_request()))

    def do_PUT(self):
        if not self.path.startswith(SERVE_PATH):
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self._send_comm_response(comm.put_sync(self._build_comm_request(body)))

    def do_POST(self):
        if not self.path.startswith(SERVE_PATH):
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        print(f"[POST] from={self.client_address} path={self.path}")
        self._send_comm_response(comm.post_sync(self._build_comm_request(body)))

    def log_message(self, fmt, *args):
        print(f"[inngest] {fmt % args}")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), InngestHandler)
    print(f"Inngest server listening on http://0.0.0.0:{PORT}{SERVE_PATH}")
    server.serve_forever()
