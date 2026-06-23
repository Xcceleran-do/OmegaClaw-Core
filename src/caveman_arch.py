# src/caveman.py — token compression for OmegaClaw
import re

_static_cache: dict = {}


def _compress_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    fillers = [
        r'\bplease note that\b', r'\bit is important to\b',
        r'\bin order to\b', r'\bthe fact that\b',
        r'\bas mentioned above\b', r'\bkindly\b',
    ]
    for f in fillers:
        text = re.sub(f, '', text, flags=re.IGNORECASE)
    return text.strip()


def _compress_static_section(key: str, text: str) -> str:
    if key not in _static_cache:
        print(f"[caveman] compressing static section: {key}")
        _static_cache[key] = _compress_text(text)
        orig, comp = len(text), len(_static_cache[key])
        print(f"[caveman] {key}: {orig} → {comp} chars ({100*(orig-comp)//orig if orig else 0}% saved)")
    return _static_cache[key]


def compress_context(raw_send: str) -> str:
    """
    Intercepts the full $send string from loop.metta before it hits the LLM.
    
    The string has this structure:
      PROMPT: ...  SKILLS: ...  OUTPUT_FORMAT: ...  LAST_SKILL_USE_RESULTS: ...  HISTORY: ...  TIME: ...  :-:-:-:  HUMAN_MESSAGE or DO NOT SPAM
    
    Strategy:
      - PROMPT + SKILLS: compress once, cache (static)
      - LAST_SKILL_USE_RESULTS: hard cap 4000 chars then compress
      - HISTORY: hard cap 8000 chars then compress
      - OUTPUT_FORMAT + TIME + message: leave as-is (already small)
    """

    print(f"[COMPRESS_CONTEXT] CALLED, len={len(raw_send)}")

    raw_send = raw_send.replace("_quote_", '"').replace("_apostrophe_", "'")

    if ":-:-:-:" in raw_send:
        context_part, message_part = raw_send.split(":-:-:-:", 1)
    else:
        context_part, message_part = raw_send, ""

    # ── 1. PROMPT ──────────────────────────────────────────────────────────
    if "PROMPT:" in context_part and "SKILLS:" in context_part:
        prompt_start = context_part.index("PROMPT:")
        skills_start = context_part.index("SKILLS:")
        prompt_text = context_part[prompt_start + 7:skills_start].strip()
        compressed_prompt = _compress_static_section("PROMPT", prompt_text)
        context_part = (
            context_part[:prompt_start + 7] + " " + compressed_prompt + " " +
            context_part[skills_start:]
        )

    # ── 2. SKILLS ──────────────────────────────────────────────────────────
    if "SKILLS:" in context_part and "OUTPUT_FORMAT:" in context_part:
        skills_start = context_part.index("SKILLS:") + 7
        output_start = context_part.index("OUTPUT_FORMAT:")
        skills_text = context_part[skills_start:output_start].strip()
        compressed_skills = _compress_static_section("SKILLS", skills_text)
        context_part = (
            context_part[:skills_start] + " " + compressed_skills + " " +
            context_part[output_start:]
        )

    # ── 3. LAST_SKILL_USE_RESULTS ──────────────────────────────────────────
    if "LAST_SKILL_USE_RESULTS:" in context_part and "HISTORY:" in context_part:
        lsr_start = context_part.index("LAST_SKILL_USE_RESULTS:") + 23
        hist_start = context_part.index("HISTORY:")
        lsr_text = context_part[lsr_start:hist_start].strip()
        if len(lsr_text) > 4000:
            context_part = (
                context_part[:lsr_start] + " " + lsr_text[-4000:] + " " +
                context_part[hist_start:]
            )
            print(f"[caveman] LSR capped: {len(lsr_text)} → 4000")
        else:
            print(f"[caveman] LSR={len(lsr_text)} (no cap needed)")

    # ── 4. HISTORY ─────────────────────────────────────────────────────────
    if "HISTORY:" in context_part:
        hist_marker = context_part.index("HISTORY:") + 8
        time_match = re.search(r' TIME: \d{4}-\d{2}-\d{2}', context_part[hist_marker:])
        if time_match:
            time_start = hist_marker + time_match.start()
            hist_text = context_part[hist_marker:time_start].strip()
            print(f"[caveman] HIST actual={len(hist_text)}, total_before={len(context_part)}")
            if len(hist_text) > 8000:
                context_part = (
                    context_part[:hist_marker] + " " +
                    hist_text[-8000:] +
                    context_part[time_start:]
                )
                print(f"[caveman] HIST capped, total_after={len(context_part)}")

    # ── Build final + log savings ───────────────────────────────────────────
    final = context_part + (":-:-:-:" + message_part if message_part else "")
    saved = len(raw_send) - len(final)
    if saved > 0:
        print(f"[caveman] {len(raw_send)} → {len(final)} chars ({100*saved//len(raw_send)}% saved)")
    return final