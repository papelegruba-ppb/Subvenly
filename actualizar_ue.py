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
BUSQUEDAS = ["SME", "small and medium-sized enterprises", "start-up", "entrepreneur", "self-employed", "digitalisation SMEs"]
PAGINAS = 3          # páginas de 50 resultados por búsqueda
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
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            print(f"  intento {i+1}/3 fallido: {e}")
            time.sleep(3 * (i + 1))
    raise RuntimeError("No se pudo consultar el portal de la UE")

def convertir(r, hoy):
    m = r.get("metadata") or {}
    ident = str(primero(m.get("identifier")) or r.get("reference") or "")
    titulo = " ".join(str(primero(m.get("title")) or r.get("title") or r.get("summary") or "").split())
    if not ident or not titulo:
        return None
    return {"id": "UE-" + ident, "titulo": titulo[:300], "organo": "Comisión Europea", "ambito": "Unión Europea",
            "territorio": "Unión Europea", "n1": "UNIÓN EUROPEA", "n2": "UNIÓN EUROPEA", "n3": "COMISIÓN EUROPEA", "fecha": iso(primero(m.get("startDate"))) or hoy.isoformat(),
            "cierre": iso(primero(m.get("deadlineDate"))), "plazo_fin": iso(primero(m.get("deadlineDate"))), "link": TOPIC.format(ident.lower()) if ident else r.get("url", ""),
            "visto": hoy.isoformat()}

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
    previo = {i["id"]: i for i in leer("novedades.json", {"items": []}).get("items", [])}
    for r in raw:
        n = convertir(r, hoy)
        if n and n["id"] not in previo:
            previo[n["id"]] = n
    limite = (hoy - dt.timedelta(days=RETENCION_DIAS)).isoformat()
    nueva_lim = (hoy - dt.timedelta(days=NUEVA_DIAS)).isoformat()
    items = [i for i in previo.values() if i["fecha"] >= limite and not (i.get("cierre") and i["cierre"] < hoy.isoformat())]
    for i in items:
        i["nueva"] = i["visto"] >= nueva_lim
    items.sort(key=lambda i: (i["fecha"], i["id"]), reverse=True)
    escribir("novedades.json", {"actualizado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "items": items[:MAX_ITEMS]}, compacto=True)
    print(f"Guardadas {min(len(items), MAX_ITEMS)} novedades en total.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR:", e)
        sys.exit(1)
