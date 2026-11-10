"""Explainable, uncalibrated page-content review heuristic (0-100)."""
import re
from collections import Counter
from html.parser import HTMLParser
from wordlist import load_wordlist, contains

VERSION = "dual-wordlist-v3"
CAVEAT = "Independent heuristic scores, not probabilities of fraud or AI authorship. AI/platform traces do not imply fraud. Page text and source only; message bodies are not scored."
BANDS = "Each score: 0-19 Low; 20-49 Moderate; 50-100 High indicator presence. Only high scam indicators trigger review flags."


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.parts = []
        self.generators = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "meta" and attributes.get("name", "").casefold() == "generator":
            self.generators.append(attributes.get("content", ""))
        if tag in {"script", "style", "head", "svg", "noscript"}:
            self.hidden.append(tag)
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()
        if tag in {"p", "div", "li", "h1", "h2", "h3", "section"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


PROFILES = ("ai_template", "scam")


def summarize(profile, factors, enough_text, unavailable=None):
    caveat = ("Builder traces and AI-related claims do not establish AI authorship or fraud."
              if profile == "ai_template" else "Warning phrases require contextual review; this is not a fraud probability or a safety verdict.")
    if unavailable or (not enough_text and not factors):
        return {"score": None, "level": "Not assessed", "flagged": False,
                "explanation": unavailable or "Too little readable text or relevant wordlist evidence was available for this assessment.",
                "action": "Review the source manually if needed.", "factors": [], "caveat": caveat,
                "wordlist_points": 0, "supplementary_points": 0}
    score = min(100, sum(f["points"] for f in factors))
    level = "High" if score >= 50 else "Moderate" if score >= 20 else "Low"
    explanation = ("Signals detected: " + "; ".join(f["name"].lower() for f in factors) + "." if factors else
                   "No configured " + ("AI/template" if profile == "ai_template" else "scam") + " indicators were found. This is not proof of authorship or safety.")
    if not enough_text:
        explanation += " Limited readable text; assessment relies on relevant wordlist evidence."
    action = ("Treat these as platform/style clues and AI-related claims; verify authorship separately."
              if profile == "ai_template" else {
                  "High": "Prioritize human review; independently verify the identity and requested action.",
                  "Moderate": "Review the request and verify it through an independent channel.",
                  "Low": "Consider source and context; a low score does not establish safety."}[level])
    return {"score": score, "level": level, "flagged": profile == "scam" and score >= 50,
            "explanation": explanation, "action": action, "factors": factors, "caveat": caveat,
            "wordlist_points": sum(f["points"] for f in factors if f.get("origin") == "wordlist"),
            "supplementary_points": sum(f["points"] for f in factors if f.get("origin") != "wordlist")}


def package(profiles):
    # Deprecated top-level fields alias the scam assessment for older clients.
    # There is deliberately no combined AI/scam score.
    return {"version": VERSION, **profiles["scam"], "caveat": CAVEAT, **profiles}


def unassessed(reason):
    return package({profile: summarize(profile, [], False, reason) for profile in PROFILES})


def assess(html, status=200, content_type="text/html", wordlist_path=None):
    if not 200 <= status < 300:
        return unassessed("The page did not return a successful HTTP response; its content was not scored.")
    if not any(kind in content_type.lower() for kind in ("text/html", "text/plain", "application/xhtml")):
        return unassessed("This content format is not supported for text assessment.")
    metadata = ""
    if "text/plain" in content_type.lower():
        text = html
    else:
        parser = VisibleText()
        parser.feed(html)
        text = "".join(parser.parts)
        metadata = " ".join(parser.generators)
    text = re.sub(r"[^\S\n]+", " ", text).strip()
    enough_text = len(re.findall(r"\w+", text)) >= 8 and len(text) >= 40
    sentences = [s.strip() for s in re.split(r"[.!?\n]+", text) if s.strip()]
    factors = {profile: [] for profile in PROFILES}
    for group in load_wordlist(wordlist_path):
        profile = group["profile"]
        entries = []
        for entry in group["entries"]:
            if group["scope"] in {"source", "metadata"}:
                found = contains(html if group["scope"] == "source" else metadata, entry)
            else:
                found = any(contains(sentence, entry) and (profile != "scam" or not re.search(
                    r"\b(never|do not|don't|avoid|nunca|jamás|no compartas|no envíes|no envies)\b", sentence, re.I)) for sentence in sentences)
            if found:
                entries.append(entry)
        if entries:
            factors[profile].append({"name": group["name"], "points": min(group["cap"], len(entries)*group["points"]),
                                     "evidence": ("Generator metadata: " + metadata if group["scope"] == "metadata" else "Wordlist matches: " + "; ".join(entries))[:180],
                                     "entries": entries, "origin": "wordlist", "scope": group["scope"]})
    counts = Counter(re.sub(r"\s+", " ", s.lower()) for s in sentences if len(s) >= 35)
    repeated = next((s for s, count in counts.items() if count >= 3), None)
    if repeated:
        factors["ai_template"].append({"name": "Repeated language", "points": 10, "evidence": repeated[:180],
            "origin": "supplementary", "note": "Duplicate responsive layouts can also cause repetition."})
    words = re.findall(r"\b[^\W\d_]+\b", text)
    capitals = sum(len(w) > 2 and w.isupper() for w in words)
    if re.search(r"[!?]{3,}", text) or (len(words) >= 20 and capitals / len(words) > 0.35):
        factors["ai_template"].append({"name": "Unusual formatting", "points": 5,
            "evidence": "Repeated punctuation or a high proportion of capitalized words.", "origin": "supplementary"})
    return package({profile: summarize(profile, factors[profile], enough_text) for profile in PROFILES})
