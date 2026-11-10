"""Shared parser for grouped, weighted literal wordlist entries."""
from pathlib import Path

WORDLIST = Path(__file__).with_name("wordlist.txt")


def load_wordlist(path=None):
    groups = []
    current = None
    for number, line in enumerate(Path(path or WORDLIST).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            parts = [part.strip() for part in line[1:-1].split("|")]
            if len(parts) not in {4, 5}:
                raise ValueError(f"Invalid wordlist group on line {number}")
            name, cap, scope, points = parts[:4]
            profile = parts[4] if len(parts) == 5 else ("ai_template" if name in {"Source and template indicators", "Emoji indicators"} else "scam")
            cap, points = int(cap), int(points)
            if not name or not 1 <= points <= cap <= 100 or scope not in {"text", "source", "metadata"} or profile not in {"ai_template", "scam"}:
                raise ValueError(f"Invalid wordlist settings on line {number}")
            current = {"name": name, "cap": cap, "scope": scope, "points": points, "profile": profile, "entries": []}
            groups.append(current)
        else:
            if current is None:
                current = {"name": "Wordlist indicators", "cap": 10, "scope": "source", "points": 2, "profile": "ai_template", "entries": []}
                groups.append(current)
            entry = line.casefold()
            if entry not in current["entries"]:
                current["entries"].append(entry)
    return groups


def contains(text, entry):
    """Literal phrase match; avoid matching 'token' inside 'tokenizer'."""
    import re
    left = r"(?<!\w)" if entry[0].isalnum() else ""
    right = r"(?!\w)" if entry[-1].isalnum() else ""
    return re.search(left + re.escape(entry) + right, text.casefold()) is not None
