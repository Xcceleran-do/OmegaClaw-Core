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
        record_limit = max(1, limit // 2)
        marker = f"[TOOL_RESULT_TRUNCATED original_chars={len(text)}]"
        keep = max(0, record_limit - len(marker) - 1)
        if keep == 0:
            text = marker[:record_limit]
        else:
            head = (keep + 1) // 2
            tail = keep // 2
            excerpt = text[:head] + (text[-tail:] if tail else "")
            text = f"{marker}\n{excerpt}"

    _records.append(text)
    while len(render()) > limit and len(_records) > 1:
        _records.pop(0)
    return render()


def render():
    """Render retained records in execution order."""
    return "\n".join(_records)
