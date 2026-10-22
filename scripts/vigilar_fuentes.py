#!/usr/bin/env python3
"""Vigila las fuentes oficiales registradas en data/fuentes.json.

Usa concurrencia limitada y una caché de robots.txt por dominio para que una fuente
lenta no bloquee la publicación completa. Nunca infiere por sí solo que una ayuda esté abierta.
"""
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import threading
import datetime as dt
import urllib.request
import urllib.error
import urllib.robotparser
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from actualizar import leer, escribir  # noqa: E402

UA = "Subvenly/1.0 (+seguimiento de fuentes oficiales)"
MAX_TEXTO = 12000
MAX_BYTES = 1_000_000
TIMEOUT_ROBOTS = 6
TIMEOUT_PAGINA = 12
MAX_WORKERS = 8

_ROBOTS_CACHE = {}
_HOST_LOCKS = {}
_HOST_LOCKS_GUARD = threading.Lock()


def bloqueo_host(url):
    p = urllib.parse.urlparse(url)
    origen = "{}://{}".format(p.scheme, p.netloc)
    with _HOST_LOCKS_GUARD:
        return _HOST_LOCKS.setdefault(origen, threading.Lock())


def permitido(url):
    p = urllib.parse.urlparse(url)
    origen = "{}://{}".format(p.scheme, p.netloc)
    lock = bloqueo_host(url)
    with lock:
        if origen not in _ROBOTS_CACHE:
            rp = urllib.robotparser.RobotFileParser()
            try:
                req = urllib.request.Request(
                    origen + "/robots.txt",
                    headers={"User-Agent": UA},
                )
                with urllib.request.urlopen(req, timeout=TIMEOUT_ROBOTS) as respuesta:
                    contenido = respuesta.read(200_000).decode("utf-8", "ignore")
                rp.parse(contenido.splitlines())
                _ROBOTS_CACHE[origen] = rp
            except urllib.error.HTTPError:
                # Mantiene el comportamiento anterior para robots.txt no disponible por HTTP.
                _ROBOTS_CACHE[origen] = True
            except Exception:
                # Si no se puede comprobar robots.txt por un error de red, no rastrear esa URL.
                _ROBOTS_CACHE[origen] = False
        regla = _ROBOTS_CACHE[origen]
    if regla is True:
        return True
    if regla is False:
        return False
    return regla.can_fetch(UA, url)


def obtener(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept-Language": "es,ca;q=0.9,en;q=0.7"},
    )
    # Serializa las peticiones al mismo host; dominios distintos se procesan en paralelo.
    with bloqueo_host(url):
        with urllib.request.urlopen(req, timeout=TIMEOUT_PAGINA) as respuesta:
            raw = respuesta.read(MAX_BYTES)
            tipo = respuesta.headers.get("Content-Type", "")
    if "text/html" in tipo or not tipo:
        texto = raw.decode("utf-8", "ignore")
        texto = re.sub(
            r"(?is)<script[^>]*>.*?</script>|<style[^>]*>.*?</style>|<noscript[^>]*>.*?</noscript>|<nav[^>]*>.*?</nav>|<header[^>]*>.*?</header>|<footer[^>]*>.*?</footer>",
            " ",
            texto,
        )
        texto = re.sub(r"(?s)<[^>]+>", " ", texto)
        texto = " ".join(texto.split())[:MAX_TEXTO]
    else:
        # Para documentos no HTML se registra una huella binaria, sin afirmar que se ha leído su contenido.
        texto = "DOCUMENTO_SHA256:" + hashlib.sha256(raw).hexdigest()
    return texto


def procesar_fuente(fuente, previo, hoy):
    url = fuente.get("url", "")
    sid = str(fuente.get("id") or url)
    ant = previo.get(sid, {})
    cambios = list(ant.get("cambios", []))
    if not url.startswith("https://"):
        return sid, {"estado": "configuracion_invalida", "comprobado": hoy, "url": url, "cambios": cambios[-10:]}, "{}: configuración inválida".format(sid)
    if not permitido(url):
        registro = {
            "estado": "cambio" if ant.get("estado") == "cambio" else "no_verificable",
            "comprobado": hoy,
            "url": url,
            "hash": ant.get("hash", ""),
            "cambios": cambios[-10:],
        }
        return sid, registro, "{}: no_verificable (robots.txt o acceso)".format(sid)
    try:
        actual = obtener(url)
        huella = hashlib.sha256(actual.encode("utf-8")).hexdigest()
        anterior = ant.get("texto", "")
        if not anterior:
            estado = "inicializado"
        elif ant.get("hash") != huella:
            estado = "cambio"
            cambios.append({
                "fecha": hoy,
                "antes_hash": ant.get("hash", ""),
                "despues_hash": huella,
                "antes": anterior[:800],
                "despues": actual[:800],
            })
        elif ant.get("estado") == "cambio":
            estado = "cambio"  # El aviso permanece hasta que se revise la fuente.
        else:
            estado = "igual"
        registro = {
            "estado": estado,
            "comprobado": hoy,
            "url": url,
            "hash": huella,
            "texto": actual,
            "cambios": cambios[-10:],
        }
        return sid, registro, "{}: {}".format(sid, estado)
    except Exception as exc:
        registro = {
            "estado": "cambio" if ant.get("estado") == "cambio" else "no_verificable",
            "comprobado": hoy,
            "url": url,
            "hash": ant.get("hash", ""),
            "texto": ant.get("texto", ""),
            "cambios": cambios[-10:],
            "error": str(exc)[:300],
        }
        return sid, registro, "{}: no_verificable ({})".format(sid, exc)


def main():
    hoy = dt.date.today().isoformat()
    registro = leer("fuentes.json", {"fuentes": []})
    previo = leer("vigilancia_fuentes.json", {}).get("fuentes", {})
    resultado = {}
    tareas = []
    vistos = set()
    for fuente in registro.get("fuentes", []):
        if not fuente.get("monitor", True):
            continue
        url = fuente.get("url", "")
        sid = str(fuente.get("id") or url)
        if not url.startswith("https://") or url in vistos:
            resultado[sid] = {
                "estado": "configuracion_invalida",
                "comprobado": hoy,
                "url": url,
            }
            continue
        vistos.add(url)
        tareas.append(fuente)

    # Concurrencia limitada por dominio: un servidor lento no paraliza las 80+ fuentes.
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futuros = {
            executor.submit(procesar_fuente, fuente, previo, hoy): str(fuente.get("id") or fuente.get("url", ""))
            for fuente in tareas
        }
        for futuro in concurrent.futures.as_completed(futuros):
            sid = futuros[futuro]
            try:
                sid, dato, mensaje = futuro.result()
            except Exception as exc:
                ant = previo.get(sid, {})
                dato = {
                    "estado": "cambio" if ant.get("estado") == "cambio" else "no_verificable",
                    "comprobado": hoy,
                    "url": ant.get("url", ""),
                    "hash": ant.get("hash", ""),
                    "texto": ant.get("texto", ""),
                    "cambios": ant.get("cambios", [])[-10:],
                    "error": str(exc)[:300],
                }
                mensaje = "{}: no_verificable ({})".format(sid, exc)
            resultado[sid] = dato
            print("  " + mensaje)

    escribir("vigilancia_fuentes.json", {"actualizado": hoy, "fuentes": resultado}, compacto=True)
    print("Vigilancia completada: {} fuentes.".format(len(resultado)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("ERROR:", exc)
        sys.exit(1)
