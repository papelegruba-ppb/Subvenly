#!/usr/bin/env python3
"""Vigila las páginas oficiales de las fichas de tipo «Crédito» y avisa si parecen haber cambiado.
No reescribe las condiciones: marca la ficha para que se revise. Respeta robots.txt.
Escribe data/vigilancia.json. Solo biblioteca estándar.
"""
import json, os, re, sys, time, hashlib, datetime as dt
import urllib.request, urllib.error, urllib.robotparser, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from actualizar import leer, escribir  # noqa: E402

UA = "Subvenly/1.0 (+vigilancia de condiciones)"
UMBRAL_PARECIDO = 0.90      # por debajo de este parecido entre textos se considera que la página cambió
MAX_TEXTO = 12000

def permitido(url):
    p = urllib.parse.urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        req = urllib.request.Request(f"{p.scheme}://{p.netloc}/robots.txt", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            rp.parse(r.read().decode("utf-8", "ignore").splitlines())
    except urllib.error.HTTPError:
        return True                   # sin robots.txt: se permite
    except Exception:
        return False
    return rp.can_fetch(UA, url)

def texto(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es"})
    with urllib.request.urlopen(req, timeout=40) as r:
        h = r.read().decode(r.headers.get_content_charset() or "utf-8", "ignore")
    h = re.sub(r"(?is)<(script|style|noscript|nav|header|footer)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return " ".join(h.split())[:MAX_TEXTO]

def cifras(t):
    return set(re.findall(r"\d[\d.,]*\s?(?:€|%|euros|millones)", t, flags=re.I))

def parecido(a, b):
    def sh(t):
        w = t.lower().split()
        return {" ".join(w[i:i + 4]) for i in range(max(1, len(w) - 3))}
    x, y = sh(a), sh(b)
    return len(x & y) / len(x | y) if (x | y) else 1.0

def cambio(antes, ahora):
    return cifras(antes) != cifras(ahora) or parecido(antes, ahora) < UMBRAL_PARECIDO

def urls(f):
    out = []
    if f.get("link") and str(f["link"]).startswith("http"):
        out.append(f["link"])
    out += [u for _, u in f.get("links", []) if str(u).startswith("http")]
    return out

def main():
    hoy = dt.date.today().isoformat()
    ruta = sys.argv[sys.argv.index("--fichas") + 1] if "--fichas" in sys.argv else None
    fichas = json.load(open(ruta, encoding="utf-8")) if ruta else leer("fichas.json", [])
    previo = leer("vigilancia.json", {}).get("fichas", {})
    res = {}
    for f in fichas:
        if f.get("tipo") != "Crédito":
            continue
        fid, ant = str(f["id"]), previo.get(str(f["id"]), {})
        snaps = ant.get("snapshots", {})
        estado, desde, nuevos = "igual", ant.get("desde", ""), {}
        for u in urls(f):
            try:
                if not permitido(u):
                    nuevos[u] = {"texto": snaps.get(u, {}).get("texto", ""), "nota": "no_verificable"}
                    continue
                t = texto(u); time.sleep(1)
            except Exception as e:
                print(f"  {fid}: no se pudo leer {u}: {e}")
                nuevos[u] = {"texto": snaps.get(u, {}).get("texto", ""), "nota": "error"}
                continue
            nuevos[u] = {"texto": t, "nota": ""}
            if u in snaps and snaps[u].get("texto") and cambio(snaps[u]["texto"], t):
                estado, desde = "cambio", hoy
        if estado == "igual" and ant.get("estado") == "cambio" and ant.get("desde"):
            estado = "cambio"          # el aviso se mantiene hasta que lo revises y lo quites
        if not nuevos or all(v["nota"] for v in nuevos.values()):
            estado = "no_verificable"
        res[fid] = {"estado": estado, "desde": desde, "comprobado": hoy, "snapshots": nuevos}
        print(f"  ficha {fid} «{f.get('titulo','')[:40]}»: {estado}")
    escribir("vigilancia.json", {"actualizado": hoy, "fichas": res}, compacto=True)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR:", e); sys.exit(1)
