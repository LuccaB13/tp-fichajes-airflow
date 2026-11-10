"""La portada de la aplicación: una cancha y una pelota dibujadas en SVG, y una foto de Ronaldinho.

La foto es de Wikimedia Commons, con licencia libre CC BY-SA 3.0: se usa sin modificar el archivo (el recorte y el
degradé se hacen con CSS al mostrarla) y con el crédito del autor, que es lo que pide la licencia.
"""
import base64
import functools
import math
import os

IMAGENES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imagenes")
TIPOS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
# Si en app/imagenes/ hay un archivo «portada» (.jpg, .jpeg, .png o .webp), la portada usa ése.
# Si no, usa la foto libre de Wikimedia Commons, con su crédito.
COMMONS = {"archivo": "ronaldinho_2006.jpg", "posicion": "38% 6%", "ancho": "42%",
           "credito": ('Foto: <a href="https://commons.wikimedia.org/wiki/File:Ronaldinho_Belletti_and_Giuly_9dec2006.jpg" '
                       'target="_blank">Ronaldinho festejando un gol en el Camp Nou (2006)</a>, de Darz Mol, '
                       '<a href="https://creativecommons.org/licenses/by-sa/3.0/deed.es" target="_blank">CC BY-SA 3.0</a>, '
                       'Wikimedia Commons')}
PROPIA = {"posicion": "50% 0%", "ancho": "30%", "credito": ""}


def _foto():
    """Qué foto usar, con dónde recortarla, qué ancho ocupa y su crédito."""
    for ext in TIPOS:
        if os.path.exists(os.path.join(IMAGENES, "portada" + ext)):
            return {**PROPIA, "archivo": "portada" + ext}
    return COMMONS

BLANCO = "#ffffff"
OSCURO = "#13261a"


def _pentagono(cx, cy, radio, giro):
    """Los 5 vértices de un pentágono regular, como texto para un <polygon>."""
    puntos = []
    for k in range(5):
        a = math.radians(giro + 72 * k)
        puntos.append(f"{cx + radio * math.cos(a):.1f},{cy + radio * math.sin(a):.1f}")
    return " ".join(puntos)


def pelota(cx, cy, r, id_recorte, trazo=None):
    """Una pelota de fútbol clásica: un pentágono negro en el centro, cinco costuras y cinco pentágonos en el borde."""
    trazo = trazo or max(1.0, r / 14)
    p = 0.32 * r                                   # radio del pentágono central
    partes = [f'<clipPath id="{id_recorte}"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>',
              f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{BLANCO}"/>',
              f'<g clip-path="url(#{id_recorte})" fill="{OSCURO}" stroke="{OSCURO}" stroke-width="{trazo:.1f}" '
              'stroke-linejoin="round">',
              f'<polygon points="{_pentagono(cx, cy, p, -90)}"/>']
    for k in range(5):
        a = math.radians(-90 + 72 * k)
        # costura que sale de cada vértice del centro hacia el pentágono del borde
        x1, y1 = cx + p * math.cos(a), cy + p * math.sin(a)
        x2, y2 = cx + 0.70 * r * math.cos(a), cy + 0.70 * r * math.sin(a)
        partes.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
        # pentágono del borde, con una punta mirando al centro (queda cortado por el círculo)
        ex, ey = cx + 1.02 * r * math.cos(a), cy + 1.02 * r * math.sin(a)
        partes.append(f'<polygon points="{_pentagono(ex, ey, p, -90 + 72 * k + 180)}"/>')
    partes.append("</g>")
    partes.append(f'<circle cx="{cx}" cy="{cy}" r="{r - trazo / 2:.1f}" fill="none" stroke="{OSCURO}" '
                  f'stroke-width="{trazo:.1f}"/>')
    return "".join(partes)


def _cancha():
    """Las líneas de una cancha vista desde arriba, muy tenues, de fondo."""
    linea = 'fill="none" stroke="white" stroke-opacity="0.13" stroke-width="3"'
    return (
        '<svg class="portada-cancha" viewBox="0 0 1200 320" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
        f'<rect x="30" y="20" width="1140" height="280" {linea}/>'
        f'<line x1="600" y1="20" x2="600" y2="300" {linea}/>'
        f'<circle cx="600" cy="160" r="62" {linea}/>'
        '<circle cx="600" cy="160" r="5" fill="white" fill-opacity="0.13"/>'
        f'<rect x="30" y="75" width="150" height="170" {linea}/>'
        f'<rect x="30" y="122" width="55" height="76" {linea}/>'
        f'<path d="M180 120 A 62 62 0 0 1 180 200" {linea}/>'
        f'<rect x="1020" y="75" width="150" height="170" {linea}/>'
        f'<rect x="1115" y="122" width="55" height="76" {linea}/>'
        f'<path d="M1020 120 A 62 62 0 0 0 1020 200" {linea}/>'
        "</svg>")


