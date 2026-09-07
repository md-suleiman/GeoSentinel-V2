import osmium
import json
import os


PBF_PATH = "data/roads/north-eastern-zone-260905.osm.pbf"
ROADS_OUTPUT = "data/roads/roads.json"
SETTLEMENTS_OUTPUT = "data/settlements/settlements.json"


ROAD_TYPES = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
}


SETTLEMENT_TYPES = {
    "city",
    "town",
    "village",
    "hamlet",
}


roads = []
settlements = []


class GeoSentinelHandler(osmium.SimpleHandler):

    def __init__(self):
        super().__init__()

    # --------------------------------
    # Extract roads
    # --------------------------------

    def way(self, w):

        highway = w.tags.get("highway")

        if highway not in ROAD_TYPES:
            return

        if not w.nodes:
            return

        coordinates = []

        for node in w.nodes:

            if node.location.valid():

                coordinates.append([
                    node.lon,
                    node.lat
                ])

        if len(coordinates) < 2:
            return

        name = w.tags.get("name")
        ref = w.tags.get("ref")

        roads.append({
            "type": highway,
            "name": name if name else None,
            "ref": ref if ref else None,
            "coordinates": coordinates
        })


    # --------------------------------
    # Extract settlements
    # --------------------------------

    def node(self, n):

        place = n.tags.get("place")

        if place not in SETTLEMENT_TYPES:
            return

        if not n.location.valid():
            return

        settlements.append({
            "type": place,
            "name": n.tags.get("name"),
            "latitude": n.lat,
            "longitude": n.lon
        })


print()
print("GeoSentinel OSM extraction starting...")
print()
print(f"Input: {PBF_PATH}")
print()


if not os.path.exists(PBF_PATH):

    raise FileNotFoundError(
        f"Could not find PBF file: {PBF_PATH}"
    )


handler = GeoSentinelHandler()

handler.apply_file(
    PBF_PATH,
    locations=True
)


print(f"Roads extracted: {len(roads)}")
print(f"Settlements extracted: {len(settlements)}")
print()


# --------------------------------
# Save roads
# --------------------------------

os.makedirs(
    os.path.dirname(ROADS_OUTPUT),
    exist_ok=True
)

with open(
    ROADS_OUTPUT,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        roads,
        file,
        ensure_ascii=False
    )


# --------------------------------
# Save settlements
# --------------------------------

os.makedirs(
    os.path.dirname(SETTLEMENTS_OUTPUT),
    exist_ok=True
)

with open(
    SETTLEMENTS_OUTPUT,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        settlements,
        file,
        ensure_ascii=False
    )


print("Extraction complete.")
print()
print(f"Road data: {ROADS_OUTPUT}")
print(f"Settlement data: {SETTLEMENTS_OUTPUT}")
print()