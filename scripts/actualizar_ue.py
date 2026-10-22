#!/usr/bin/env python3
"""Busca convocatorias abiertas o próximas de la Unión Europea (Portal Funding & Tenders)
orientadas a pymes, startups y emprendedores, y las añade a data/novedades.json.
Usa la API de búsqueda pública del portal (sin clave personal). Solo biblioteca estándar.

Uso:
  python scripts/actualizar_ue.py
  python scripts/actualizar_ue.py --fixture ejemplo.json   # prueba sin red
"""
import json, os, sys, time, uuid, datetime as dt
import urllib.request, urllib.parse, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from actualizar import leer, escribir, iso, RETENCION_DIAS, NUEVA_DIAS, MAX_ITEMS  # noqa: E402

API = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
TOPIC = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{}"
# ---------- AJUSTES ----------
BUSQUEDAS = [
    "SME", "small and medium-sized enterprises", "start-up", "entrepreneur", "self-employed",
    "digitalisation SMEs", "research and innovation", "education and training", "culture and creative industries",
    "environment and climate", "renewable energy", "agriculture and rural development", "social inclusion",
    "youth", "civil society organisations", "non-profit organisations", "health", "transport and mobility",
    "biodiversity", "women and equality", "sport", "public authorities", "citizens"
]
PAGINAS = 1          # una página por tema para mantener la ejecución acotada
ESTADOS = ["31094501", "31094502"]   # próximas y abiertas
TIPOS = ["1", "2", "8"]              # subvenciones, premios y financiación en cascada
# -----------------------------

def primero(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""

def consultar(texto, pagina):
    consulta = {"bool": {"must": [{"terms": {"type": TIPOS}}, {"terms": {"status": ESTADOS}}]}}
    partes = {"sort": {"order": "DESC", "field": "startDate"}, "query": consulta, "languages": ["en"]}
    limite = uuid.uuid4().hex
    cuerpo = b""
    for nombre, valor in partes.items():
        cuerpo += (f'--{limite}\r\nContent-Disposition: form-data; name="{nombre}"; filename="blob"\r\n'
                   f'Content-Type: application/json\r\n\r\n{json.dumps(valor)}\r\n').encode()
    cuerpo += f"--{limite}--\r\n".encode()
    url = API + "?" + urllib.parse.urlencode({"apiKey": "SEDIA", "text": texto, "pageSize": 50, "pageNumber": pagina})
    req = urllib.request.Request(url, data=cuerpo, method="POST", headers={
        "Content-Type": f"multipart/form-data; boundary={limite}", "User-Agent": "Subvenly/1.0", "Accept": "application/json"})
    global ERRORES_CONSULTA
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.load(r)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        ERRORES_CONSULTA += 1
        print(f"  consulta omitida por error temporal: {e}")
        return None

def convertir(r, hoy):
    m = r.get("metadata") or {}
    ident = str(primero(m.get("identifier")) or r.get("reference") or "")
    titulo = " ".join(str(primero(m.get("title")) or r.get("title") or r.get("summary") or "").split())
    if not ident or not titulo:
        return None
    apertura = iso(primero(m.get("startDate")))
    cierre = iso(primero(m.get("deadlineDate")))
    estado = str(primero(m.get("status")) or "")
    if not estado:
        acciones = primero(m.get("actions"))
        if isinstance(acciones, str):
            try:
                acciones = json.loads(acciones)
            except json.JSONDecodeError:
                acciones = []
        if isinstance(acciones, list) and acciones:
            estado = str(((acciones[0].get("status") or {}).get("id")) or "")
    if estado == "31094501":
        estado_convocatoria = "próxima"
    elif estado == "31094502":
        estado_convocatoria = "en plazo"
    else:
        estado_convocatoria = "por verificar"
    return {"id": "UE-" + ident, "titulo": titulo[:300], "organo": "Comisión Europea", "ambito": "Unión Europea",
            "territorio": "Unión Europea", "n1": "UNIÓN EUROPEA", "n2": "UNIÓN EUROPEA", "n3": "COMISIÓN EUROPEA",
            "fecha": hoy.isoformat(), "fechaTipo": "detectada", "plazo_inicio": apertura,
            "cierre": cierre, "plazo_fin": cierre, "estadoConvocatoria": estado_convocatoria,
            "link": TOPIC.format(ident.lower()) if ident else r.get("url", ""), "visto": hoy.isoformat()}

def main():
    hoy = dt.date.today()
    if "--fixture" in sys.argv:
        raw = json.load(open(sys.argv[sys.argv.index("--fixture") + 1], encoding="utf-8")).get("results", [])
    else:
        raw, vistos = [], set()
        for t in BUSQUEDAS:
            for p in range(1, PAGINAS + 1):
                res = consultar(t, p).get("results") or []
                print(f"  '{t}' página {p}: {len(res)} resultados")
                for r in res:
                    k = str(primero((r.get("metadata") or {}).get("identifier")) or r.get("reference"))
                    if k not in vistos:
                        vistos.add(k); raw.append(r)
                if len(res) < 50:
                    break
                time.sleep(0.5)
    print(f"Recibidas {len(raw)} convocatorias de la UE")
    if not raw:
        print("El portal no devolvió nada: no se modifica ningún dato.")
        return 1
    escribir("_diagnostico_ue.json", {"fecha": hoy.isoformat(), "recibidas": len(raw), "ejemplo": raw[0]})
    previo_doc = leer("novedades.json", {"items": []})
    estado_actualizacion = previo_doc.get("estadoActualizacion", "desconocida")
    previo = {i["id"]: i for i in previo_doc.get("items", [])}
    for r in raw:
        n = convertir(r, hoy)
        if not n:
            continue
        if n["id"] not in previo:
            previo[n["id"]] = n
        else:
            # Actualizar plazos y estado del portal sin reiniciar la fecha en que se detectó.
            visto = previo[n["id"]].get("visto") or n["visto"]
            previo[n["id"]].update(n)
            previo[n["id"]]["visto"] = visto
    limite = (hoy - dt.timedelta(days=RETENCION_DIAS)).isoformat()
    nueva_lim = (hoy - dt.timedelta(days=NUEVA_DIAS)).isoformat()
    items = [i for i in previo.values() if (i["fecha"] >= limite or (i.get("plazo_fin") and i["plazo_fin"] >= hoy.isoformat())) and not (i.get("cierre") and i["cierre"] < hoy.isoformat())]
    for i in items:
        i["nueva"] = i["visto"] >= nueva_lim
    items.sort(key=lambda i: (i["fecha"], i["id"]), reverse=True)
    if ERRORES_CONSULTA:
        estado_actualizacion = "parcial"
        errores_previos = previo_doc.get("erroresActualizacion", [])
        errores_previos = errores_previos if isinstance(errores_previos, list) else []
        errores_actualizacion = list(dict.fromkeys(errores_previos + [f"Unión Europea: {ERRORES_CONSULTA} consulta(s) fallida(s)"]))
    else:
        errores_actualizacion = previo_doc.get("erroresActualizacion", [])
    salida = {"actualizado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "estadoActualizacion": estado_actualizacion, "items": items[:MAX_ITEMS]}
    if errores_actualizacion:
        salida["erroresActualizacion"] = errores_actualizacion
    escribir("novedades.json", salida, compacto=True)
    print(f"Guardadas {min(len(items), MAX_ITEMS)} novedades en total.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR:", e)
        sys.exit(1)
