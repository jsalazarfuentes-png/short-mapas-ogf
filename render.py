#!/usr/bin/env python3
"""Renderiza un short vertical (1080x1920) de geografía de OpenGeofiction a partir de un guion JSON.
Voz: la voz de Apple del Mac (orden `say`). Mapa: teselas reales de OGF ya descargadas con ogf_mapa.py.

Uso:
  render.py guion.json voz      -> genera la voz por frases y mide tiempos (voz/*.wav, tiempos.json)
  render.py guion.json fotos    -> hoja de fotogramas para revisar (fotos/hoja.jpg)
  render.py guion.json video    -> vídeo final (salida en la carpeta del guion)
"""
import json, math, os, re, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
SAFE_TOP, SAFE_BOTTOM, SAFE_RIGHT = 170, 1480, 150
AMARILLO = (255, 214, 64)
ROJO = (232, 52, 52)
TINTA = (14, 22, 36)
BLANCO = (255, 255, 255)

F_TITULO = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
F_TEXTO = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = "ffmpeg"

# ---------------------------------------------------------------- utilidades
_cmaps = {}
def _cmap(path):
    if path not in _cmaps:
        try:
            from fontTools.ttLib import TTFont
            _cmaps[path] = set(TTFont(path).getBestCmap().keys())
        except Exception:
            _cmaps[path] = None
    return _cmaps[path]

_fonts = {}
def fuente(texto, size, gruesa=True):
    """Arial Black si tiene todas las letras; si no, Arial Bold (tiene ĳ, ð, ǎ, ř, cirílico...)."""
    path = F_TITULO if gruesa else F_TEXTO
    cm = _cmap(path)
    if cm is not None and any(ord(c) not in cm for c in texto if not c.isspace()):
        path = F_TEXTO
    k = (path, size)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(path, size)
    return _fonts[k]

def ease(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)

def ease_out_back(t):
    t = min(max(t, 0.0), 1.0)
    c1 = 1.4; c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

