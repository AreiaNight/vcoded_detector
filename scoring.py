"""Explainable, uncalibrated page-content review heuristic (0-100)."""
import re
from collections import Counter
from html.parser import HTMLParser
from wordlist import load_wordlist, contains

VERSION = "wordlist-review-v2"
CAVEAT = "Experimental review priority, not a probability of fraud or AI authorship. Page text and source only; message bodies are not scored."
BANDS = "0-19 Low; 20-49 Moderate; 50-100 High. Scores of 50 or more are flagged for review."


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
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


def unassessed(reason):
    return {"version": VERSION, "score": None, "level": "Not assessed", "flagged": False,
            "explanation": reason, "action": "Review the source manually if needed.",
            "factors": [], "caveat": CAVEAT}


def assess(html, status=200, content_type="text/html", wordlist_path=None):
    if not 200 <= status < 300:
        return unassessed("The page did not return a successful HTTP response; its content was not scored.")
    if not any(kind in content_type.lower() for kind in ("text/html", "text/plain", "application/xhtml")):
        return unassessed("This content format is not supported for text assessment.")
    if "text/plain" in content_type.lower():
        text = html
    else:
        parser = VisibleText()
        parser.feed(html)
        text = "".join(parser.parts)
    text = re.sub(r"[^\S\n]+", " ", text).strip()
    enough_text = len(re.findall(r"\w+", text)) >= 8 and len(text) >= 40
    sentences = [s.strip() for s in re.split(r"[.!?\n]+", text) if s.strip()]
    factors = []

    def add(name, points, evidence):
        factors.append({"name": name, "points": points, "evidence": evidence[:180]})

    for group in load_wordlist(wordlist_path):
        entries = []
        for entry in group["entries"]:
            if group["scope"] == "source":
                found = contains(html, entry)
            else:
                found = any(contains(sentence, entry) and not re.search(
                    r"\b(never|do not|don't|avoid|nunca|jamás|no compartas|no envíes|no envies)\b",
                    sentence, re.I) for sentence in sentences)
            if found:
                entries.append(entry)
        if entries:
            points = min(group["cap"], len(entries) * group["points"])
            add(group["name"], points, "Wordlist matches: " + "; ".join(entries))
            factors[-1]["entries"] = entries
            factors[-1]["origin"] = "wordlist"
            factors[-1]["scope"] = group["scope"]
    if not enough_text and not factors:
        return unassessed("Too little readable text or wordlist evidence was available for a meaningful assessment.")
    counts = Counter(re.sub(r"\s+", " ", s.lower()) for s in sentences if len(s) >= 35)
    repeated = next((s for s, count in counts.items() if count >= 3), None)
    if repeated:
        add("Repeated language", 10, repeated)
    words = re.findall(r"\b[^\W\d_]+\b", text)
    capitals = sum(len(w) > 2 and w.isupper() for w in words)
    if re.search(r"[!?]{3,}", text) or (len(words) >= 20 and capitals / len(words) > 0.35):
        add("Unusual formatting", 5, "Repeated punctuation or a high proportion of capitalized words.")
    score = min(100, sum(f["points"] for f in factors))
    level = "High" if score >= 50 else "Moderate" if score >= 20 else "Low"
    explanation = ("Signals detected: " + "; ".join(f["name"].lower() for f in factors) + "."
                   if factors else "No configured warning signals were found in the readable page text. This does not establish that the page is safe.")
    if not enough_text:
        explanation += " Limited readable text; assessment relies on wordlist evidence."
    action = {"High": "Prioritize human review and verify the claimed identity and requested action.",
              "Moderate": "Review the request and verify it through an independent channel.",
              "Low": "No automatic escalation; consider source and context before acting."}[level]
    return {"version": VERSION, "score": score, "level": level, "flagged": score >= 50,
            "explanation": explanation, "action": action, "factors": factors, "caveat": CAVEAT,
            "wordlist_points": sum(f["points"] for f in factors if f.get("origin") == "wordlist"),
            "supplementary_points": sum(f["points"] for f in factors if f.get("origin") != "wordlist")}
