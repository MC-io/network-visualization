import sys

import requests


def fetch_ids(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return [item["id"] for item in payload["data"]]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fetch_ids.py <url>")
        sys.exit(1)

    ids = fetch_ids(sys.argv[1])
    print(ids)
    print(len(ids))
