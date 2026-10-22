#!/usr/bin/env python3
"""Importa novedades locales desde el RSS público del CIDO (Diputació de Barcelona).

El RSS es una fuente de descubrimiento, no una certificación de que la convocatoria
siga abierta. Por eso los registros importados quedan como "por verificar" y enlazan
a la ficha original del CIDO.
"""
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "..", "data")
FEED = "https://cido.diba.cat/rss/subvencions/subvencions-ens-locals"
FEEDS = [
    ("subvencions-ens-locals", FEED, "Local"),
    ("beques", "https://cido.diba.cat/rss/subvencions/beques", "Otros"),
]
RETENCION_DIAS = 90
NUEVA_DIAS = 7
USER_AGENT = "Subvenly/1.0 (+https://papelegruba-ppb.github.io/Subvenly/; ayuda pública y reutilización de datos)"


def descargar_rss(url, intentos=3):
    """Descarga el RSS con reintentos breves ante fallos de red transitorios."""
    ultimo_error = None
    for intento in range(intentos):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"},
        )
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                contenido = response.read(8 * 1024 * 1024 + 1)
            if len(contenido) > 8 * 1024 * 1024:
                raise ValueError("El RSS supera el límite de 8 MiB.")
            return contenido
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            ultimo_error = exc
            if intento + 1 < intentos:
                time.sleep(2 * (intento + 1))
    raise RuntimeError("No se pudo descargar el RSS tras {} intentos: {}".format(intentos, ultimo_error))


def limpiar(valor):
    valor = html.unescape(str(valor or ""))
    valor = re.sub(r"<!\[CDATA\[|\]\]>", " ", valor)
    valor = re.sub(r"<[^>]+>", " ", valor)
    return re.sub(r"\s+", " ", valor).strip()


def campo(elemento, nombre):
    for hijo in list(elemento):
        if hijo.tag.rsplit("}", 1)[-1].lower() == nombre.lower():
            return "".join(hijo.itertext()).strip()
    return ""


def fecha_iso(valor, hoy=None):
    hoy = hoy or dt.date.today()
    valor = limpiar(valor)
    if not valor:
        return hoy.isoformat()
    try:
        parsed = email.utils.parsedate_to_datetime(valor)
        if parsed:
            return parsed.date().isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", valor)
    if match:
        try:
            return dt.date(int(match.group(3)), int(match.group(2)), int(match.group(1))).isoformat()
        except ValueError:
            pass
    try:
        return dt.date.fromisoformat(valor[:10]).isoformat()
    except ValueError:
        return hoy.isoformat()


def referencia(link, titulo):
    match = re.search(r"/subvencions/(\d+)(?:/|$)", link)
    if match:
        return "cido-" + match.group(1)
    return "cido-" + hashlib.sha256((link + "|" + titulo).encode("utf-8")).hexdigest()[:20]


def nivel_entidad(organo, defecto="Otros"):
    """Clasificación prudente por nombre del organismo, sin inferir elegibilidad."""
    k = limpiar(organo).casefold()
    if any(x in k for x in ("ajuntament", "ayuntamiento", "diputació", "diputacion",
                            "consell comarcal", "mancomunitat", "ens local", "entidad local")):
        return "Local"
    if any(x in k for x in ("generalitat", "agaur", "govern de la generalitat", "governo autonómico")):
        return "Autonómica"
    if any(x in k for x in ("ministerio", "ministeri", "sepe", "imserso", "administración general del estado")):
        return "Estatal"
    if any(x in k for x in ("unión europea", "union europea", "comisión europea", "comision europea", "european commission")):
        return "Unión Europea"
    return defecto


def territorio_entidad(nivel):
    if nivel in ("Local", "Autonómica"):
        return "Cataluña"
    if nivel == "Estatal":
        return "España"
    if nivel == "Unión Europea":
        return "Unión Europea"
    return "Cataluña"


