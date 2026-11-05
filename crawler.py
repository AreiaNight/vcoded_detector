import argparse
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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan one URL or a file of URLs.")
    parser.add_argument("target", nargs="?", help="URL supplied by the dashboard")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", help="A single URL to scan")
    source.add_argument("--urls-file", type=Path, help="File with one URL per line")
    args = parser.parse_args(argv)
    if args.target and (args.url or args.urls_file):
        parser.error("Use a positional URL, --url, or --urls-file, not a combination")
    if not (args.target or args.url or args.urls_file):
        parser.error("Provide a URL or --urls-file")

    batch = args.urls_file is not None
    try:
        urls = (args.urls_file.read_text(encoding="utf-8").splitlines()
                if batch else [args.target or args.url])
        urls = list(dict.fromkeys(url.strip() for url in urls if url.strip()))
    except (OSError, UnicodeError) as error:
        print(f"Could not read URL file: {error}", file=sys.stderr)
        return 1

    records = []
    failed = False
    for url in urls:
        try:
            data = analyze(url)
        except requests.Timeout:
            error = "The page took too long to respond"
        except requests.exceptions.SSLError as exc:
            error = f"TLS/SSL error: {exc}"
        except requests.ConnectionError as exc:
            error = "Could not connect to the page"
            if str(exc):
                error += f": {exc}"
        except (requests.RequestException, OSError, UnicodeError) as exc:
            error = f"Could not analyze the page: {exc}"
        else:
            records.append({"url": url, **data} if batch else data)
            if batch:
                print(
                    f"Scanned {url}: HTTP {data['status']}; "
                    f"total matches: {data['total']}",
                    file=sys.stderr, end="\n\n",
                )
            continue
        failed = True
        print(f"Failed to scan {url}: {error}", file=sys.stderr, end="\n\n")
        if batch:
            records.append({"url": url, "error": error})

    # Preserve the dashboard's single-object JSON contract. Batch mode emits an array.
    if batch:
        blocks = [json.dumps(record, indent=2) for record in records]
        print("[\n" + ",\n\n".join(blocks) + "\n]" if blocks else "[]")
    elif records:
        print(json.dumps(records[0]))
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
