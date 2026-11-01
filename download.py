import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests


def get_json(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def save_json(data, path):
    # Write to a temp file first so an interrupted run never leaves a half-written file
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def download(ids_url, stops_url, out_dir, workers=10):
    out_dir = Path(out_dir)
    stops_dir = out_dir / "stops"
    stops_dir.mkdir(parents=True, exist_ok=True)

    ids_payload = get_json(ids_url)
    save_json(ids_payload, out_dir / "ids.json")
    ids = [item["id"] for item in ids_payload["data"]]

    # Skip files already downloaded, so a failed run can be resumed
    pending = [item_id for item_id in ids if not (stops_dir / f"{item_id}.json").exists()]
    print(f"Got {len(ids)} ids, {len(pending)} left to download", file=sys.stderr)

    def download_one(item_id):
        save_json(get_json(f"{stops_url.rstrip('/')}/{item_id}"), stops_dir / f"{item_id}.json")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for i, _ in enumerate(executor.map(download_one, pending), 1):
            if i % 50 == 0 or i == len(pending):
                print(f"Downloaded {i}/{len(pending)}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download the ids and stops responses to a folder")
    parser.add_argument("ids_url", help="Endpoint returning the list of ids")
    parser.add_argument("stops_url", help="Base endpoint; each id is appended at the end")
    parser.add_argument("--out", default="data", help="Folder to save the responses in (default: data)")
    parser.add_argument("--workers", type=int, default=10, help="Parallel requests (default: 10)")
    args = parser.parse_args()

    download(args.ids_url, args.stops_url, args.out, args.workers)
