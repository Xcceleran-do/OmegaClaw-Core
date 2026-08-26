"""Task-scoped tool evidence retained across agent turns."""


_records = []


def reset():
    """Start a new task with no evidence."""
    _records.clear()


def append(record, max_chars):
    """Append one result and evict only whole older records."""
    limit = int(max_chars)
    if limit <= 0:
        reset()
        return ""

    text = str(record)
    if len(text) > limit:
        marker = f"[TOOL_RESULT_TRUNCATED original_chars={len(text)}]"
        keep = max(0, limit - len(marker) - 1)
        text = marker[:limit] if keep == 0 else f"{marker}\n{text[-keep:]}"

    _records.append(text)
    while len(render()) > limit and len(_records) > 1:
        _records.pop(0)
    return render()


def render():
    """Render retained records in execution order."""
    return "\n".join(_records)