def merc(lon, lat):
    """Coordenadas mundiales a zoom 0 (0..256)."""
    s = math.sin(math.radians(lat))
    return (lon + 180) / 360 * 256, (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * 256

def wav_info(path):
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()

def leer_wav(path, sr=44100):
    with wave.open(path) as w:
        assert w.getframerate() == sr and w.getsampwidth() == 2
        d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if w.getnchannels() == 2:
            d = d.reshape(-1, 2).mean(axis=1)
    return d

def escribir_wav(path, data, sr=44100):
    d = np.clip(data, -1, 1)
    with wave.open(path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((d * 32767).astype(np.int16).tobytes())

# ---------------------------------------------------------------- guion
class Guion:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.dir = os.path.dirname(self.path)
        self.g = json.load(open(path))
        self.escenas = self.g["escenas"]
        self.ruta = lambda p: p if os.path.isabs(p) else os.path.join(self.dir, p)

    # ---------------- voz
    def voz(self):
        vd = self.ruta("voz"); os.makedirs(vd, exist_ok=True)
        voz = self.g.get("voz", "Mónica"); vel = str(self.g.get("velocidad", 180))
        for i, e in enumerate(self.escenas):
            dice = e.get("dice", e["texto"])
            aiff, wav = f"{vd}/{i:02d}.aiff", f"{vd}/{i:02d}.wav"
            subprocess.run(["say", "-v", voz, "-r", vel, "-o", aiff, dice], check=True)
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", aiff, "-ac", "1", "-ar", "44100",
                            "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                                   "silenceremove=start_periods=1:start_threshold=-50dB,areverse", wav], check=True)
            os.remove(aiff)
        self.tiempos(recalcular=True)
        print(json.dumps(self.t, indent=1))

    def tiempos(self, recalcular=False):
        tp = self.ruta("tiempos.json")
        if not recalcular and os.path.exists(tp):
            self.t = json.load(open(tp)); return self.t
        t = 0.35; out = []
        pausa = self.g.get("pausa", 0.32)
        for i, e in enumerate(self.escenas):
            d = wav_info(self.ruta(f"voz/{i:02d}.wav"))
            out.append({"ini": round(t, 3), "voz": round(d, 3), "fin": round(t + d + e.get("pausa", pausa), 3)})
            t = out[-1]["fin"]
        out[-1]["fin"] = round(out[-1]["fin"] + self.g.get("cola", 1.0), 3)
        json.dump(out, open(tp, "w"), indent=1)
        self.t = out
        return out

    @property
    def duracion(self):
        return self.t[-1]["fin"]

# ---------------------------------------------------------------- mapa
class Mapa:
    def __init__(self, guion):
        self.niveles = []
        for m in guion.g["mapas"]:
            meta = json.load(open(guion.ruta(m) + ".json"))
            img = Image.open(guion.ruta(m) + ".png").convert("RGB")
            self.niveles.append((meta["z"], meta, img))
        self.niveles.sort(key=lambda x: x[0])
        self.fondo = tuple(guion.g.get("color_fondo", [242, 239, 233]))

    def _cubre(self, nivel, cx, cy, z):
        L, meta, img = nivel
        k = 2 ** L
        s = 2 ** (z - L)
        hw, hh = W / 2 / s, H / 2 / s
        x, y = cx * k - meta["ox"], cy * k - meta["oy"]
        return x - hw >= 0 and y - hh >= 0 and x + hw <= meta["w"] and y + hh <= meta["h"]

    def _pinta(self, nivel, cx, cy, z):
        L, meta, img = nivel
        k = 2 ** L
        s = 2 ** (z - L)          # píxeles de salida por píxel del nivel
        x, y = cx * k - meta["ox"], cy * k - meta["oy"]
        a = 1 / s
        data = (a, 0, x - W / 2 * a, 0, a, y - H / 2 * a)
        src = img
        if s < 0.7:  # reducir mucho: prefiltrar para evitar dientes de sierra
            f = max(1, int(0.75 / s))
            if f > 1:
                key = ("red", L, f)
                if not hasattr(self, "_cache"): self._cache = {}
                if key not in self._cache:
                    self._cache[key] = img.resize((img.width // f, img.height // f), Image.LANCZOS)
                src = self._cache[key]
                data = (a / f, 0, (x - W / 2 * a) / f, 0, a / f, (y - H / 2 * a) / f)
        return src.transform((W, H), Image.AFFINE, data, resample=Image.BILINEAR, fillcolor=self.fondo)

    def frame(self, cx, cy, z):
        cub = [n for n in self.niveles if self._cubre(n, cx, cy, z)]
        if not cub:
            cub = [self.niveles[0]]
        # nivel principal: el más pequeño con L >= z-0.5 que cubre; si no, el mayor que cubre
        mayores = [n for n in cub if n[0] >= z - 0.5]
        a = mayores[0] if mayores else cub[-1]
        menores = [n for n in cub if n[0] < a[0]]
        img = self._pinta(a, cx, cy, z)
        if menores and mayores:
            b = menores[-1]
            t = (z - (a[0] - 0.5)) / 0.45
            if t < 1:
                img = Image.blend(self._pinta(b, cx, cy, z), img, ease(t))
        return img

# ---------------------------------------------------------------- dibujo de piezas
def caja_redonda(d, box, r, fill):
    d.rounded_rectangle(box, r, fill=fill)

def texto_centrado(d, x, y, txt, f, fill, stroke=0, sfill=TINTA):
    bb = d.textbbox((0, 0), txt, font=f, stroke_width=stroke)
    d.text((x - (bb[2] + bb[0]) / 2, y - (bb[3] + bb[1]) / 2), txt, font=f, fill=fill,
           stroke_width=stroke, stroke_fill=sfill)

def envolver(d, txt, f, ancho):
    palabras, lineas, act = txt.split(), [], ""
    for p in palabras:
        prueba = (act + " " + p).strip()
        if d.textlength(prueba, font=f) <= ancho or not act:
            act = prueba
        else:
            lineas.append(act); act = p
    if act: lineas.append(act)
    return lineas

_tarjetas = {}
def tarjeta_img(texto, sub, grande=False, acento=AMARILLO):
    k = (texto, sub, grande, acento)
    if k in _tarjetas: return _tarjetas[k]
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    size = 118 if grande else 74
    ft = fuente(texto, size)
    while tmp.textlength(texto, font=ft) > 820 and size > 40:
        size -= 4; ft = fuente(texto, size)
    lineas = envolver(tmp, texto, ft, 820)
    fs = fuente(sub or "", 42, gruesa=False)
    sublineas = envolver(tmp, sub, fs, 800) if sub else []
    lh = int(size * 1.12); sh = 54
    alto = 70 + lh * len(lineas) + (24 + sh * len(sublineas) if sublineas else 0)
    ancho = 880
    im = Image.new("RGBA", (ancho + 40, alto + 40), (0, 0, 0, 0))
    sombra = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((20, 26, ancho + 20, alto + 26), 34, fill=(0, 0, 0, 120))
    sombra = sombra.filter(ImageFilter.GaussianBlur(10))
    im.alpha_composite(sombra)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, 20, ancho + 20, alto + 20), 34, fill=TINTA + (238,))
    d.rounded_rectangle((20, 20, 36, alto + 20), 8, fill=acento + (255,))
    y = 20 + 35 + lh / 2
    for ln in lineas:
        texto_centrado(d, 20 + ancho / 2 + 8, y, ln, fuente(ln, size), acento if grande else BLANCO)
        y += lh
    y += 24 - lh / 2 + sh / 2 if sublineas else 0
    for ln in sublineas:
        texto_centrado(d, 20 + ancho / 2 + 8, y, ln, fs, (205, 214, 228))
        y += sh
    _tarjetas[k] = im
    return im

def comentario_img(texto, etiqueta):
    """Burbuja blanca de comentario (estilo «respondiendo a un comentario»)."""
    k = ("com", texto, etiqueta)
    if k in _tarjetas: return _tarjetas[k]
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    ancho = 840; size = 50
    ft = fuente(texto, size)
    lineas = envolver(tmp, texto, ft, ancho - 150)
    while len(lineas) > 3 and size > 32:
        size -= 4; ft = fuente(texto, size); lineas = envolver(tmp, texto, ft, ancho - 150)
    fe = fuente(etiqueta, 34, gruesa=False)
    lh = int(size * 1.18)
    alto = 40 + 44 + 14 + lh * len(lineas) + 36
    im = Image.new("RGBA", (ancho + 40, alto + 70), (0, 0, 0, 0))
    sombra = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((20, 26, ancho + 20, alto + 26), 36, fill=(0, 0, 0, 110))
    im.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, 20, ancho + 20, alto + 20), 36, fill=(255, 255, 255, 250))
    d.polygon([(90, alto + 18), (150, alto + 18), (96, alto + 62)], fill=(255, 255, 255, 250))   # piquito
    d.ellipse((50, 56, 130, 136), fill=(214, 218, 226))
    d.ellipse((76, 70, 104, 98), fill=(160, 166, 178)); d.pieslice((60, 96, 120, 156), 180, 360, fill=(160, 166, 178))
    d.text((152, 60), etiqueta, font=fe, fill=(110, 116, 128), anchor="la")
    y = 60 + 44 + 14
    for ln in lineas:
        d.text((152, y), ln, font=fuente(ln, size), fill=(20, 22, 28), anchor="la"); y += lh
    _tarjetas[k] = im
    return im

