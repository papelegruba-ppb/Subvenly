#!/usr/bin/env python3
"""Busca convocatorias nuevas en la BDNS (Base de Datos Nacional de Subvenciones)
y actualiza data/novedades.json. Solo usa la biblioteca estándar de Python.

Uso:
  python scripts/actualizar.py                    # consulta la API real
  python scripts/actualizar.py --fixture f.json   # prueba con un JSON local, sin red
"""
import json, os, sys, time, unicodedata, datetime as dt
import urllib.request, urllib.parse, urllib.error

API = "https://www.infosubvenciones.es/bdnstrans/api/convocatorias/busqueda"
FICHA = "https://www.infosubvenciones.es/bdnstrans/GE/es/convocatoria/{}"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

# ---------- AJUSTES (edita aquí lo que quieras filtrar) ----------
DIAS_PRIMERA_VEZ = 14      # cuántos días atrás mira la primera vez
MARGEN_DIAS = 2            # solape con la última búsqueda, por si algo llega tarde
RETENCION_DIAS = 90       # cuánto tiempo se conserva una novedad
NUEVA_DIAS = 7             # durante cuántos días lleva la etiqueta "Nuevo"
PAGINA = 200
MAX_PAGINAS = 40
MAX_ITEMS = 2000
MAX_DETALLES = 300        # máximo de convocatorias cuyo detalle se pide en cada ejecución
DETALLE = "https://www.infosubvenciones.es/bdnstrans/api/convocatorias?numConv={}&vpd=GE"
# Territorios que se conservan (sin tildes, en minúsculas). Lista vacía = TODA España:
# estatales, de todas las comunidades autónomas y locales (ayuntamientos, diputaciones...).
# Ejemplo para limitarlo: ["cataluna", "catalunya", "lleida", "madrid"]
TERRITORIOS = []
# La convocatoria debe mencionar alguno de estos temas...
INCLUIR = [
    # Empresa, autónomos, empleo e innovación
    "autonom", "emprend", "pyme", "microempres", "pequena empresa", "empresa", "comerc",
    "contratacion", "contractacio", "empleo", "ocupacio", "digitaliz", "inversion", "inversio",
    "innovacion", "innovacio", "formacion", "formacio", "establecimiento", "negocio", "turis",
    "rural", "industri", "internacionaliz", "eficiencia energ", "autoocupacio", "cuota cero",
    "tarifa cero", "bonificacion", "bonificacio", "ayuda al empleo",
    # Personas, familias, vivienda y prestaciones
    "ingreso minimo vital", "ingres minim vital", "renta garantizada", "renda garantida",
    "nacimiento", "naixement", "adopcion", "adopcio", "familia", "families", "infancia",
    "infancia", "hijos a cargo", "crianza", "maternidad", "maternitat", "alquiler", "lloguer",
    "vivienda", "habitatge", "arrendamiento", "jovenes", "joves", "discapacidad", "discapacitat",
    "dependencia", "dependencia", "pobreza", "vulnerabilidad", "emergencia social",
    # Emergencias, energía, combustible y medidas extraordinarias
    "dana", "catastrofe", "catastrofe", "emergencia", "combustible", "gasoleo", "gasoil",
    "carburante", "energia", "anticrisis", "pago unico", "pagament unic", "200 euros",
    "200 €", "marcas", "marques", "propiedad industrial", "propietat industrial"
]
# Exclusiones de bajo valor; no excluir becas o ayudas educativas de forma global.
EXCLUIR = ["deportiv", "esportiv", "festejo", "bienestar animal"]
# -----------------------------------------------------------------

def norm(t):
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode()
    return t.lower()

