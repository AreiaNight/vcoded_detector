import sys
import json
from pathlib import Path
import requests

WORDLIST = Path(__file__).with_name("wordlist.txt")


def load_signals():
    # dict.fromkeys drops repeated lines, so no signal is counted twice.
    lines = WORDLIST.read_text(encoding="utf-8").splitlines()
    return list(dict.fromkeys(line.strip().lower() for line in lines if line.strip()))


def analyze(url):
    # Compose the view-source link so It doesn't have to open the main webpage
    view_source = "view-source:" + url

    response = requests.get(url, timeout=10)
    # Without a declared charset, requests assumes Latin-1 and breaks emoji signals.
    if "charset" not in response.headers.get("content-type", "").lower():
        response.encoding = "utf-8"
    html = response.text.lower()

    results = []
    for signal in load_signals():
        count = html.count(signal)
        if count > 0:
            results.append({"word": signal, "count": count})
    results.sort(key=lambda item: item["count"], reverse=True)

    return {
        "status": response.status_code,
        "source": view_source,
        "total": sum(item["count"] for item in results),
        "results": results,
    }


if __name__ == "__main__":
    # sys.argv[1] is the URL sent by Go. The JSON goes to stdout, errors to stderr.
    try:
        data = analyze(sys.argv[1])
    except requests.Timeout:
        sys.exit("The page took too long to respond")
    except requests.ConnectionError:
        sys.exit("Could not connect to the page")
    except requests.RequestException as error:
        sys.exit(f"Could not fetch the page: {error}")
    print(json.dumps(data))
