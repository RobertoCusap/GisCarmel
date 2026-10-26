"""Build the atlas's geometry and base layers with Python and Folium.

The browser bridge handles interaction with the species catalogue. All source
coordinates remain untouched; observations sharing a location share a popup.
"""

from collections import defaultdict
from html import escape

import folium
from branca.element import MacroElement, Template


class AtlasBridge(MacroElement):
    """Expose Folium's generated objects to our small local browser bridge."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        window.ATLAS_MAP_CONFIG = {
            map: {{ this.map_name }},
            groups: {
                {% for species_id, group_name in this.groups.items() %}
                {{ species_id|tojson }}: {{ group_name }},
                {% endfor %}
            },
            basemaps: {street: {{ this.street_name }}, satellite: {{ this.satellite_name }}},
            markers: [
                {% for item in this.markers %}
                {layer: {{ item.name }}, locationId: {{ item.location_id|tojson }}, speciesId: {{ item.species_id|tojson }}},
                {% endfor %}
            ],
            locations: {{ this.locations|tojson }},
            species: {{ this.species|tojson }},
            bounds: {{ this.bounds|tojson }}
        };
        var bridgeScript = document.createElement('script');
        bridgeScript.src = '/static/map.js';
        document.body.appendChild(bridgeScript);
        {% endmacro %}
        """
    )


def build_map(dataset: dict) -> str:
    """Return a complete local-asset Folium page for the atlas iframe."""
    bounds = dataset["bounds"]
    center = [
        (bounds[0][0] + bounds[1][0]) / 2,
        (bounds[0][1] + bounds[1][1]) / 2,
    ]
    atlas_map = folium.Map(
        location=center,
        tiles=None,
        zoom_start=14,
        min_zoom=3,
        max_zoom=21,
        zoom_control=False,
        control_scale=True,
        prefer_canvas=False,
        attribution_control=True,
        fade_animation=False,
    )
    # Folium's default Bootstrap/jQuery dependencies aren't needed by this map.
    # Vendoring Leaflet also keeps the controls and dots usable without internet.
    atlas_map.default_js = [("leaflet", "/static/vendor/leaflet/leaflet.js")]
    atlas_map.default_css = [
        ("leaflet_css", "/static/vendor/leaflet/leaflet.css"),
        ("atlas_css", "/static/map.css"),
    ]
    street = folium.TileLayer(
        tiles="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
        name="Street",
        max_zoom=21,
        max_native_zoom=19,
    ).add_to(atlas_map)
    satellite = folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr='Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
        name="Satellite",
        max_zoom=21,
        # Esri's zoom-19 tiles return a no-data image in this survey area.
        # All source locations have zoom-18 imagery. Reuse those tiles when
        # zooming closer, rather than displaying the provider's placeholder.
        max_native_zoom=18,
        show=False,
    ).add_to(atlas_map)

    species_by_id = {item["id"]: item for item in dataset["species"]}
    groups = {
        species_id: folium.FeatureGroup(name=item["name"], control=False).add_to(atlas_map)
        for species_id, item in species_by_id.items()
    }
    by_coordinate = defaultdict(list)
    for observation in dataset["observations"]:
        by_coordinate[(observation["latitude"], observation["longitude"])].append(observation)

    locations = {}
    markers = []
    for index, (coordinate, observations) in enumerate(by_coordinate.items()):
        location_id = f"location-{index}"
        locations[location_id] = observations
        location_species = dict.fromkeys(item["species_id"] for item in observations)
        for species_id in location_species:
            species = species_by_id[species_id]
            marker = folium.CircleMarker(
                location=list(coordinate),
                radius=6,
                color="#ffffff",
                weight=1.7,
                fill=True,
                fill_color=species["color"],
                fill_opacity=0.95,
                opacity=1,
                bubbling_mouse_events=False,
                tooltip=folium.Tooltip(escape(species["name"]), sticky=False, direction="top"),
            ).add_to(groups[species_id])
            markers.append({"name": marker.get_name(), "location_id": location_id, "species_id": species_id})

    atlas_map.fit_bounds(bounds, padding=(36, 36), max_zoom=17)
    bridge = AtlasBridge()
    bridge.map_name = atlas_map.get_name()
    bridge.street_name = street.get_name()
    bridge.satellite_name = satellite.get_name()
    bridge.groups = {key: group.get_name() for key, group in groups.items()}
    bridge.markers = markers
    bridge.locations = locations
    bridge.species = species_by_id
    bridge.bounds = bounds
    bridge.add_to(atlas_map)
    return atlas_map.get_root().render()