def pick(d, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return ""

def iso(f):
    f = str(f or "")[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(f, fmt).date().isoformat()
        except ValueError:
            pass
    return ""

def get(url, intentos=3):
    req = urllib.request.Request(url, headers={"User-Agent": "Subvenly/1.0 (+actualizacion nocturna)", "Accept": "application/json"})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            print(f"  intento {i+1}/{intentos} fallido: {e}")
            time.sleep(3 * (i + 1))
    raise RuntimeError("No se pudo consultar la BDNS tras varios intentos")

def descargar(desde, hasta):
    items = []
    for p in range(MAX_PAGINAS):
        q = urllib.parse.urlencode({"page": p, "pageSize": PAGINA, "order": "numeroConvocatoria", "direccion": "desc",
                                    "fechaDesde": desde.strftime("%d/%m/%Y"), "fechaHasta": hasta.strftime("%d/%m/%Y"), "vpd": "GE"})
        r = get(API + "?" + q)
        c = r.get("content") if isinstance(r, dict) else r
        if not c:
            break
        items += c
        print(f"  página {p}: {len(c)} convocatorias")
        if isinstance(r, dict) and r.get("last"):
            break
        time.sleep(0.2)  # el límite oficial es de 10 peticiones por segundo
    return items

def relevante(it):
    n1, n2, n3 = (pick(it, k) for k in ("nivel1", "nivel2", "nivel3"))
    territorio = norm(" ".join([str(n1), str(n2), str(n3)]))
    texto = norm(pick(it, "descripcion", "descripcionLeng"))
    estatal = "estado" in norm(n1) or "estatal" in norm(n1)
    if TERRITORIOS and not (estatal or any(t in territorio for t in TERRITORIOS)):
        return False
    if any(x in texto for x in EXCLUIR):
        return False
    return any(x in texto for x in INCLUIR)

def lista(d, *keys):
    """Convierte una lista de textos o de {descripcion: ...} en un texto separado por comas."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, list) and v:
            out = [str(pick(x, "descripcion", "nombre") if isinstance(x, dict) else x) for x in v]
            return ", ".join(o for o in out if o)
        if isinstance(v, str) and v:
            return v
    return ""

def campos_detalle(d):
    """Extrae del detalle de una convocatoria lo que se muestra en la web (todo es opcional)."""
    if not isinstance(d, dict):
        return {}
    r = {"plazo_inicio": iso(pick(d, "fechaInicioSolicitud")), "plazo_fin": iso(pick(d, "fechaFinSolicitud")),
         "presupuesto": pick(d, "presupuestoTotal"), "beneficiarios": lista(d, "tiposBeneficiarios", "beneficiarios"),
         "finalidad": str(pick(d, "descripcionFinalidad", "finalidad")), "bases": str(pick(d, "urlBasesReguladoras")),
         "sede": str(pick(d, "sedeElectronica"))}
    if len(r["beneficiarios"]) > 200: r["beneficiarios"] = r["beneficiarios"][:197].rstrip() + "…"
    return {k: v for k, v in r.items() if v not in ("", None)}

def clasificar(n1, n2):
    t = norm(n1)
    terr = n2.title() if n2 else ""
    if "estado" in t or "estatal" in t:
        return "Estatal", "España"
    if "local" in t:
        return "Local", terr
    if "autonom" in t:
        return "Autonómica", terr
    return "Otros", terr

def convertir(it, hoy):
    num = str(pick(it, "numeroConvocatoria", "codigoBDNS", "id"))
    n1, n2, n3 = (str(pick(it, k)) for k in ("nivel1", "nivel2", "nivel3"))
    titulo = " ".join(str(pick(it, "descripcion", "descripcionLeng")).split())
    if len(titulo) > 300:
        titulo = titulo[:297].rstrip() + "…"
    ambito, territorio = clasificar(n1, n2)
    return {"id": num, "titulo": titulo, "organo": " · ".join(x for x in (n3, n2) if x),
            "n1": n1, "n2": n2, "n3": n3, "ambito": ambito, "territorio": territorio, "fecha": iso(pick(it, "fechaRecepcion")) or hoy.isoformat(),
            "link": FICHA.format(num), "visto": hoy.isoformat()}

def leer(nombre, defecto):
    try:
        with open(os.path.join(DATA, nombre), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return defecto

def escribir(nombre, obj, compacto=False):
    with open(os.path.join(DATA, nombre), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=None if compacto else 1, separators=(",", ":") if compacto else None)

def main():
    hoy = dt.date.today()
    estado = leer("estado.json", {})
    ultima = iso(estado.get("ultima"))
    desde = (dt.date.fromisoformat(ultima) - dt.timedelta(days=MARGEN_DIAS)) if ultima else hoy - dt.timedelta(days=DIAS_PRIMERA_VEZ)
    if "--fixture" in sys.argv:
        raw = json.load(open(sys.argv[sys.argv.index("--fixture") + 1], encoding="utf-8"))
        raw = raw.get("content", raw)
    else:
        print(f"Consultando la BDNS desde {desde} hasta {hoy}")
        raw = descargar(desde, hoy)
    filtradas = [it for it in raw if relevante(it)]
    print(f"Recibidas: {len(raw)} · relevantes: {len(filtradas)}")
    if not raw:
        print("La BDNS no devolvió nada: no se modifica ningún dato.")
        return 1
    detalles, det_ok = 0, True
    previo = {i["id"]: i for i in leer("novedades.json", {"items": []}).get("items", [])}
    for it in filtradas:
        n = convertir(it, hoy)
        if n["id"] and n["id"] not in previo:
            if det_ok and detalles < MAX_DETALLES:
                try:
                    n.update(campos_detalle(get(DETALLE.format(n["id"]), intentos=1)))
                    detalles += 1
                    time.sleep(0.15)
                except Exception as e:
                    print("  detalle no disponible, se sigue sin él:", e)
                    det_ok = False
            previo[n["id"]] = n
    # Diagnóstico (se escribe al final para incluir los contadores): sirve para comprobar los nombres de campo reales
    escribir("_diagnostico.json", {"fecha": hoy.isoformat(), "recibidas": len(raw), "relevantes": len(filtradas), "detalles_pedidos": detalles, "detalle_funciona": det_ok,
                                   "claves_primer_elemento": sorted(raw[0].keys()) if isinstance(raw[0], dict) else [],
                                   "ejemplo": raw[0]})
    limite = (hoy - dt.timedelta(days=RETENCION_DIAS)).isoformat()
    nueva_lim = (hoy - dt.timedelta(days=NUEVA_DIAS)).isoformat()
    items = [i for i in previo.values() if i["fecha"] >= limite]
    for i in items:
        i["nueva"] = i["visto"] >= nueva_lim
    items.sort(key=lambda i: (i["fecha"], i["id"]), reverse=True)
    escribir("novedades.json", {"actualizado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "items": items[:MAX_ITEMS]}, compacto=True)
    escribir("estado.json", {"ultima": hoy.isoformat()})
    print(f"Guardadas {min(len(items), MAX_ITEMS)} novedades.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR:", e)
        sys.exit(1)
