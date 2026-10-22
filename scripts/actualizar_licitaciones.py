#!/usr/bin/env python3
"""Busca licitaciones ABIERTAS en la Plataforma de Contratación del Sector Público (datos abiertos)
y las guarda en data/licitaciones.json. Solo biblioteca estándar.

Fuentes (ficheros Atom públicos, hasta 500 entradas por fichero, enlazados con rel="next"):
  - licitaciones de los perfiles de contratante de la Plataforma (sin contratos menores)
  - licitaciones de plataformas agregadas (entidades que publican en otra plataforma)
Los contratos menores no se incluyen: sus datos se publican una vez adjudicados.

Uso:
  python scripts/actualizar_licitaciones.py
  python scripts/actualizar_licitaciones.py --fixture ejemplo.atom   # prueba sin red
"""
import json, os, sys, time, datetime as dt
import urllib.request, urllib.error
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from actualizar import leer, escribir, iso  # noqa: E402

FEEDS = [
    ("perfiles", "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom"),
    ("agregadas", "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044/PlataformasAgregadasSinMenores.atom"),
]
# ---------- AJUSTES ----------
DIAS_PRIMERA_VEZ = 7     # cuántos días atrás mira la primera vez
MARGEN_DIAS = 1
MAX_FICHEROS = 4        # tope de ficheros de 500 entradas por fuente y ejecución
MAX_ITEMS = 4000
SIN_PLAZO_DIAS = 30      # si una licitación no indica fecha límite, se conserva este tiempo
TIPOS = {"1": "Suministros", "2": "Servicios", "3": "Obras", "21": "Gestión de servicios públicos",
         "22": "Concesión de servicios", "31": "Concesión de obras", "32": "Concesión de obras públicas"}
# -----------------------------

def local(tag):
    return tag.rsplit("}", 1)[-1]

def hijo(e, nombre):
    if e is not None:
        for c in e:
            if local(c.tag) == nombre:
                return c
    return None

def desc(e, nombre):
    if e is not None:
        for x in e.iter():
            if local(x.tag) == nombre:
                return x
    return None

def txt(e):
    return " ".join((e.text or "").split()) if e is not None else ""

def leer_url(url, intentos=1):
    req = urllib.request.Request(url, headers={"User-Agent": "Subvenly/1.0 (+actualizacion nocturna)"})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  intento {i+1}/{intentos} fallido: {e}")
            if i + 1 < intentos: time.sleep(1)
    raise RuntimeError("No se pudo descargar " + url)

def importe(v):
    try:
        return round(float(v))
    except (TypeError, ValueError):
        return None

def entrada(e, hoy):
    estado = txt(desc(e, "ContractFolderStatusCode"))
    if estado != "PUB":           # solo las que están en plazo de presentación de ofertas
        return None
    proj = desc(e, "ProcurementProject")
    lugar = desc(proj, "RealizedLocation")
    parte = desc(desc(e, "LocatedContractingParty"), "PartyName")
    presup = desc(proj, "BudgetAmount")
    cierre = iso(txt(desc(desc(e, "TenderSubmissionDeadlinePeriod"), "EndDate")))
    if cierre and cierre < hoy.isoformat():
        return None
    cpv = txt(desc(desc(proj, "RequiredCommodityClassification"), "ItemClassificationCode"))
    enlace = ""
    for c in e:
        if local(c.tag) == "link" and c.get("href"):
            enlace = c.get("href"); break
    ident = txt(desc(e, "ContractFolderID")) or txt(hijo(e, "id"))
    titulo = txt(hijo(proj, "Name")) or txt(hijo(e, "title"))
    if not ident or not titulo:
        return None
    return {"id": ident, "titulo": titulo[:300], "organo": txt(desc(parte, "Name")),
            "territorio": txt(desc(lugar, "CountrySubentity")), "nuts": txt(desc(lugar, "CountrySubentityCode")),
            "tipo": TIPOS.get(txt(hijo(proj, "TypeCode")), "Otros"), "cpv": cpv[:8],
            "presupuesto": importe(txt(desc(presup, "TaxExclusiveAmount")) or txt(desc(presup, "TotalAmount"))),
            "cierre": cierre, "link": enlace, "visto": hoy.isoformat(), "actualizada": iso(txt(hijo(e, "updated")))}

