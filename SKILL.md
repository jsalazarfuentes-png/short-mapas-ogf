---
name: short-mapas-ogf
description: Hace un short vertical (1080x1920, 55-75 s) de geografía de OpenGeofiction (OGF) con el mapa REAL de OGF (teselas ogf-carto), el contorno real del país sacado de los datos del mapa, voz automática de Apple (orden `say`, voz Mónica) y subtítulos. Sin Remotion y sin emojis. Activar cuando el usuario pida un vídeo o short de un país, región o lugar de OpenGeofiction / OGF, sobre todo de formas raras, exclaves o fronteras extrañas.
---

# Shorts de OpenGeofiction con voz de Apple

Todo es independiente: Python + ffmpeg (imageio-ffmpeg). No usa la plantilla de Shorts de Mapas ni sus recursos.

## Preparar (una vez por sesión)
```
python3 -m venv <scratchpad>/venv && <scratchpad>/venv/bin/pip install pillow numpy imageio-ffmpeg fonttools
```
Herramientas en `~/.claude/skills/short-mapas-ogf/` (render.py, ogf_datos.py, ogf_mapa.py).

## Pasos
1. **Datos solo del mapa** (no de la wiki salvo que el usuario lo pida):
   `ogf_datos.py "Nombre" <proyecto>/datos` -> `datos.md` con etiquetas (fundación, huso, idioma, nombre oficial...), trozos con km², vecinos y lugares con capital. Todo dato del guion sale de ahí. Nunca inventar.
2. **Mapas**: `ogf_mapa.py <proyecto>/mapas zNN --zona O S E N --z NN` para cada nivel que use la cámara
   (uno por zoom entero, de 5 a 12, cada uno cubriendo con margen lo que verá la cámara a ese zoom; máx. 900 teselas).
   Revisar dibujando el contorno encima antes de escribir las tomas.
3. **Guion** `<proyecto>/guion.json` (ver ejemplo `ejemplo_podopotztaalka.json`). 150-190 palabras, una frase por escena.
   - `texto`: subtítulo con la ortografía real. `dice`: lo que lee la voz (fonética: Podopotztaalka -> «Podopotstálka»,
     cifras en letra, códigos deletreados «U, ele, veintisiete, jota»).
   - `camara`: lon, lat, z (zoom fraccionario), `mov` (s de viaje), `deriva` (empuje lento; la cámara nunca se para).
   - `elementos`: `resaltar` (trozos por índice de datos.md), `circulo`, `punto`, `etiqueta_mapa`, `tarjeta`, `cifra`, `comparar`; tiempos `desde`/`hasta` en s desde el inicio de la escena.
   - Sin emojis en ningún texto.
4. **Voz**: `render.py guion.json voz` (voz de Apple, frase a frase; mide tiempos).
5. **Revisar**: `render.py guion.json fotos` y mirar `fotos/hoja.jpg`. Nada puede pisarse: título arriba (185-290 px),
   tarjetas desde y=560, subtítulos 1300-1480, nada importante en los 150 px de la derecha.
6. **Vídeo**: `render.py guion.json video` -> `<titulo>.mp4` en la carpeta del proyecto (~5 min).
7. Texto para subir con crédito: «Mapa: OpenGeofiction (opengeofiction.net), CC BY-NC-SA 2.0». Voz: Apple (sistema). Música: sintetizada por el propio script.
