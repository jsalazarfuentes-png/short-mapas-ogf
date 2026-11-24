#!/usr/bin/env python3
"""Saca los datos de un país o región de OpenGeofiction SOLO del mapa (Nominatim y Overpass de OGF).
Uso: ogf_datos.py "Nombre" CARPETA_DATOS
Guarda contorno.json (GeoJSON), lugares.json, vecinos.json y datos.md (resumen para el guion)."""
import json, math, os, sys, urllib.parse, urllib.request

UA = {"User-Agent": "ogf-short-maker/1.0"}
NOM = "https://nominatim.opengeofiction.net"
OVP = "https://overpass.opengeofiction.net/api/interpreter"

def get(url, data=None):
    req = urllib.request.Request(url, data=data, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=180))

def overpass(q):
    return get(OVP, urllib.parse.urlencode({"data": q}).encode())

def area_km2(ring):
    a = 0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        a += x1 * y2 - x2 * y1
    lat = sum(c[1] for c in ring) / len(ring)
    return abs(a) / 2 * 111.32 ** 2 * math.cos(math.radians(lat))

def main():
    nombre, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    r = get(f"{NOM}/search?" + urllib.parse.urlencode({"q": nombre, "format": "json", "polygon_geojson": 1, "limit": 1}))
    if not r: raise SystemExit("No está en el mapa de OGF: " + nombre)
    r = r[0]; rid = r["osm_id"]
    json.dump(r["geojson"], open(f"{out}/contorno.json", "w"))
    rel = overpass(f'[out:json][timeout:90];rel({rid});out tags;')["elements"][0]["tags"]
    lug = overpass(f'[out:json][timeout:120];rel({rid});map_to_area->.a;node(area.a)[place~"city|town|village"];out;')["elements"]
    vec = overpass(f'[out:json][timeout:120];rel({rid});way(r);rel(bw)["boundary"="administrative"]["admin_level"="{rel.get("admin_level","2")}"];out tags;')["elements"]
    json.dump(lug, open(f"{out}/lugares.json", "w"), ensure_ascii=False)
    json.dump(vec, open(f"{out}/vecinos.json", "w"), ensure_ascii=False)
    g = r["geojson"]; polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    L = [f"# {nombre} (relación {rid}) — datos sacados del mapa de OGF", "", "## Etiquetas", ""]
    L += [f"- {k}: {v}" for k, v in sorted(rel.items())]
    L += ["", "## Trozos del territorio (índice, km², oeste-este, sur-norte)", ""]
    tot = 0
    for i, p in enumerate(polys):
        a = area_km2(p[0]); tot += a
        xs = [c[0] for c in p[0]]; ys = [c[1] for c in p[0]]
        L.append(f"- trozo {i}: {a:.0f} km², lon {min(xs):.3f}–{max(xs):.3f}, lat {min(ys):.3f}–{max(ys):.3f}")
    L += [f"- TOTAL: {tot:.0f} km²", "", "## Vecinos", ""]
    L += [f"- {e['tags'].get('name')} ({e['tags'].get('ogf:id','')})" for e in vec if e["id"] != rid]
    L += ["", "## Lugares (tipo, nombre, capital, población, lat, lon)", ""]
    for e in sorted(lug, key=lambda e: ({"city": 0, "town": 1}.get(e["tags"].get("place"), 2))):
        t = e["tags"]
        L.append(f"- {t.get('place')} | {t.get('name')} | capital={t.get('capital','')} | pob={t.get('population','')} | {e['lat']:.4f}, {e['lon']:.4f}")
    open(f"{out}/datos.md", "w").write("\n".join(L) + "\n")
    print("\n".join(L))

if __name__ == "__main__":
    main()
