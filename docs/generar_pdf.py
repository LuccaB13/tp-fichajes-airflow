"""Genera el PDF de la documentación a partir de `EXPLICACION.md`.

    py docs/generar_pdf.py

El markdown es la fuente de verdad: se edita ese archivo y se vuelve a correr
esto. El bloque ```mermaid del diagrama se reemplaza por un diagrama dibujado,
porque en un PDF no hay quién renderice mermaid.

Necesita reportlab, que es una dependencia **sólo de documentación** y por eso
no está en `requirements.txt` (el pipeline no la usa):

    py -m pip install reportlab
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

AQUI = Path(__file__).resolve().parent
ENTRADA = AQUI / "EXPLICACION.md"
SALIDA = AQUI / "Explicacion_Pipeline_Fichajes.pdf"

# ----------------------------------------------------------------- paleta
TINTA = colors.HexColor("#14181F")
TINTA_SUAVE = colors.HexColor("#4E5967")
TINTA_TENUE = colors.HexColor("#78838F")
ACENTO = colors.HexColor("#1B4FA0")
ACENTO_FONDO = colors.HexColor("#EDF2FA")
LINEA = colors.HexColor("#D6DDE5")
LINEA_TENUE = colors.HexColor("#E8EDF2")
FONDO_CODIGO = colors.HexColor("#F5F7F9")
BRONCE = colors.HexColor("#8A5A24")
PLATA = colors.HexColor("#5C6875")


# ---------------------------------------------------------------- fuentes
def registrar_fuentes():
    """Usa las fuentes de Windows. Se incrustan en el PDF, así que el archivo
    se ve igual en cualquier máquina."""
    fuentes = Path("C:/Windows/Fonts")
    pares = [
        ("Cuerpo", "calibri.ttf"), ("Cuerpo-Bold", "calibrib.ttf"),
        ("Cuerpo-Italic", "calibrii.ttf"), ("Cuerpo-BoldItalic", "calibriz.ttf"),
        ("Titulo", "segoeuib.ttf"), ("Titulo-Light", "segoeui.ttf"),
        ("Mono", "consola.ttf"), ("Mono-Bold", "consolab.ttf"),
    ]
    for nombre, archivo in pares:
        ruta = fuentes / archivo
        if not ruta.exists():
            raise SystemExit(f"falta la fuente {ruta}")
        pdfmetrics.registerFont(TTFont(nombre, str(ruta)))
    pdfmetrics.registerFontFamily(
        "Cuerpo", normal="Cuerpo", bold="Cuerpo-Bold",
        italic="Cuerpo-Italic", boldItalic="Cuerpo-BoldItalic")


# ---------------------------------------------------------------- estilos
def construir_estilos():
    base = dict(fontName="Cuerpo", fontSize=9.6, leading=14.2, textColor=TINTA)
    return {
        "cuerpo": ParagraphStyle("cuerpo", spaceAfter=7, **base),
        "cuerpo_tabla": ParagraphStyle(
            "cuerpo_tabla", fontName="Cuerpo", fontSize=8.5, leading=11.4,
            textColor=TINTA),
        "cabecera_tabla": ParagraphStyle(
            "cabecera_tabla", fontName="Cuerpo-Bold", fontSize=7.6, leading=10,
            textColor=TINTA_TENUE),
        "h1": ParagraphStyle("h1", fontName="Titulo", fontSize=19, leading=23,
                             textColor=TINTA, spaceBefore=4, spaceAfter=12),
        "h2": ParagraphStyle("h2", fontName="Titulo", fontSize=14.5, leading=18,
                             textColor=TINTA, spaceBefore=16, spaceAfter=8),
        "h3": ParagraphStyle("h3", fontName="Titulo", fontSize=11, leading=14.5,
                             textColor=ACENTO, spaceBefore=12, spaceAfter=5),
        "h4": ParagraphStyle("h4", fontName="Cuerpo-Bold", fontSize=9.6,
                             leading=13, textColor=TINTA_SUAVE,
                             spaceBefore=9, spaceAfter=4),
        "lista": ParagraphStyle("lista", spaceAfter=3, leftIndent=13,
                                bulletIndent=3, **base),
        "codigo": ParagraphStyle("codigo", fontName="Mono", fontSize=7.8,
                                 leading=10.6, textColor=TINTA),
        "aviso_titulo": ParagraphStyle(
            "aviso_titulo", fontName="Cuerpo-Bold", fontSize=9.4, leading=13,
            textColor=ACENTO, spaceAfter=3),
        "aviso": ParagraphStyle("aviso", fontName="Cuerpo", fontSize=9.2,
                                leading=13.4, textColor=TINTA_SUAVE,
                                spaceAfter=4),
        "portada_titulo": ParagraphStyle(
            "portada_titulo", fontName="Titulo", fontSize=29, leading=33,
            textColor=TINTA, spaceAfter=10),
        "portada_bajada": ParagraphStyle(
            "portada_bajada", fontName="Titulo-Light", fontSize=12.5,
            leading=18, textColor=TINTA_SUAVE, spaceAfter=22),
        "portada_pie": ParagraphStyle(
            "portada_pie", fontName="Cuerpo", fontSize=9.5, leading=15,
            textColor=TINTA_TENUE),
        "pie_doc": ParagraphStyle("pie_doc", fontName="Cuerpo-Italic",
                                  fontSize=8.6, leading=12.5,
                                  textColor=TINTA_TENUE, alignment=TA_CENTER),
    }


# ------------------------------------------------------- formato en línea
def en_linea(texto: str) -> str:
    """`code`, **negrita** y *cursiva* a las mini-etiquetas de reportlab.

    Los tramos de código se sacan primero y se reemplazan por un marcador, para
    que la negrita pueda **envolver** un `código` sin que el asterisco quede
    partido en dos pedazos y se imprima literal.
    """
    guardados: list[str] = []

    def guardar(m):
        guardados.append(m.group(1))
        return f"\x00{len(guardados) - 1}\x00"

    p = re.sub(r"`([^`]+)`", guardar, texto)
    p = html.escape(p)
    p = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", p)
    p = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", p)
    p = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", p)

    def restaurar(m):
        return ('<font face="Mono" size="8.4" color="#23408A">'
                + html.escape(guardados[int(m.group(1))]) + "</font>")

    return re.sub(r"\x00(\d+)\x00", restaurar, p)


# ------------------------------------------------- el diagrama, dibujado
class DiagramaDAG(Flowable):
    """El grafo de tareas, dibujado con primitivas.

    Tres columnas: el corte del cortocircuito a la izquierda, el flujo
    principal al centro, y la rama de respaldo a la derecha.
    """

    ALTO_CAJA = 30
    SALTO = 48

    def __init__(self, ancho):
        super().__init__()
        self.ancho = ancho
        self.filas = 10
        self.alto = self.filas * self.ALTO_CAJA + (self.filas - 1) * (
            self.SALTO - self.ALTO_CAJA) + 16

    def wrap(self, disponible_x, disponible_y):
        return self.ancho, self.alto

    # -- helpers ---------------------------------------------------------
    def _y(self, fila):
        """Borde superior de la fila, midiendo desde arriba."""
        return self.alto - 8 - fila * self.SALTO

    def _caja(self, x, fila, ancho, titulo, sub="", tipo="tarea"):
        c = self.canv
        y = self._y(fila) - self.ALTO_CAJA
        relleno, borde, color_txt = colors.white, LINEA, TINTA
        if tipo == "decision":
            relleno, borde, color_txt = ACENTO_FONDO, ACENTO, ACENTO
        elif tipo == "fin":
            relleno, borde, color_txt = colors.HexColor("#EFF5EF"), \
                colors.HexColor("#5C8A5C"), colors.HexColor("#33613A")
        elif tipo == "respaldo":
            relleno, borde, color_txt = colors.HexColor("#FBF4EC"), BRONCE, BRONCE

        c.setFillColor(relleno)
        c.setStrokeColor(borde)
        c.setLineWidth(0.9)
        c.roundRect(x, y, ancho, self.ALTO_CAJA, 3, stroke=1, fill=1)

        c.setFillColor(color_txt)
        c.setFont("Mono-Bold", 6.9)
        centro = x + ancho / 2
        c.drawCentredString(centro, y + (18 if sub else 11), titulo)
        if sub:
            c.setFillColor(TINTA_TENUE)
            c.setFont("Cuerpo-Italic", 6.3)
            c.drawCentredString(centro, y + 7, sub)
        return (x, y, ancho, self.ALTO_CAJA)

    def _flecha(self, x1, y1, x2, y2, etiqueta=None, lado="der"):
        c = self.canv
        c.setStrokeColor(TINTA_SUAVE)
        c.setFillColor(TINTA_SUAVE)
        c.setLineWidth(0.8)
        c.line(x1, y1, x2, y2)
        # punta
        if abs(x1 - x2) < 0.5:                       # vertical
            dy = -4 if y2 < y1 else 4
            c.setFillColor(TINTA_SUAVE)
            p = c.beginPath()
            p.moveTo(x2, y2)
            p.lineTo(x2 - 2.8, y2 - dy)
            p.lineTo(x2 + 2.8, y2 - dy)
            p.close()
            c.drawPath(p, fill=1, stroke=0)
        else:                                        # horizontal
            dx = -4 if x2 < x1 else 4
            p = c.beginPath()
            p.moveTo(x2, y2)
            p.lineTo(x2 - dx, y2 - 2.8)
            p.lineTo(x2 - dx, y2 + 2.8)
            p.close()
            c.drawPath(p, fill=1, stroke=0)
        if etiqueta:
            c.setFont("Cuerpo", 6.2)
            c.setFillColor(TINTA_TENUE)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if lado == "der":
                c.drawString(mx + 3, my - 2, etiqueta)
            else:
                c.drawRightString(mx - 3, my - 2, etiqueta)

    def _codo(self, x1, y1, x2, y2, etiqueta=None):
        """Va en L: primero horizontal, después vertical."""
        c = self.canv
        c.setStrokeColor(TINTA_SUAVE)
        c.setLineWidth(0.8)
        c.line(x1, y1, x2, y1)
        self._flecha(x2, y1, x2, y2)
        if etiqueta:
            c.setFont("Cuerpo", 6.2)
            c.setFillColor(TINTA_TENUE)
            c.drawCentredString((x1 + x2) / 2, y1 + 3, etiqueta)

    # -- dibujo ----------------------------------------------------------
    def draw(self):
        W = self.ancho
        an_c = 196                      # ancho de la columna central
        x_c = (W - an_c) / 2
        an_l, an_r = 104, 118
        x_l = max(0, x_c - an_l - 22)
        x_r = min(W - an_r, x_c + an_c + 22)
        cen = x_c + an_c / 2

        self._caja(x_c, 0, an_c, "esperar_fuentes", "@task.sensor · reschedule")
        self._caja(x_c, 1, an_c, "elegir_camino", "@task.branch · ALL_DONE",
                   tipo="decision")
        self._caja(x_c, 2, an_c, "hay_novedad", "@task.short_circuit",
                   tipo="decision")
        self._caja(x_r, 2, an_r, "usar_respaldo", "plata congelada",
                   tipo="respaldo")
        self._caja(x_l, 3, an_l, "fin de la corrida", "en verde, sin bajar nada",
                   tipo="fin")
        self._caja(x_c, 3, an_c, "aterrizar_bronce_uefa", "JSON crudo")
        self._caja(x_c, 4, an_c, "construir_catalogo", "cruce UEFA con TM")
        self._caja(x_c, 5, an_c, "aterrizar_bronce_transfermarkt",
                   ".expand() · una por club")
        self._caja(x_c, 6, an_c, "aterrizar_bronce_fotmob",
                   ".expand() · una por club")
        self._caja(x_c, 7, an_c, "generar_capa_plata", "ALL_DONE · sin red")
        self._caja(x_c, 8, an_c, "validar_dataset_plata",
                   "NONE_FAILED_MIN_ONE_SUCCESS")
        self._caja(x_c, 9, an_c, "publicar", "CSV fechado + huella")

        # flechas verticales del tronco
        for fila in (0, 1, 2, 3, 4, 5, 6, 7, 8):
            if fila in (1, 2):
                continue
            self._flecha(cen, self._y(fila) - self.ALTO_CAJA,
                         cen, self._y(fila + 1))
        self._flecha(cen, self._y(1) - self.ALTO_CAJA, cen, self._y(2),
                     "fuentes OK")
        self._flecha(cen, self._y(2) - self.ALTO_CAJA, cen, self._y(3), "True")

        # rama derecha: del branch al respaldo, y del respaldo a validar
        self._codo(x_c + an_c, self._y(1) - self.ALTO_CAJA / 2,
                   x_r + an_r / 2, self._y(2), "sin respuesta")
        c = self.canv
        c.setStrokeColor(TINTA_SUAVE)
        c.setLineWidth(0.8)
        y_resp = self._y(2) - self.ALTO_CAJA
        y_val = self._y(8) - self.ALTO_CAJA / 2
        c.line(x_r + an_r / 2, y_resp, x_r + an_r / 2, y_val)
        self._flecha(x_r + an_r / 2, y_val, x_c + an_c, y_val)

        # rama izquierda: el cortocircuito que corta
        self._codo(x_c, self._y(2) - self.ALTO_CAJA / 2,
                   x_l + an_l / 2, self._y(3), "False")


# ------------------------------------------------------- parser markdown
class Constructor:
    def __init__(self, estilos, ancho_util):
        self.e = estilos
        self.ancho = ancho_util
        self.historia = []

    # -- piezas ----------------------------------------------------------
    def parrafo(self, texto, estilo="cuerpo"):
        self.historia.append(Paragraph(en_linea(texto), self.e[estilo]))

    def titulo(self, texto, nivel):
        estilo = {2: "h2", 3: "h3", 4: "h4"}[nivel]
        p = Paragraph(en_linea(texto), self.e[estilo])
        if nivel == 2:
            self.historia.append(Spacer(1, 4))
            self.historia.append(_Regla(self.ancho))
        self.historia.append(p)

    def bloque_codigo(self, lineas):
        texto = "<br/>".join(
            html.escape(l).replace(" ", "&nbsp;") or "&nbsp;" for l in lineas)
        p = Paragraph(texto, self.e["codigo"])
        t = Table([[p]], colWidths=[self.ancho])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), FONDO_CODIGO),
            ("BOX", (0, 0), (-1, -1), 0.6, LINEA),
            ("LINEBEFORE", (0, 0), (0, -1), 2, PLATA),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        self.historia.append(t)
        self.historia.append(Spacer(1, 8))

    def aviso(self, lineas):
        contenido = []
        titulo = None
        cuerpo = []
        for l in lineas:
            if titulo is None and l.strip().startswith("**") and l.strip().endswith("**"):
                titulo = l.strip().strip("*")
                continue
            cuerpo.append(l)
        if titulo:
            contenido.append(Paragraph(en_linea(titulo), self.e["aviso_titulo"]))
        for parr in _agrupar_parrafos(cuerpo):
            if parr["tipo"] == "lista":
                for item in parr["items"]:
                    contenido.append(Paragraph(
                        en_linea(item), self.e["aviso"], bulletText="•"))
            elif parr["tipo"] == "codigo":
                contenido.append(Paragraph(
                    "<br/>".join(html.escape(l).replace(" ", "&nbsp;") or "&nbsp;"
                                 for l in parr["lineas"]), self.e["codigo"]))
            elif parr["tipo"] == "tabla":
                contenido.append(Spacer(1, 3))
                contenido.append(self._tabla_flowable(parr["filas"],
                                                      self.ancho - 20))
                contenido.append(Spacer(1, 3))
            else:
                contenido.append(Paragraph(en_linea(parr["texto"]), self.e["aviso"]))
        t = Table([[contenido]], colWidths=[self.ancho])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), ACENTO_FONDO),
            ("LINEBEFORE", (0, 0), (0, -1), 2.2, ACENTO),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        self.historia.append(KeepTogether(t))
        self.historia.append(Spacer(1, 9))

    def lista(self, items, ordenada=False):
        for i, item in enumerate(items, 1):
            self.historia.append(Paragraph(
                en_linea(item), self.e["lista"],
                bulletText=f"{i}." if ordenada else "•"))
        self.historia.append(Spacer(1, 5))

    def _tabla_flowable(self, filas, ancho):
        """Arma la tabla y la devuelve, sin agregarla a la historia.

        La usan las dos rutas: las tablas del cuerpo y las que aparecen dentro
        de un recuadro, que van más angostas.
        """
        cabecera, cuerpo = filas[0], filas[1:]
        n = len(cabecera)
        datos = [[Paragraph(en_linea(c), self.e["cabecera_tabla"]) for c in cabecera]]
        for fila in cuerpo:
            fila = (fila + [""] * n)[:n]
            datos.append([Paragraph(en_linea(c), self.e["cuerpo_tabla"]) for c in fila])

        # ancho proporcional al contenido, con un piso para que nada se aplaste
        pesos = []
        for col in range(n):
            largo = max(len(f[col]) if col < len(f) else 0
                        for f in [cabecera] + cuerpo)
            pesos.append(max(largo, 8) ** 0.62)
        total = sum(pesos)
        anchos = [ancho * p / total for p in pesos]

        t = Table(datos, colWidths=anchos, repeatRows=1)
        estilo = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F5F8")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, LINEA),
            ("BOX", (0, 0), (-1, -1), 0.6, LINEA),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
        for i in range(1, len(datos)):
            estilo.append(("LINEBELOW", (0, i), (-1, i), 0.4, LINEA_TENUE))
        t.setStyle(TableStyle(estilo))
        return t

    def tabla(self, filas):
        self.historia.append(self._tabla_flowable(filas, self.ancho))
        self.historia.append(Spacer(1, 10))


class _Regla(Flowable):
    def __init__(self, ancho):
        super().__init__()
        self.ancho, self.alto = ancho, 3

    def wrap(self, *_):
        return self.ancho, self.alto

    def draw(self):
        self.canv.setStrokeColor(TINTA)
        self.canv.setLineWidth(1.1)
        self.canv.line(0, 1, self.ancho, 1)


def _agrupar_parrafos(lineas):
    """Agrupa líneas sueltas en párrafos, listas, tablas y bloques de código.

    Las tablas hacen falta acá y no sólo en el cuerpo: hay recuadros que
    incluyen una, y si no se reconocen salen impresas con los pipes a la vista.
    """
    bloques, buffer, items, codigo = [], [], [], None
    tabla = []
    def cerrar_texto():
        if buffer:
            bloques.append({"tipo": "texto", "texto": " ".join(buffer)})
            buffer.clear()
    def cerrar_lista():
        if items:
            bloques.append({"tipo": "lista", "items": list(items)})
            items.clear()

    def cerrar_tabla():
        if tabla:
            bloques.append({"tipo": "tabla", "filas": list(tabla)})
            tabla.clear()

    for linea in lineas:
        if linea.strip().startswith("```"):
            if codigo is None:
                cerrar_texto(); cerrar_lista(); cerrar_tabla(); codigo = []
            else:
                bloques.append({"tipo": "codigo", "lineas": codigo}); codigo = None
            continue
        if codigo is not None:
            codigo.append(linea)
            continue
        if linea.strip().startswith("|"):
            cerrar_texto(); cerrar_lista()
            cruda = linea.strip().strip("|")
            if not re.match(r"^[\s:|-]+$", cruda):
                tabla.append([c.strip() for c in cruda.split("|")])
            continue
        cerrar_tabla()
        if not linea.strip():
            cerrar_texto(); cerrar_lista()
            continue
        if re.match(r"^\s*[-*]\s+", linea):
            cerrar_texto()
            items.append(re.sub(r"^\s*[-*]\s+", "", linea))
            continue
        if items:
            items[-1] += " " + linea.strip()
            continue
        buffer.append(linea.strip())
    cerrar_texto(); cerrar_lista(); cerrar_tabla()
    return bloques


def construir(md: str, estilos, ancho):
    c = Constructor(estilos, ancho)
    lineas = md.split("\n")
    i = 0
    # la portada y el índice se arman aparte: se salta hasta el primer "## "
    while i < len(lineas) and not lineas[i].startswith("## "):
        i += 1

    buffer_parrafo, items, ordenada = [], [], False

    def volcar_parrafo():
        if buffer_parrafo:
            c.parrafo(" ".join(buffer_parrafo))
            buffer_parrafo.clear()

    def volcar_lista():
        nonlocal ordenada
        if items:
            c.lista(list(items), ordenada)
            items.clear()
            ordenada = False

    while i < len(lineas):
        linea = lineas[i]
        desnuda = linea.strip()

        if desnuda.startswith("## "):
            volcar_parrafo(); volcar_lista()
            c.titulo(desnuda[3:], 2)
        elif desnuda.startswith("### "):
            volcar_parrafo(); volcar_lista()
            c.titulo(desnuda[4:], 3)
        elif desnuda.startswith("#### "):
            volcar_parrafo(); volcar_lista()
            c.titulo(desnuda[5:], 4)
        elif desnuda.startswith("```"):
            volcar_parrafo(); volcar_lista()
            lenguaje = desnuda[3:].strip()
            cuerpo, i = [], i + 1
            while i < len(lineas) and not lineas[i].strip().startswith("```"):
                cuerpo.append(lineas[i])
                i += 1
            if lenguaje == "mermaid":
                c.historia.append(Spacer(1, 4))
                c.historia.append(DiagramaDAG(ancho))
                c.historia.append(Spacer(1, 12))
            else:
                c.bloque_codigo(cuerpo)
        elif desnuda.startswith(">"):
            volcar_parrafo(); volcar_lista()
            cita = []
            while i < len(lineas) and lineas[i].strip().startswith(">"):
                cita.append(re.sub(r"^\s*>\s?", "", lineas[i]))
                i += 1
            i -= 1
            c.aviso(cita)
        elif desnuda.startswith("|"):
            volcar_parrafo(); volcar_lista()
            filas = []
            while i < len(lineas) and lineas[i].strip().startswith("|"):
                cruda = lineas[i].strip().strip("|")
                if not re.match(r"^[\s:|-]+$", cruda):
                    filas.append([celda.strip() for celda in cruda.split("|")])
                i += 1
            i -= 1
            if filas:
                c.tabla(filas)
        elif re.match(r"^\d+\.\s+", desnuda):
            volcar_parrafo()
            ordenada = True
            items.append(re.sub(r"^\d+\.\s+", "", desnuda))
        elif re.match(r"^[-*]\s+", desnuda):
            volcar_parrafo()
            items.append(re.sub(r"^[-*]\s+", "", desnuda))
        elif desnuda == "---":
            volcar_parrafo(); volcar_lista()
        elif not desnuda:
            volcar_parrafo(); volcar_lista()
        elif desnuda.startswith("*") and desnuda.endswith("*") and len(desnuda) > 2 \
                and not desnuda.startswith("**"):
            volcar_parrafo(); volcar_lista()
            c.historia.append(Spacer(1, 10))
            c.parrafo(desnuda.strip("*"), "pie_doc")
        else:
            if items:
                items[-1] += " " + desnuda
            else:
                buffer_parrafo.append(desnuda)
        i += 1

    volcar_parrafo(); volcar_lista()
    return c.historia


# ---------------------------------------------------------------- portada
def portada(estilos, ancho, md):
    encabezado = md.split("\n## Contenido")[0]
    indice = []
    for linea in md.split("\n"):
        m = re.match(r"^(\d+)\.\s+(.+)$", linea.strip())
        if m and len(indice) < 13:
            indice.append((m.group(1), m.group(2)))

    h = [Spacer(1, 62)]
    h.append(Paragraph("CIENCIA DE DATOS · UTN FRM · 2026",
                       ParagraphStyle("k", fontName="Cuerpo-Bold", fontSize=8.6,
                                      leading=12, textColor=ACENTO)))
    h.append(Spacer(1, 14))
    h.append(Paragraph("Pipeline de Datos:<br/>Fichajes y Coeficientes UEFA",
                       estilos["portada_titulo"]))
    h.append(_Regla(ancho))
    h.append(Spacer(1, 14))
    h.append(Paragraph(
        "Cómo funciona el proyecto — arquitectura, flujo de datos y los "
        "cambios de esta versión.", estilos["portada_bajada"]))

    filas = [[f"{n}.", t] for n, t in indice]
    if filas:
        t = Table(filas, colWidths=[22, ancho - 22])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Mono"),
            ("FONTSIZE", (0, 0), (0, -1), 8.4),
            ("TEXTCOLOR", (0, 0), (0, -1), TINTA_TENUE),
            ("FONTNAME", (1, 0), (1, -1), "Cuerpo"),
            ("FONTSIZE", (1, 0), (1, -1), 9.6),
            ("TEXTCOLOR", (1, 0), (1, -1), TINTA),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        h.append(Paragraph("Contenido", estilos["h4"]))
        h.append(t)

    h.append(Spacer(1, 26))
    h.append(Paragraph(
        "Repositorio: <b>airflow-proyecto</b> · DAG: <b>pipeline_fichajes</b><br/>"
        "Apache Airflow 3.3 sobre Astro Runtime", estilos["portada_pie"]))
    h.append(PageBreak())
    return h


# ------------------------------------------------------------- documento
def pie_de_pagina(canv, doc):
    canv.saveState()
    canv.setStrokeColor(LINEA)
    canv.setLineWidth(0.6)
    y = 14 * mm
    canv.line(doc.leftMargin, y + 9, doc.leftMargin + doc.width, y + 9)
    canv.setFont("Cuerpo", 7.6)
    canv.setFillColor(TINTA_TENUE)
    if doc.page > 1:
        canv.drawString(doc.leftMargin, y,
                        "Pipeline de fichajes · Ciencia de Datos · UTN FRM 2026")
        canv.drawRightString(doc.leftMargin + doc.width, y, str(doc.page))
    canv.restoreState()


def main():
    registrar_fuentes()
    estilos = construir_estilos()
    md = ENTRADA.read_text(encoding="utf-8")

    doc = BaseDocTemplate(
        str(SALIDA), pagesize=A4,
        leftMargin=21 * mm, rightMargin=19 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title="Pipeline de Datos: Fichajes y Coeficientes UEFA",
        author="Ciencia de Datos · UTN FRM 2026",
        subject="Documentación del pipeline de fichajes")
    marco = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="normal", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="pag", frames=[marco],
                                       onPage=pie_de_pagina)])

    historia = portada(estilos, doc.width, md)
    historia += construir(md, estilos, doc.width)
    doc.build(historia)
    print(f"PDF generado: {SALIDA}  ({SALIDA.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    sys.exit(main())
