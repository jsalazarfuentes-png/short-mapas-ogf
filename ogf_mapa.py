#!/usr/bin/env python3
"""Descarga y une teselas reales del mapa de OpenGeofiction (estilo ogf-carto).
Uso: ogf_mapa.py SALIDA_DIR NOMBRE --zona OESTE SUR ESTE NORTE --z ZOOM
Crea NOMBRE.png y NOMBRE.json (zoom y origen en píxeles mundiales)."""
import argparse, json, math, os, time, urllib.request, io
from PIL import Image

TILE = "https://tile.opengeofiction.net/ogf-carto/{z}/{x}/{y}.png"
UA = {"User-Agent": "ogf-short-maker/1.0"}

def lonlat_px(lon, lat, z):
    n = 256 * 2 ** z
    x = (lon + 180) / 360 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("salida"); ap.add_argument("nombre")
    ap.add_argument("--zona", nargs=4, type=float, required=True)
    ap.add_argument("--z", type=int, required=True)
    a = ap.parse_args()
    w, s, e, n = a.zona; z = a.z
    x0, y0 = lonlat_px(w, n, z); x1, y1 = lonlat_px(e, s, z)
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    total = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
    if total > 900: raise SystemExit(f"Demasiadas teselas ({total}); baja el zoom o la zona")
    cache = os.path.join(a.salida, "cache"); os.makedirs(cache, exist_ok=True)
    img = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), (170, 211, 223))
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            f = os.path.join(cache, f"{z}_{tx}_{ty}.png")
            if not os.path.exists(f):
                for intento in range(4):
                    try:
                        req = urllib.request.Request(TILE.format(z=z, x=tx, y=ty), headers=UA)
                        data = urllib.request.urlopen(req, timeout=30).read()
                        Image.open(io.BytesIO(data)).verify()
                        open(f, "wb").write(data); break
                    except Exception as ex:
                        time.sleep(1.5 * (intento + 1))
                else:
                    print("falta tesela", z, tx, ty); continue
                time.sleep(0.05)
            img.paste(Image.open(f).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    img.save(os.path.join(a.salida, a.nombre + ".png"))
    json.dump({"z": z, "ox": tx0 * 256, "oy": ty0 * 256, "w": img.width, "h": img.height},
              open(os.path.join(a.salida, a.nombre + ".json"), "w"))
    print(f"{a.nombre}: {total} teselas, {img.width}x{img.height}")

if __name__ == "__main__":
    main()
