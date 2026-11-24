# short-mapas-ogf

Skill para [Claude Code](https://claude.com/claude-code) que hace shorts verticales (1080x1920, 55-75 s) sobre países y lugares de [OpenGeofiction](https://opengeofiction.net) (OGF).

- Usa el mapa real de OGF (teselas `ogf-carto`).
- Saca el contorno real del país de los datos del mapa.
- La voz es la de Apple (orden `say`, voz Mónica) y el vídeo lleva subtítulos.
- No hace falta Remotion ni ningún programa de pago.

## Qué necesitas

- Un Mac (la voz usa la orden `say` y las fuentes Arial del sistema).
- Python 3.
- Claude Code.

## Instalar

**Opción 1, con git:**

```bash
git clone https://github.com/jsalazarfuentes-png/short-mapas-ogf.git ~/.claude/skills/short-mapas-ogf
```

**Opción 2, con el zip:** descarga `short-mapas-ogf.zip`, descomprímelo y pon la carpeta `short-mapas-ogf` dentro de `~/.claude/skills/`.

Abre Claude Code y pide, por ejemplo: «hazme un short de OGF sobre Podopotztaalka».

## Cómo funciona

1. `ogf_datos.py`: saca los datos del país del mapa de OGF (trozos, km², vecinos, capital).
2. `ogf_mapa.py`: descarga las teselas del mapa para cada nivel de zoom.
3. `guion.json`: el guion con escenas, cámara y elementos. Tienes un ejemplo en `ejemplo_podopotztaalka.json`.
4. `render.py guion.json voz | fotos | video`: graba la voz, hace una hoja de fotogramas para revisar y monta el vídeo final.

Las instrucciones completas para Claude están en [`SKILL.md`](SKILL.md).

## Créditos y licencias

- **Código:** licencia MIT (ver `LICENSE`).
- **Mapas:** los vídeos que hagas con esta skill usan el mapa de OpenGeofiction. Pon siempre este crédito: «Mapa: OpenGeofiction (opengeofiction.net), CC BY-NC-SA 2.0». Esa licencia no permite el uso comercial del mapa.
- **Descargas:** usa las teselas y la API de OGF con moderación. El script ya limita cuántas teselas descarga.
