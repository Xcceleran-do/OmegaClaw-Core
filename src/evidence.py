"""Task-scoped tool evidence retained across agent turns."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    text: str


@dataclass(frozen=True)
class EvidenceStats:
    task_generation: int
    evidence_limit_chars: int
    appended_records: int
    appended_chars: int
    retained_records: int
    retained_chars: int
    evicted_records: int
    evicted_chars: int
    truncated_records: int
    truncated_chars: int

    def as_dict(self) -> dict[str, int]:
        return {
            "task_generation": self.task_generation,
            "evidence_limit_chars": self.evidence_limit_chars,
            "appended_records": self.appended_records,
            "appended_chars": self.appended_chars,
            "retained_records": self.retained_records,
            "retained_chars": self.retained_chars,
            "evicted_records": self.evicted_records,
            "evicted_chars": self.evicted_chars,
            "truncated_records": self.truncated_records,
            "truncated_chars": self.truncated_chars,
        }


_records: list[EvidenceRecord] = []
_next_id = 1
_task_generation = 0
_evidence_limit_chars = 0
_appended_records = 0
_appended_chars = 0
_evicted_records = 0
_evicted_chars = 0
_truncated_records = 0
_truncated_chars = 0


def reset():
    """Start a new task with no evidence."""
    global _next_id, _task_generation, _evidence_limit_chars
    global _appended_records, _appended_chars
    global _evicted_records, _evicted_chars
    global _truncated_records, _truncated_chars
    _records.clear()
    _next_id = 1
    _task_generation += 1
    _evidence_limit_chars = 0
    _appended_records = 0
    _appended_chars = 0
    _evicted_records = 0
    _evicted_chars = 0
    _truncated_records = 0
    _truncated_chars = 0


def append(record, max_chars):
    """Append one result and evict only whole older records."""
    global _next_id, _evidence_limit_chars, _appended_records, _appended_chars
    global _evicted_records, _evicted_chars
    global _truncated_records, _truncated_chars
    limit = int(max_chars)
    if limit <= 0:
        reset()
        return ""
    _evidence_limit_chars = limit

    text = str(record)
    original_chars = len(text)
    _appended_records += 1
    _appended_chars += original_chars
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
        _truncated_records += 1
        _truncated_chars += original_chars - len(text)

    _records.append(EvidenceRecord(id=f"tool-result-{_next_id}", text=text))
    _next_id += 1
    while len(render()) > limit and len(_records) > 1:
        evicted = _records.pop(0)
        _evicted_records += 1
        _evicted_chars += len(evicted.text)
    return render()


def render():
    """Render retained records in execution order."""
    return "\n".join(record.text for record in _records)


def records():
    """Return an immutable snapshot for context selection."""
    return tuple(_records)


def stats():
    """Return task-local evidence counters without changing retention behavior."""
    return EvidenceStats(
        task_generation=_task_generation,
        evidence_limit_chars=_evidence_limit_chars,
        appended_records=_appended_records,
        appended_chars=_appended_chars,
        retained_records=len(_records),
        retained_chars=sum(len(record.text) for record in _records),
        evicted_records=_evicted_records,
        evicted_chars=_evicted_chars,
        truncated_records=_truncated_records,
        truncated_chars=_truncated_chars,
    )