@functools.lru_cache(maxsize=4)
def _foto_base64(archivo):
    """La foto embebida en el HTML (st.markdown no sirve archivos locales por URL)."""
    with open(os.path.join(IMAGENES, archivo), "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


ESTILO = """
<style>
.portada {position: relative; overflow: hidden; border-radius: 16px; color: white; min-height: 340px;
  display: flex; align-items: center; padding: 2.4rem 2.4rem 2.8rem; margin-bottom: 1.2rem;
  background:
    repeating-linear-gradient(90deg, rgba(255,255,255,0.05) 0 90px, rgba(255,255,255,0) 90px 180px),
    linear-gradient(115deg, #0a2614 0%, #14532d 50%, #2e8540 100%);}
.portada-cancha {position: absolute; inset: 0; width: 100%; height: 100%;}
/* la foto ocupa el costado derecho y se funde con el verde hacia la izquierda */
.portada-foto {position: absolute; top: 0; right: 0; bottom: 0; width: 42%; margin: 0;
  -webkit-mask-image: linear-gradient(to right, transparent 0%, black 38%);
          mask-image: linear-gradient(to right, transparent 0%, black 38%);}
.portada-foto img {width: 100%; height: 100%; object-fit: cover; object-position: 38% 6%; display: block;}
.portada-texto {position: relative; flex: 0 1 60%;}
.portada-chico {font-size: 0.78rem; letter-spacing: 0.14em; text-transform: uppercase; opacity: 0.85;
  display: flex; align-items: center; gap: 0.5rem;}
.portada .portada-titulo {color: white; font-size: 2.6rem; font-weight: 800; line-height: 1.1; margin: 0.7rem 0 0.8rem;
  text-shadow: 0 2px 12px rgba(0,0,0,0.35);}
.portada-sub {font-size: 1.05rem; opacity: 0.92;}
.portada-sub b {color: white;}
.portada-credito {position: absolute; right: 0.9rem; bottom: 0.5rem; font-size: 0.68rem; color: rgba(255,255,255,0.8);
  text-shadow: 0 1px 3px rgba(0,0,0,0.8); max-width: 40%; text-align: right; line-height: 1.3;}
.portada-credito a {color: rgba(255,255,255,0.95); text-decoration: underline;}
@media (max-width: 900px) {
  .portada {padding: 1.6rem 1.4rem 3rem; min-height: 0;}
  .portada .portada-titulo {font-size: 1.7rem;}
  .portada-texto {flex-basis: 100%;}
  .portada-foto {width: 100% !important; opacity: 0.35;
    -webkit-mask-image: linear-gradient(to right, transparent 0%, black 60%);
            mask-image: linear-gradient(to right, transparent 0%, black 60%);}
  .portada-credito {max-width: 90%;}
}
</style>"""


def html(titulo, subtitulo):
    """La portada completa: el estilo, la cancha de fondo, la foto, el texto y el crédito de la foto."""
    logo = f'<svg width="22" height="22" viewBox="0 0 44 44" aria-hidden="true">{pelota(22, 22, 21, "recorte-pelota-chica")}</svg>'
    foto = _foto()
    tipo = TIPOS[os.path.splitext(foto["archivo"])[1]]
    credito = f'<div class="portada-credito">{foto["credito"]}</div>' if foto["credito"] else ""
    return (ESTILO + '<div class="portada">' + _cancha()
            + f'<figure class="portada-foto" style="width: {foto["ancho"]}">'
              f'<img src="data:{tipo};base64,{_foto_base64(foto["archivo"])}" style="object-position: {foto["posicion"]}" '
              'alt="Ronaldinho con la camiseta del Barcelona"></figure>'
            + '<div class="portada-texto">'
            + f'<div class="portada-chico">{logo}<span>Ciencia de Datos · UTN FRM · Grupo 7 · 2026</span></div>'
            + f'<div class="portada-titulo" role="heading" aria-level="1">{titulo}</div>'
            + f'<div class="portada-sub">{subtitulo}</div>'
            + "</div>"
            + credito
            + "</div>")