def recorrer(url, corte, hoy, raiz_local=None):
    """Sigue los enlaces rel="next" hasta llegar a entradas anteriores a 'corte'."""
    out, n = [], 0
    while url and n < MAX_FICHEROS:
        print(f"  fichero {n+1}")
        raiz = ET.fromstring(raiz_local if raiz_local is not None else leer_url(url))
        entradas = [x for x in raiz if local(x.tag) == "entry"]
        for e in entradas:
            r = entrada(e, hoy)
            if r:
                out.append(r)
        ultima = iso(txt(hijo(entradas[-1], "updated"))) if entradas else ""
        sig = next((c.get("href") for c in raiz if local(c.tag) == "link" and c.get("rel") == "next"), "")
        n += 1
        if raiz_local is not None or not entradas or (ultima and ultima < corte):
            break
        url = sig
    return out, n

def main():
    hoy = dt.date.today()
    estado = leer("estado_licitaciones.json", {})
    ultima = iso(estado.get("ultima"))
    corte = ((dt.date.fromisoformat(ultima) - dt.timedelta(days=MARGEN_DIAS)) if ultima else hoy - dt.timedelta(days=DIAS_PRIMERA_VEZ)).isoformat()
    nuevas, ficheros, fuentes_ok, errores = [], 0, [], []
    if "--fixture" in sys.argv:
        datos = open(sys.argv[sys.argv.index("--fixture") + 1], "rb").read()
        r, n = recorrer("fixture", corte, hoy, raiz_local=datos)
        nuevas += r; ficheros += n; fuentes_ok.append("fixture")
    else:
        for nombre, url in FEEDS:
            print(f"Fuente '{nombre}' desde {corte}")
            try:
                r, n = recorrer(url, corte, hoy)
                nuevas += r; ficheros += n; fuentes_ok.append(nombre)
                print(f"  {nombre}: correcta ({n} ficheros, {len(r)} licitaciones)")
            except Exception as exc:
                errores.append({"fuente": nombre, "error": str(exc)[:500]})
                print(f"  {nombre}: ERROR: {exc}")
    print(f"Ficheros leídos: {ficheros} · fuentes correctas: {len(fuentes_ok)} · errores: {len(errores)} · licitaciones encontradas: {len(nuevas)}")
    if not ficheros:
        escribir("_diagnostico_licitaciones.json", {"fecha": hoy.isoformat(), "ficheros": 0, "encontradas": 0,
            "guardadas": len(leer("licitaciones.json", {"items": []}).get("items", [])), "fuentes_correctas": fuentes_ok,
            "errores": errores, "estado": "fallida", "ejemplo": None})
        return 1
    previo_doc = leer("licitaciones.json", {"items": []})
    previo = {i["id"]: i for i in previo_doc.get("items", [])}
    for r in nuevas:                       # las entradas vienen de la más reciente a la más antigua
        if r["id"] not in previo or (r["actualizada"] or "") >= (previo[r["id"]].get("actualizada") or ""):
            r["visto"] = previo.get(r["id"], r).get("visto", r["visto"])
            previo[r["id"]] = r
    lim_sin_plazo = (hoy - dt.timedelta(days=SIN_PLAZO_DIAS)).isoformat()
    items = [i for i in previo.values() if (i["cierre"] and i["cierre"] >= hoy.isoformat()) or (not i["cierre"] and i["visto"] >= lim_sin_plazo)]
    items.sort(key=lambda i: (i["cierre"] or "9999", i["id"]))
    estado_actualizacion = "completa" if not errores else "parcial"
    escribir("_diagnostico_licitaciones.json", {"fecha": hoy.isoformat(), "ficheros": ficheros, "encontradas": len(nuevas),
        "guardadas": min(len(items), MAX_ITEMS), "fuentes_correctas": fuentes_ok, "errores": errores,
        "estado": estado_actualizacion, "ejemplo": nuevas[0] if nuevas else None})
    escribir("licitaciones.json", {"actualizado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "estadoActualizacion": estado_actualizacion, "fuentesConError": [e["fuente"] for e in errores],
        "items": items[:MAX_ITEMS]}, compacto=True)
    # No avanzar el punto de control si alguna fuente falló: el siguiente ciclo vuelve a cubrir el periodo.
    if not errores:
        escribir("estado_licitaciones.json", {"ultima": hoy.isoformat(), "fuentes": fuentes_ok})
    print(f"Guardadas {min(len(items), MAX_ITEMS)} licitaciones abiertas; estado de actualización: {estado_actualizacion}.")
    return 2 if errores else 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR:", e)
        sys.exit(1)
