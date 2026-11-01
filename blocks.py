import csv


def load_blocks(path):
    # X is longitude, Y is latitude, T_TOTAL is the block's population
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [
            {"id": row["MANZANA_ID"], "lat": float(row["Y"]), "lng": float(row["X"]), "population": int(row["T_TOTAL"])}
            for row in csv.DictReader(f)
        ]


def blocks_in_box(blocks, nw, se):
    """Keep only blocks inside the box with corners nw=(lat, lng) and se=(lat, lng)."""
    (north, west), (south, east) = nw, se
    if north <= south or west >= east:
        raise ValueError(f"Northwest corner {nw} must be north and west of southeast corner {se}")
    return [b for b in blocks if south <= b["lat"] <= north and west <= b["lng"] <= east]
