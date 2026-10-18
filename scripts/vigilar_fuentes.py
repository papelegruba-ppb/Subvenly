#!/usr/bin/env python3
"""Vigila las fuentes oficiales registradas en data/fuentes.json.
Detecta cambios de contenido para revisión; nunca infiere por sí solo que una ayuda está abierta.
Respeta robots.txt y usa solo la biblioteca estándar.
"""
import hashlib, json, os, re, sys, time, datetime as dt
import urllib.request, urllib.error, urllib.robotparser, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from actualizar import leer, escribir  # noqa: E402

UA = "Subvenly/1.0 (+seguimiento de fuentes oficiales)"
MAX_TEXTO = 12000

def permitido(url):
    p = urllib.parse.urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        req = urllib.request.Request(f"{p.scheme}://{p.netloc}/robots.txt", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            rp.parse(r.read().decode("utf-8", "ignore").splitlines())
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False
    return rp.can_fetch(UA, url)

def obtener(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es,ca;q=0.9,en;q=0.7"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read(2_000_000)
        tipo = r.headers.get("Content-Type", "")
    if "text/html" in tipo or not tipo:
        text = raw.decode("utf-8", "ignore")
        text = re.sub(r"(?is)<(script|style|noscript|nav|header|footer)[^>]*>.*?</\\1>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = " ".join(text.split())[:MAX_TEXTO]
    else:
        # Para documentos no HTML se registra una huella binaria, sin afirmar que se ha leído su contenido.
        text = "DOCUMENTO_SHA256:" + hashlib.sha256(raw).hexdigest()
    return text

def main():
    hoy = dt.date.today().isoformat()
    registro = leer("fuentes.json", {"fuentes": []})
    previo = leer("vigilancia_fuentes.json", {}).get("fuentes", {})
    resultado = {}
    vistos = set()
    for fuente in registro.get("fuentes", []):
        if not fuente.get("monitor", True):
            continue
        url = fuente.get("url", "")
        sid = str(fuente.get("id") or url)
        if not url.startswith("https://") or url in vistos:
            resultado[sid] = {"estado": "configuracion_invalida", "comprobado": hoy, "url": url}
            continue
        vistos.add(url)
        ant = previo.get(sid, {})
        cambios = list(ant.get("cambios", []))
        if not permitido(url):
            resultado[sid] = {"estado": "no_verificable", "comprobado": hoy, "url": url, "hash": ant.get("hash", ""), "cambios": cambios[-10:]}
            print(f"  {sid}: no_verificable (robots.txt o acceso)")
            continue
        try:
            actual = obtener(url)
            huella = hashlib.sha256(actual.encode("utf-8")).hexdigest()
            anterior = ant.get("texto", "")
            if not anterior:
                estado = "inicializado"
            elif ant.get("hash") != huella:
                estado = "cambio"
                cambios.append({"fecha": hoy, "antes_hash": ant.get("hash", ""), "despues_hash": huella,
                                "antes": anterior[:800], "despues": actual[:800]})
            elif ant.get("estado") == "cambio":
                estado = "cambio"  # El aviso permanece hasta que se revise la fuente.
            else:
                estado = "igual"
            resultado[sid] = {"estado": estado, "comprobado": hoy, "url": url, "hash": huella,
                              "texto": actual, "cambios": cambios[-10:]}
            print(f"  {sid}: {estado}")
            time.sleep(0.5)
        except Exception as exc:
            resultado[sid] = {"estado": "no_verificable", "comprobado": hoy, "url": url,
                              "hash": ant.get("hash", ""), "texto": ant.get("texto", ""), "cambios": cambios[-10:],
                              "error": str(exc)[:300]}
            print(f"  {sid}: no_verificable ({exc})")
    escribir("vigilancia_fuentes.json", {"actualizado": hoy, "fuentes": resultado}, compacto=True)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("ERROR:", exc)
        sys.exit(1)
