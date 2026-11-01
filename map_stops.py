import folium


def _add_points(layer, points, color, radius):
    for lat, lng, tooltip in points:
        folium.CircleMarker(
            location=(lat, lng),
            radius=radius,
            weight=0,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            tooltip=tooltip,
        ).add_to(layer)


def draw_map(coordinates, path, blocks=None, coverage_m=200, metro_box=None):
    center = (
        sum(lat for lat, _ in coordinates) / len(coordinates),
        sum(lng for _, lng in coordinates) / len(coordinates),
    )
    # OSM's tile servers block pages opened via file://, so open the map through
    # a local server instead: python -m http.server 8000 -> http://localhost:8000/<file>
    # prefer_canvas draws markers on a canvas instead of as DOM elements, which keeps ~20k points fast
    m = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap", prefer_canvas=True)

    if metro_box:
        folium.Rectangle(bounds=list(metro_box), color="black", weight=2, fill=False, tooltip="Metro area").add_to(m)

    # Blocks go first so stops are drawn on top of them
    if blocks:
        for covered, color, label in [
            (True, "blue", f"Blocks within {coverage_m:g} m of a stop (blue)"),
            (False, "orange", f"Blocks farther than {coverage_m:g} m from every stop (orange)"),
        ]:
            layer = folium.FeatureGroup(name=label).add_to(m)
            points = [(b["lat"], b["lng"], f"Block {b['id']}, population {b['population']}") for b in blocks if b["covered"] == covered]
            _add_points(layer, points, color, radius=2)

    stop_layer = folium.FeatureGroup(name="Stops (red)").add_to(m)
    _add_points(stop_layer, [(lat, lng, f"{lat}, {lng}") for lat, lng in coordinates], "red", radius=3)

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(path)
