import argparse
import json
import math
import sys
from pathlib import Path

EARTH_RADIUS_M = 6_371_000
METERS_PER_DEGREE = 2 * math.pi * EARTH_RADIUS_M / 360


def haversine_m(lat1, lng1, lat2, lng2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_all_stops(data_dir):
    """Yield every stop from the responses saved by download.py, in the order of ids.json."""
    data_dir = Path(data_dir)
    ids = [item["id"] for item in load_json(data_dir / "ids.json")["data"]]
    for item_id in ids:
        yield from load_json(data_dir / "stops" / f"{item_id}.json")["data"]["stops"]


class PointGrid:
    """Grid of cells ~threshold_m wide, so only nearby cells need to be checked."""

    def __init__(self, threshold_m):
        self.cell_deg = threshold_m / METERS_PER_DEGREE
        self.cells = {}

    def _cell(self, lat, lng):
        return math.floor(lat / self.cell_deg), math.floor(lng / self.cell_deg)

    def add(self, point_id, lat, lng):
        self.cells.setdefault(self._cell(lat, lng), set()).add(point_id)

    def remove(self, point_id, lat, lng):
        self.cells[self._cell(lat, lng)].discard(point_id)

    def candidates(self, lat, lng):
        row, col = self._cell(lat, lng)
        # Longitude degrees shrink away from the equator, so search more columns
        lng_reach = math.ceil(1 / max(math.cos(math.radians(lat)), 1e-6))
        for r in range(row - 1, row + 2):
            for c in range(col - lng_reach, col + lng_reach + 1):
                yield from self.cells.get((r, c), ())


def centroid(stops):
    return (
        sum(stop["lat"] for stop in stops) / len(stops),
        sum(stop["lng"] for stop in stops) / len(stops),
    )


def cluster_stops(stops, threshold_m=20):
    """Group stops so every stop is within threshold_m of its group's centroid.

    Returns a list of {"centroid": (lat, lng), "stops": [original stop dicts]}.
    """
    clusters = []
    grid = PointGrid(threshold_m)

    def nearby(lat, lng, exclude=None):
        # Ids of clusters whose centroid is within the threshold, nearest first
        found = []
        for i in grid.candidates(lat, lng):
            distance = haversine_m(lat, lng, *clusters[i]["centroid"])
            if i != exclude and distance <= threshold_m:
                found.append((distance, i))
        return [i for _, i in sorted(found)]

    def try_add(i, new_stops):
        # Add stops to cluster i only if every stop stays within the threshold of the new centroid
        members = clusters[i]["stops"] + new_stops
        new_centroid = centroid(members)
        if any(haversine_m(s["lat"], s["lng"], *new_centroid) > threshold_m for s in members):
            return False
        grid.remove(i, *clusters[i]["centroid"])
        clusters[i] = {"centroid": new_centroid, "stops": members}
        grid.add(i, *new_centroid)
        return True

    for stop in stops:
        if not any(try_add(i, [stop]) for i in nearby(stop["lat"], stop["lng"])):
            clusters.append({"centroid": (stop["lat"], stop["lng"]), "stops": [stop]})
            grid.add(len(clusters) - 1, stop["lat"], stop["lng"])

    # Centroids move as stops are added, so merge clusters that drifted within the threshold
    merged = True
    while merged:
        merged = False
        for i, cluster in enumerate(clusters):
            if cluster is None:
                continue
            for j in nearby(*cluster["centroid"], exclude=i):
                other = clusters[j]
                if try_add(i, other["stops"]):
                    grid.remove(j, *other["centroid"])
                    clusters[j] = None
                    merged = True
                    break

    return [cluster for cluster in clusters if cluster is not None]


def mark_coverage(blocks, coordinates, coverage_m=200):
    """Set block["covered"] to whether any stop is within coverage_m of the block."""
    grid = PointGrid(coverage_m)
    for i, (lat, lng) in enumerate(coordinates):
        grid.add(i, lat, lng)
    for block in blocks:
        block["covered"] = any(
            haversine_m(block["lat"], block["lng"], *coordinates[i]) <= coverage_m
            for i in grid.candidates(block["lat"], block["lng"])
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data", help="Folder with the responses saved by download.py (default: data)")
    parser.add_argument("--threshold", type=float, default=20, help="Merge distance in meters (default: 20)")
    parser.add_argument("--no-merge", action="store_true", help="Skip merging nearby stops; only drop exact duplicates")
    parser.add_argument("--map", metavar="FILE", help="Save the points on an OpenStreetMap HTML map, e.g. stops.html")
    parser.add_argument("--blocks", metavar="CSV", help="CSV of block centroids (X=lng, Y=lat, MANZANA_ID) to also draw on the map")
    parser.add_argument("--coverage", type=float, default=200, help="Blocks farther than this from every stop are marked uncovered, in meters (default: 200)")
    parser.add_argument(
        "--metro-box",
        type=float,
        nargs=4,
        metavar=("NW_LAT", "NW_LNG", "SE_LAT", "SE_LNG"),
        help="Only keep blocks inside this box (northwest and southeast corners)",
    )
    args = parser.parse_args()

    stops = load_all_stops(args.data)
    if args.no_merge:
        coordinates = list(dict.fromkeys((stop["lat"], stop["lng"]) for stop in stops))
    else:
        clusters = cluster_stops(stops, args.threshold)
        coordinates = [cluster["centroid"] for cluster in clusters]
    print(coordinates)
    print(len(coordinates))

    blocks = None
    metro_box = (tuple(args.metro_box[:2]), tuple(args.metro_box[2:])) if args.metro_box else None
    if args.blocks:
        from blocks import blocks_in_box, load_blocks

        blocks = load_blocks(args.blocks)
        if metro_box:
            all_count = len(blocks)
            blocks = blocks_in_box(blocks, *metro_box)
            print(f"Metro box: kept {len(blocks):,} of {all_count:,} blocks", file=sys.stderr)
        mark_coverage(blocks, coordinates, args.coverage)
        uncovered = [block for block in blocks if not block["covered"]]
        total_population = sum(block["population"] for block in blocks)
        uncovered_population = sum(block["population"] for block in uncovered)
        print(f"\nBlocks farther than {args.coverage:g} m from every stop:", file=sys.stderr)
        print(f"  Blocks:     {len(uncovered):,} of {len(blocks):,} ({len(uncovered) / len(blocks):.1%})", file=sys.stderr)
        print(
            f"  Population: {uncovered_population:,} of {total_population:,} ({uncovered_population / total_population:.1%})",
            file=sys.stderr,
        )

    if args.map:
        from map_stops import draw_map

        draw_map(coordinates, args.map, blocks, args.coverage, metro_box)
        print(f"Map saved to {args.map}", file=sys.stderr)
