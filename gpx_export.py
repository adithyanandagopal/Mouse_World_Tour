"""Tiny GPX writer -- no extra dependency needed for such a simple format."""
from xml.sax.saxutils import escape

GPX_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<gpx version="1.1" creator="Mouse World Tour" '
    'xmlns="http://www.topografix.com/GPX/1/1">\n'
    "<trk><name>{name}</name><trkseg>\n"
)
GPX_FOOTER = "</trkseg></trk>\n</gpx>\n"


def write_gpx(path, waypoints, track_name="Mouse World Tour"):
    """waypoints: list of dicts with lat, lon, and optionally timestamp (ISO)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(GPX_HEADER.format(name=escape(track_name)))
        for wp in waypoints:
            lat = wp.get("lat")
            lon = wp.get("lon")
            ts = wp.get("timestamp")
            if lat is None or lon is None:
                continue
            if ts:
                f.write(f'<trkpt lat="{lat}" lon="{lon}"><time>{escape(str(ts))}</time></trkpt>\n')
            else:
                f.write(f'<trkpt lat="{lat}" lon="{lon}"></trkpt>\n')
        f.write(GPX_FOOTER)