def parsear_rss(contenido, hoy=None, feed=FEED, nivel_defecto="Local"):
    """Convierte RSS/Atom en registros normalizados; no hace peticiones de red."""
    hoy = hoy or dt.date.today()
    root = ET.fromstring(contenido)
    nodos = [e for e in root.iter() if e.tag.rsplit("}", 1)[-1].lower() in ("item", "entry")]
    salida, vistos = [], set()
    for item in nodos:
        titulo = limpiar(campo(item, "title"))
        link = limpiar(campo(item, "link"))
        if not link:
            for hijo in list(item):
                if hijo.tag.rsplit("}", 1)[-1].lower() == "link":
                    link = limpiar(hijo.attrib.get("href", ""))
                    if link:
                        break
        link = urllib.parse.urljoin(feed, link)
        if not link.startswith("https://cido.diba.cat/subvencions/"):
            continue
        descripcion = limpiar(campo(item, "description") or campo(item, "encoded") or campo(item, "summary") or campo(item, "content"))
        if not titulo or titulo.lower().startswith("data de publicacio"):
            # Fallback: usa el último segmento del enlace, sin inventar un título si no hay slug.
            slug = urllib.parse.urlparse(link).path.rstrip("/").split("/")[-1]
            titulo = limpiar(urllib.parse.unquote(slug).replace("-", " ")) if slug and not slug.isdigit() else ""
        if not titulo:
            continue
        ident = referencia(link, titulo)
        if ident in vistos:
            continue
        vistos.add(ident)
        pub = campo(item, "pubDate") or campo(item, "published") or campo(item, "updated")
        if not pub:
            match = re.search(r"Data de publicació:\s*([^;|]+)", descripcion, re.I)
            pub = match.group(1) if match else ""
        org = ""
        match = re.search(r"(?:Ens|Entidad|Organisme)\s*:\s*(.+?)(?=\s+(?:Número de referència|Numero de referencia|Data de publicació)\s*:|$)", descripcion, re.I)
        if match:
            org = limpiar(match.group(1))
        ref = ""
        match = re.search(r"(?:Número de referència|Numero de referencia)\s*:\s*([\w.-]+)", descripcion, re.I)
        if match:
            ref = match.group(1)
        resumen = re.sub(r"Data de publicació:\s*[^.]+?(?=\s+Ens\s*:|$)", " ", descripcion, flags=re.I)
        resumen = re.sub(r"Ens\s*:\s*.+?(?=\s+Número de referència\s*:|$)", " ", resumen, flags=re.I)
        resumen = re.sub(r"(?:Número de referència|Numero de referencia)\s*:\s*[\w.-]+", " ", resumen, flags=re.I)
        resumen = limpiar(resumen)
        nivel = nivel_entidad(org, nivel_defecto)
        territorio = territorio_entidad(nivel)
        salida.append({
            "id": ident,
            "fuente": "CIDO",
            "fuenteUrl": feed,
            "categoriaFuente": "becas" if feed.endswith("/beques") else "subvenciones locales",
            "referenciaFuente": ref,
            "titulo": titulo[:300],
            "organo": org or "Entidad local de Cataluña",
            "n1": nivel,
            "n2": territorio,
            "n3": org,
            "ambito": nivel,
            "territorio": territorio,
            "fecha": fecha_iso(pub, hoy),
            "fechaTipo": "publicada",
            "link": link,
            "estadoConvocatoria": "por verificar",
            "finalidad": (resumen or descripcion or titulo)[:900],
            "visto": hoy.isoformat(),
            "licenciaDatos": "CC BY · atribución al CIDO/Diputación de Barcelona",
        })
    return salida


def leer_json(nombre, defecto):
    try:
        with open(os.path.join(DATA, nombre), encoding="utf-8") as archivo:
            return json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return defecto


def escribir_json(nombre, valor):
    ruta = os.path.join(DATA, nombre)
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(valor, archivo, ensure_ascii=False, separators=(",", ":"))
        archivo.write("\n")
    os.replace(temporal, ruta)


def combinar(datos, nuevos, hoy=None):
    hoy = hoy or dt.date.today()
    previos = datos.get("items", [])
    limite = (hoy - dt.timedelta(days=RETENCION_DIAS)).isoformat()
    nueva_lim = (hoy - dt.timedelta(days=NUEVA_DIAS)).isoformat()
    mapa = {str(x.get("id")): x for x in previos if str(x.get("id", "")).startswith("cido-")}
    altas = 0
    for nuevo in nuevos:
        ident = str(nuevo["id"])
        anterior = mapa.get(ident)
        if anterior:
            visto = anterior.get("visto") or nuevo["visto"]
            anterior.update(nuevo)
            anterior["visto"] = visto
            mapa[ident] = anterior
        else:
            mapa[ident] = nuevo
            altas += 1
    cido = []
    for item in mapa.values():
        fecha = str(item.get("fecha") or "")
        if fecha >= limite or (item.get("plazo_fin") and item["plazo_fin"] >= hoy.isoformat()):
            item["nueva"] = str(item.get("visto") or "") >= nueva_lim
            cido.append(item)
    no_cido = [x for x in previos if not str(x.get("id", "")).startswith("cido-")]
    combinado = no_cido + cido
    combinado.sort(key=lambda x: (str(x.get("fecha") or ""), str(x.get("id") or "")), reverse=True)
    salida = dict(datos)
    salida["items"] = combinado
    return salida, {"recibidas": len(nuevos), "nuevas": altas, "conservadasCIDO": len(cido), "total": len(combinado)}


def main():
    hoy = dt.date.today()
    diagnostico = {"fecha": hoy.isoformat(), "fuentes": [x[0] for x in FEEDS], "estado": "error"}
    nuevos, errores, por_fuente = [], [], {}
    for nombre, url, nivel_defecto in FEEDS:
        try:
            contenido = descargar_rss(url)
            registros = parsear_rss(contenido, hoy, feed=url, nivel_defecto=nivel_defecto)
            if not registros:
                raise ValueError("El RSS no devolvió registros reconocibles.")
            nuevos.extend(registros)
            por_fuente[nombre] = len(registros)
        except Exception as exc:
            errores.append("{}: {}".format(nombre, str(exc)[:400]))
    if not nuevos:
        raise RuntimeError("Ningún RSS del CIDO devolvió registros. " + "; ".join(errores))
    datos = leer_json("novedades.json", {"items": []})
    combinado, resumen = combinar(datos, nuevos, hoy)
    escribir_json("novedades.json", combinado)
    diagnostico.update(resumen)
    diagnostico["porFuente"] = por_fuente
    diagnostico["errores"] = errores
    diagnostico["estado"] = "parcial" if errores else "correcta"
    diagnostico["muestra"] = [{"id": x["id"], "titulo": x["titulo"], "link": x["link"], "fuenteUrl": x["fuenteUrl"]} for x in nuevos[:5]]
    escribir_json("_diagnostico_cido.json", diagnostico)
    print("CIDO RSS: {} recibidas, {} nuevas, {} conservadas.".format(resumen["recibidas"], resumen["nuevas"], resumen["conservadasCIDO"]))
    if errores:
        print("Aviso CIDO: algunas fuentes fallaron: " + "; ".join(errores), file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())