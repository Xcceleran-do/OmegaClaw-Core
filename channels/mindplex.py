import queue as _queue_module
import threading
from pathlib import Path

_q = _queue_module.Queue()
_server_started = False
_server_lock = threading.Lock()


def start_mindplex():
    global _server_started
    with _server_lock:
        if _server_started:
            return
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

        def _run():
            try:
                import inngest_server
                inngest_server.build_server().serve_forever()
            except Exception as e:
                print(f"[mindplex] Inngest server failed to start: {e}")

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        _server_started = True


def enqueue(post_id, comment_id, preview=""):
    print(f"[mindplex] enqueued post={post_id} comment={comment_id} preview={preview[:60]!r}")
    _q.put({"post_id": str(post_id), "comment_id": str(comment_id), "preview": str(preview)})


def getLastMessage() -> str:
    try:
        ev = _q.get_nowait()
    except _queue_module.Empty:
        return ""
    preview = f" Reader said: \"{ev['preview'][:120]}\"" if ev.get("preview") else ""
    msg = (
        f"A reader commented on your article (post_id={ev['post_id']} comment_id={ev['comment_id']}).{preview}"
        f" Call handle-comment {ev['post_id']} {ev['comment_id']} to reply."
    )
    return msg


def send_message(msg: str):
    pass