def pegar_centrado(base, im, cx, cy, escala=1.0, alpha=1.0):
    if escala != 1.0:
        im = im.resize((max(1, int(im.width * escala)), max(1, int(im.height * escala))), Image.BILINEAR)
    if alpha < 1.0:
        im = im.copy(); a = im.getchannel("A").point(lambda v: int(v * alpha)); im.putalpha(a)
    base.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))

# ---------------------------------------------------------------- renderizador
class Render:
    def __init__(self, guion):
        self.G = guion
        self.g = guion.g
        guion.tiempos()
        self.mapa = Mapa(guion)
        geo = json.load(open(guion.ruta(self.g["contorno"])))
        polys = geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]]
        self.trozos = []
        for p in polys:
            anillos = []
            for ring in p:
                anillos.append(np.array([merc(x, y) for x, y in ring]))
            self.trozos.append(anillos)
        self.camaras = self._camaras()
        self.vineta = self._vineta()
        self.subs = self._subtitulos()

    # cámara: transición suave al objetivo de cada escena y luego deriva lenta (nunca se para)
    def _camaras(self):
        cams = []
        prev = None
        for i, e in enumerate(self.G.escenas):
            c = e["camara"]; x, y = merc(c["lon"], c["lat"])
            cams.append({"x": x, "y": y, "z": c["z"], "mov": c.get("mov", 1.3 if i else 0.0),
                         "deriva": c.get("deriva", 0.14), "dx": c.get("dx", 0), "dy": c.get("dy", 0),
                         "arco": c.get("arco", 0), "vuelo": c.get("vuelo")})
        return cams

    def camara(self, t):
        T = self.G.t
        estado = None
        for i, c in enumerate(self.camaras):
            ini, fin = T[i]["ini"] if i else 0.0, T[i]["fin"]
            if i == len(T) - 1: fin = self.G.duracion
            if estado is None:
                estado = (c["x"], c["y"], c["z"] - c["deriva"] * 0.0)
            # posición de partida = estado al final de la escena anterior
            x0, y0, z0 = estado
            dur = max(0.01, fin - ini)
            def en(tt):
                u = (tt - ini)
                m = c["mov"]
                k = ease(u / m) if m > 0 else 1.0
                dz = c["deriva"] * ease(u / dur)
                # mover en un espacio común (zoom 0) interpolando en log del zoom
                if c.get("vuelo") and m > 0:
                    # «vuelo»: alejarse hasta el zoom c["vuelo"], viajar allí arriba y acercarse (sin cortes ni borrones)
                    kk = min(max(u / m, 0.0), 1.0); zm = c["vuelo"]
                    zz = z0 + (zm - z0) * ease(kk / 0.42) if kk < 0.42 else (zm if kk < 0.58 else zm + (c["z"] - zm) * ease((kk - 0.58) / 0.42))
                    kp = ease((kk - 0.3) / 0.4)
                    # sin cruzar el antimeridiano: el mapa del mundo no se repite a los lados
                    xx = x0 + (c["x"] - x0) * kp + c["dx"] * u / dur / 2 ** zz
                    yy = y0 + (c["y"] - y0) * kp + c["dy"] * u / dur / 2 ** zz
                    return xx, yy, zz + dz
                zz = z0 + (c["z"] - z0) * k - c["arco"] * 4 * k * (1 - k)  # «arco»: se aleja a mitad de un salto largo
                xx = x0 + (c["x"] - x0) * k + c["dx"] * u / dur / 2 ** zz * 256 / 256
                yy = y0 + (c["y"] - y0) * k + c["dy"] * u / dur / 2 ** zz * 256 / 256
                return xx, yy, zz + dz
            if t < fin or i == len(self.camaras) - 1:
                return en(t)
            estado = en(fin)
        return estado

    def _vineta(self):
        yy, xx = np.mgrid[0:H, 0:W]
        d = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.72)) ** 2)
        a = (np.clip((d - 0.55) / 0.6, 0, 1) ** 1.6 * 150).astype(np.uint8)
        im = Image.new("RGBA", (W, H), (10, 14, 22, 0)); im.putalpha(Image.fromarray(a))
        # franja superior e inferior un poco más oscura para que se lean los textos
        g = np.zeros((H, 1), np.float32)
        g[:420, 0] = np.linspace(110, 0, 420)
        g[H - 640:, 0] = np.linspace(0, 150, 640)
        band = Image.new("RGBA", (W, H), (8, 12, 20, 0))
        band.putalpha(Image.fromarray(np.repeat(g, W, axis=1).astype(np.uint8)))
        im.alpha_composite(band)
        return im

    def _subtitulos(self):
        subs = []
        for i, e in enumerate(self.G.escenas):
            T = self.G.t[i]
            palabras = e["texto"].split()
            trozos, act = [], []
            for p in palabras:
                act.append(p)
                if len(" ".join(act)) >= 13 or p[-1] in ".,:;?!" or len(act) >= 3:
                    trozos.append(" ".join(act)); act = []
            if act: trozos.append(" ".join(act))
            peso = [len(x) + 3 + (6 if x[-1] in ".,:;?!" else 0) for x in trozos]
            tot = sum(peso); t = T["ini"]
            for x, p in zip(trozos, peso):
                d = T["voz"] * p / tot
                subs.append((t, t + d, x)); t += d
        return subs

    def geo_px(self, lon, lat, cam):
        cx, cy, z = cam; s = 2 ** z
        x, y = merc(lon, lat)
        return (x - cx) * s + W / 2, (y - cy) * s + H / 2

    def _contorno(self, base, cam, trozos, prog=1.0, color=ROJO, relleno=70, grosor=7, pulso=0.0):
        cx, cy, z = cam; s = 2 ** z
        capa = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(capa)
        lineas = []
        for ti in trozos:
            for ri, ring in enumerate(self.trozos[ti]):
                pts = (ring - [cx, cy]) * s + [W / 2, H / 2]
                if pts[:, 0].max() < -50 or pts[:, 0].min() > W + 50 or pts[:, 1].max() < -50 or pts[:, 1].min() > H + 50:
                    continue
                # simplificar puntos muy juntos
                if len(pts) > 400:
                    paso = max(1, int(len(pts) / max(200, min(len(pts), (pts.max(0) - pts.min(0)).max()))))
                    pts = pts[::paso]
                pl = [tuple(p) for p in pts]
                if prog >= 1 and relleno:
                    d.polygon(pl, fill=color + ((0 if ri else relleno),))
                n = max(2, int(len(pl) * prog))
                lineas.append(pl[:n] if prog < 1 else pl + [pl[0]])
        g = grosor * (1 + 0.35 * pulso)
        for pl in lineas:
            d.line(pl, fill=(255, 255, 255, 230), width=int(g + 8), joint="curve")
        for pl in lineas:
            d.line(pl, fill=color + (255,), width=int(g), joint="curve")
        base.alpha_composite(capa)

    def _elemento(self, base, el, t, ini, fin, cam):
        desde = ini + el.get("desde", 0.15)
        hasta = ini + el["hasta"] if "hasta" in el else fin
        if el.get("hasta_escena") is not None:
            hasta = self.G.t[el["hasta_escena"]]["fin"]
        if t < desde or t > hasta:
            return
        u = t - desde
        fade = min(1.0, u / 0.25, max(0.0, (hasta - t) / 0.25))
        tipo = el["tipo"]
        if tipo == "resaltar":
            pul = 0.5 + 0.5 * math.sin(u * 6)
            self._contorno(base, cam, el["trozos"], color=tuple(el.get("color", AMARILLO)),
                           relleno=int(90 * fade), grosor=8, pulso=pul)
        elif tipo == "circulo":
            x, y = self.geo_px(el["lon"], el["lat"], cam)
            r = el.get("radio", 90) * (0.9 + 0.12 * math.sin(u * 5)) * ease_out_back(u / 0.4)
            capa = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(capa)
            d.ellipse((x - r - 4, y - r - 4, x + r + 4, y + r + 4), outline=(255, 255, 255, int(230 * fade)), width=14)
            d.ellipse((x - r, y - r, x + r, y + r), outline=AMARILLO + (int(255 * fade),), width=8)
            base.alpha_composite(capa)
        elif tipo in ("punto", "etiqueta_mapa"):
            x, y = self.geo_px(el["lon"], el["lat"], cam)
            x += el.get("ox", 0); y += el.get("oy", 0)
            d = ImageDraw.Draw(base)
            if tipo == "punto":
                r = 16 * ease_out_back(u / 0.35)
                d.ellipse((x - r - 6, y - r - 6, x + r + 6, y + r + 6), fill=BLANCO)
                d.ellipse((x - r, y - r, x + r, y + r), fill=ROJO)
            f = fuente(el["texto"], el.get("tam", 50))
            tw = d.textlength(el["texto"], font=f)
            lx = x + (34 if tipo == "punto" else -tw / 2 - 26)
            if tipo == "punto" and el.get("lado") == "izq":
                lx = x - 34 - tw - 52
            lx = min(max(lx, 40), W - SAFE_RIGHT - tw - 52)
            ly = y - 38 if tipo == "punto" else y - 38
            capa = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dc = ImageDraw.Draw(capa)
            dc.rounded_rectangle((lx, ly, lx + tw + 52, ly + 76), 20, fill=(255, 255, 255, int(240 * fade)))
            dc.text((lx + 26, ly + 38), el["texto"], font=f, fill=TINTA + (int(255 * fade),), anchor="lm")
            base.alpha_composite(capa)
        elif tipo in ("tarjeta", "cifra"):
            im = tarjeta_img(el["texto"], el.get("sub"), grande=(tipo == "cifra"),
                             acento=tuple(el.get("acento", AMARILLO)))
            esc = 0.82 + 0.18 * ease_out_back(u / 0.35)
            pegar_centrado(base, im, (W - SAFE_RIGHT) / 2 + 35, el.get("y", 700), esc, fade)
        elif tipo == "comparar":
            self._comparar(base, el, u, fade)
        elif tipo == "comentario":
            im = comentario_img(el["texto"], el.get("etiqueta", ""))
            esc = 0.85 + 0.15 * ease_out_back(min(1.0, u / 0.35))
            pegar_centrado(base, im, (W - SAFE_RIGHT) / 2 + 35, el.get("y", 360), esc, fade)

    def _comparar(self, base, el, u, fade):
        capa = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(capa)
        y0 = el.get("y", 560); x0, x1 = 70, W - SAFE_RIGHT - 20
        filas = el["filas"]; vmax = max(f["valor"] for f in filas)
        alto = 70 + 150 * len(filas)
        d.rounded_rectangle((x0 - 20, y0, x1 + 20, y0 + alto), 34, fill=TINTA + (int(235 * fade),))
        for i, f in enumerate(filas):
            yy = y0 + 45 + i * 150
            fl = fuente(f["etiqueta"], 44, gruesa=False)
            d.text((x0 + 20, yy), f["etiqueta"], font=fl, fill=(220, 228, 240, int(255 * fade)))
            k = ease(u / 0.9 - i * 0.25)
            ancho = (x1 - x0 - 60) * f["valor"] / vmax * k
            col = tuple(f.get("color", AMARILLO))
            d.rounded_rectangle((x0 + 20, yy + 58, x0 + 20 + max(ancho, 12), yy + 112), 14, fill=col + (int(255 * fade),))
            fv = fuente(f["texto"], 46)
            tv = f["texto"]
            tw = d.textlength(tv, font=fv)
            tx = min(x0 + 34 + ancho, x1 - tw - 10) if ancho > tw + 40 else x0 + 34
            if ancho > tw + 40: tx = x0 + 20 + ancho - tw - 18
            d.text((tx, yy + 85), tv, font=fv, fill=TINTA + (int(255 * fade),) if ancho > tw + 40 else BLANCO + (int(255 * fade),), anchor="lm")
        base.alpha_composite(capa)

    def _titulo(self, base, t):
        txt = self.g.get("titulo_pantalla")
        if not txt: return
        k = ease(t / 0.5)
        d = ImageDraw.Draw(base)
        size = 54; f = fuente(txt, size)
        while d.textlength(txt, font=f) > 780 and size > 30:
            size -= 2; f = fuente(txt, size)
        lineas = [txt]
        alto = 40 + 66 * len(lineas)
        capa = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dc = ImageDraw.Draw(capa)
        x0, x1 = 70, W - SAFE_RIGHT + 20
        y0 = 185 - (1 - k) * 60
        dc.rounded_rectangle((x0, y0, x1, y0 + alto), 26, fill=ROJO + (int(245 * k),))
        y = y0 + 20 + 33
        for ln in lineas:
            texto_centrado(dc, (x0 + x1) / 2, y, ln, f, BLANCO + (int(255 * k),))
            y += 66
        base.alpha_composite(capa)

    def _sub(self, base, t):
        for a, b, txt in self.subs:
            if a <= t < b:
                u = t - a
                txt = txt.upper()
                size = 78
                d = ImageDraw.Draw(base)
                f = fuente(txt, size)
                lineas = envolver(d, txt, f, 820)
                while (len(lineas) > 2 or max(d.textlength(l, font=f) for l in lineas) > 840) and size > 44:
                    size -= 6; f = fuente(txt, size); lineas = envolver(d, txt, f, 820)
                esc = 0.9 + 0.1 * ease_out_back(u / 0.18)
                lh = size * 1.15
                im = Image.new("RGBA", (W, int(lh * len(lineas) + 40)), (0, 0, 0, 0)); di = ImageDraw.Draw(im)
                y = 20 + lh / 2
                for ln in lineas:
                    texto_centrado(di, (W - SAFE_RIGHT) / 2 + 35, y, ln, f, BLANCO, stroke=10, sfill=(10, 12, 18))
                    y += lh
                cy = 1395 - (len(lineas) - 1) * lh / 2
                if esc != 1:
                    im2 = im.resize((int(W * esc), int(im.height * esc)), Image.BILINEAR)
                    base.alpha_composite(im2, (int((W - im2.width) / 2), int(cy - im2.height / 2)))
                else:
                    base.alpha_composite(im, (0, int(cy - im.height / 2)))
                return

    def frame(self, t):
        cam = self.camara(t)
        base = self.mapa.frame(*cam).convert("RGBA")
        T = self.G.t
        # contorno del país (se dibuja en la primera escena)
        dib = self.g.get("dibujar_contorno", 2.2)
        prog = ease((t - 0.2) / dib) if dib else 1.0
        cfg = self.g.get("contorno_estilo", {})
        if not self.g.get("sin_contorno"):  # «sin_contorno»: solo se ven los trozos que se resaltan
          self._contorno(base, cam, list(range(len(self.trozos))), prog=prog,
                       color=tuple(cfg.get("color", ROJO)), relleno=cfg.get("relleno", 70),
                       grosor=cfg.get("grosor", 7))
        for i, e in enumerate(self.G.escenas):
            ini, fin = T[i]["ini"], T[i]["fin"]
            for el in e.get("elementos", []):
                self._elemento(base, el, t, ini, fin, cam)
        base.alpha_composite(self.vineta)
        self._titulo(base, t)
        self._sub(base, t)
        # fundido final
        if t > self.G.duracion - 0.5:
            k = (t - (self.G.duracion - 0.5)) / 0.5
            base = Image.blend(base, Image.new("RGBA", (W, H), (0, 0, 0, 255)), min(1, k) * 0.9)
        return base.convert("RGB")

    # ------------------------------------------------ audio
    def audio(self, path):
        sr = 44100
        n = int(self.G.duracion * sr) + sr
        voz = np.zeros(n, np.float32)
        for i, T in enumerate(self.G.t):
            d = leer_wav(self.G.ruta(f"voz/{i:02d}.wav"))
            a = int(T["ini"] * sr); voz[a:a + len(d)] += d[: n - a]
        pk = np.abs(voz).max() or 1
        voz = voz / pk * 0.89
        mezcla = voz.copy()
        if self.g.get("musica", True):
            t = np.arange(n) / sr
            acordes = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (130.81, 196.0, 261.63), (196.0, 246.94, 293.66)]
            pad = np.zeros(n, np.float32); dur = 4.0
            for k in range(int(n / sr / dur) + 1):
                a, b = int(k * dur * sr), int((k + 1) * dur * sr + sr)
                b = min(b, n)
                if a >= n: break
                tt = t[a:b] - k * dur
                env = np.clip(tt / 1.2, 0, 1) * np.clip((dur + 1 - tt) / 1.2, 0, 1)
                for f in acordes[k % 4]:
                    pad[a:b] += (np.sin(2 * np.pi * f * tt) * 0.5 + np.sin(2 * np.pi * f * 2.003 * tt) * 0.12) * env
            # pulso suave de bajo
            beat = 60 / 96
            bajo = np.zeros(n, np.float32)
            for k in range(int(n / sr / beat)):
                a = int(k * beat * sr); b = min(n, a + int(0.35 * sr))
                tt = t[a:b] - k * beat
                f = acordes[int(k * beat / dur) % 4][0] / 2
                bajo[a:b] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 9)
            mus = pad / (np.abs(pad).max() or 1) * 0.07 + bajo / (np.abs(bajo).max() or 1) * 0.06
            # baja la música mientras habla la voz
            envv = np.convolve(np.abs(voz), np.ones(4410) / 4410, mode="same")
            duck = 1 - 0.45 * np.clip(envv / 0.05, 0, 1)
            mus *= duck
            mus[-sr * 2:] *= np.linspace(1, 0, sr * 2)
            mezcla += mus
            # golpes de aire en los cambios de cámara grandes
            rng = np.random.default_rng(7)
            for i, c in enumerate(self.camaras):
                if i == 0: continue
                if abs(c["z"] - self.camaras[i - 1]["z"]) < 0.6: continue
                a = int(self.G.t[i]["ini"] * sr); m = int(0.6 * sr)
                if a + m > n: continue
                ruido = rng.standard_normal(m).astype(np.float32)
                ruido = np.convolve(ruido, np.ones(18) / 18, mode="same")
                env = np.sin(np.linspace(0, np.pi, m)) ** 2
                mezcla[a:a + m] += ruido * env * 0.18
        mezcla = mezcla / max(1.0, np.abs(mezcla).max() / 0.95)
        escribir_wav(path, mezcla[: int(self.G.duracion * sr)], sr)

    def video(self, salida):
        tmp_a = self.G.ruta("_audio.wav")
        self.audio(tmp_a)
        nf = int(self.G.duracion * FPS)
        p = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                              "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", tmp_a,
                              "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                              "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                              "-movflags", "+faststart", "-shortest", salida], stdin=subprocess.PIPE)
        for i in range(nf):
            p.stdin.write(self.frame(i / FPS).tobytes())
            if i % 150 == 0:
                print(f"  fotograma {i}/{nf}", flush=True)
        p.stdin.close(); p.wait()
        os.remove(tmp_a)
        if p.returncode: raise SystemExit("ffmpeg falló")
        print("Vídeo listo:", salida)

    def fotos(self, carpeta):
        os.makedirs(carpeta, exist_ok=True)
        tiempos = []
        for i, T in enumerate(self.G.t):
            tiempos += [T["ini"] + 0.15, T["ini"] + min(1.6, T["voz"] * 0.5), T["fin"] - 0.15]
        miniaturas = []
        for k, t in enumerate(tiempos):
            im = self.frame(t)
            im.save(f"{carpeta}/f{k:02d}.jpg", quality=85)
            th = im.resize((270, 480)); ImageDraw.Draw(th).text((8, 8), f"{t:.1f}s", fill=(255, 0, 0))
            miniaturas.append(th)
        cols = 9; filas = math.ceil(len(miniaturas) / cols)
        hoja = Image.new("RGB", (cols * 270, filas * 480), (0, 0, 0))
        for k, th in enumerate(miniaturas):
            hoja.paste(th, ((k % cols) * 270, (k // cols) * 480))
        hoja.save(f"{carpeta}/hoja.jpg", quality=85)
        print("Hoja:", f"{carpeta}/hoja.jpg")

def main():
    guion = Guion(sys.argv[1]); orden = sys.argv[2]
    if orden == "voz":
        guion.voz(); return
    r = Render(guion)
    if orden == "fotos":
        r.fotos(guion.ruta("fotos"))
    elif orden == "foto":
        t = float(sys.argv[3]); r.frame(t).save(guion.ruta(f"fotos/t{t:.1f}.jpg"))
    elif orden == "video":
        nombre = re.sub(r'[\\/:*?"<>|]', "", guion.g.get("titulo", "short")).strip()
        r.video(guion.ruta(nombre + ".mp4"))

if __name__ == "__main__":
    main()
