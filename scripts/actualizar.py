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
MAX_DETALLES = 100        # presupuesto prudente de detalles nuevos y revisiones por ejecución
DIAS_RETROCESO = 90       # cobertura histórica progresiva dentro de la ventana retenida
BLOQUE_RETROCESO = 7      # días por lote histórico para no disparar el tiempo de ejecución
DETALLE = "https://www.infosubvenciones.es/bdnstrans/api/convocatorias?numConv={}&vpd=GE"
# Territorios que se conservan (sin tildes, en minúsculas). Lista vacía = TODA España:
# estatales, de todas las comunidades autónomas y locales (ayuntamientos, diputaciones...).
# Ejemplo para limitarlo: ["cataluna", "catalunya", "lleida", "madrid"]
TERRITORIOS = []
# La convocatoria debe mencionar alguno de estos temas...
INCLUIR = [
    # Términos generales de convocatoria: priorizar cobertura amplia y revisar relevancia después
    "ayuda", "ajut", "subvencion", "prestacion", "prestacio", "subsidio", "pension", "pensio",
    "beca", "premio", "premi",
    # Autónomos, empresas, empleo y actividad económica
    "autonom", "emprend", "pyme", "microempres", "pequena empresa", "empresa", "comerc",
    "contratacion", "contractacio", "empleo", "ocupacio", "digitaliz", "inversion", "inversio",
    "innovacion", "innovacio", "formacion", "formacio", "establecimiento", "negocio", "turis",
    "rural", "industri", "internacionaliz", "eficiencia energ", "autoocupacio", "cuota cero",
    "tarifa cero", "bonificacion", "bonificacio", "ayuda al empleo", "exportacion", "exportacio",
    "financiacion", "financament", "economia social", "cooperativa", "artesania", "artesania",
    "startup", "empresa emergente", "propiedad industrial", "propietat industrial", "marca",
    # Personas, familias, vivienda y prestaciones
    "ingreso minimo vital", "ingres minim vital", "renta garantizada", "renda garantida",
    "nacimiento", "naixement", "adopcion", "adopcio", "familia", "families", "infancia",
    "hijos a cargo", "crianza", "maternidad", "maternitat", "alquiler", "lloguer", "vivienda",
    "habitatge", "arrendamiento", "jovenes", "joves", "discapacidad", "discapacitat",
    "dependencia", "pobreza", "vulnerabilidad", "emergencia social", "mayores", "tercera edad",
    "salud", "sanidad", "sanitari", "enfermedad", "cuidados", "conciliacion", "conciliacio",
    "igualdad", "igualtat", "mujer", "dona", "violencia", "victimas", "victimes", "exclusion social",
    "emigrante retornado", "emigrants retornats", "retorno", "retorn", "desempleo", "atur",
    "renta", "familia monoparental", "familia numerosa", "beca", "becas", "estudios", "estudi",
    "educacion", "educacio", "libros", "llibres", "comedor escolar", "transport escolar",
    "matricula", "matrícula", "universidad", "universitat", "juventud", "joventut",
    # Cultura, deporte, investigación, agricultura, medio ambiente y territorio
    "cultura", "cultural", "patrimonio", "patrimoni", "museo", "cinematograf", "audiovisual",
    "artes escenicas", "arts esceniques", "deporte", "deportiv", "esport", "club deportivo",
    "investigacion", "investigacio", "ciencia", "cientific", "agricultura", "agricola",
    "ganader", "ramader", "pesca", "acuicultura", "forestal", "explotacion agraria",
    "medio ambiente", "medi ambient", "biodiversidad", "biodiversitat", "residuos", "residus",
    "agua", "sequía", "sequia", "incendio", "incendis", "inundacion", "inundacio", "catastrofe",
    "catastrofe", "dana", "emergencia", "combustible", "gasoleo", "gasoil", "carburante",
    "energia", "energía", "anticrisis", "pago unico", "pagament unic", "rehabilitacion",
    "rehabilitacio", "accesibilidad", "accessibilitat", "eficiencia energetica", "movilidad",
    "mobilitat", "transporte", "transport", "comunidad de propietarios", "comunitat de propietaris",
    "asociaciones", "associacions", "entidad sin animo de lucro", "entitats sense afany de lucre",
    "ong", "voluntariado", "voluntariat", "premio", "premios", "premi", "200 euros", "200 €"
]
# No se excluyen categorías completas (deporte, cultura, asociaciones, bienestar animal, etc.):
# pueden contener ayudas públicas legítimas. La relevancia se decide por términos positivos.
EXCLUIR = []
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
    else:
        raise RuntimeError("Se alcanzó el límite de páginas BDNS sin completar el intervalo; no se avanzará el cursor.")
    return items

def relevante(it):
    n1, n2, n3 = (pick(it, k) for k in ("nivel1", "nivel2", "nivel3"))
    territorio = norm(" ".join([str(n1), str(n2), str(n3)]))
    texto = norm(" ".join(str(it.get(k) or "") for k in ("descripcion", "descripcionLeng")))
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
    return {"id": num, "fuente": "BDNS", "titulo": titulo, "organo": " · ".join(x for x in (n3, n2) if x),
            "n1": n1, "n2": n2, "n3": n3, "ambito": ambito, "territorio": territorio, "fecha": iso(pick(it, "fechaRecepcion")) or hoy.isoformat(),
            "link": FICHA.format(num), "visto": hoy.isoformat()}

def normalizar_fuente(item):
    """Rellena la procedencia solo cuando el identificador o el enlace son concluyentes."""
    if not isinstance(item, dict) or item.get("fuente"):
        return item
    ident = str(item.get("id") or "").strip().lower()
    link = str(item.get("link") or "").strip().lower()
    if ident.startswith("cido-") or "cido.diba.cat/" in link:
        item["fuente"] = "CIDO"
    elif ident.startswith("ue-") or "ec.europa.eu/info/funding-tenders/" in link or "api.tech.ec.europa.eu/" in link:
        item["fuente"] = "Comisión Europea"
    elif ident.isdigit() or "infosubvenciones.es/bdnstrans/" in link:
        item["fuente"] = "BDNS"
    return item

def es_bdns(item):
    """Solo las convocatorias de la BDNS tienen detalle en el endpoint numConv."""
    return item.get("fuente") != "CIDO" and str(item.get("id", "")).isdigit()


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
    fixture = "--fixture" in sys.argv
    error_retroceso = ""
    retroceso_hasta_siguiente = estado.get("retrocesoHasta", "")
    if fixture:
        raw = json.load(open(sys.argv[sys.argv.index("--fixture") + 1], encoding="utf-8"))
        raw = raw.get("content", raw)
    else:
        print(f"Consultando la BDNS desde {desde} hasta {hoy}")
        raw = descargar(desde, hoy)
        # Segunda pasada: recorre progresivamente los últimos 90 días para completar categorías
        # que antes no se detectaban por las palabras clave. Se hace en bloques de siete días.
        limite_retroceso = hoy - dt.timedelta(days=DIAS_RETROCESO)
        try:
            cursor = dt.date.fromisoformat(estado.get("retrocesoHasta", "")) if estado.get("retrocesoHasta") else hoy - dt.timedelta(days=3)
        except ValueError:
            cursor = hoy - dt.timedelta(days=3)
        if cursor < limite_retroceso or cursor > hoy:
            cursor = hoy - dt.timedelta(days=3)
        retroceso_desde = max(limite_retroceso, cursor - dt.timedelta(days=BLOQUE_RETROCESO - 1))
        print(f"Repaso histórico BDNS: {retroceso_desde} a {cursor}")
        try:
            historico = descargar(retroceso_desde, cursor)
            raw.extend(historico)
            if retroceso_desde <= limite_retroceso:
                retroceso_hasta_siguiente = (hoy - dt.timedelta(days=3)).isoformat()
            else:
                retroceso_hasta_siguiente = (retroceso_desde - dt.timedelta(days=1)).isoformat()
        except Exception as exc:
            error_retroceso = str(exc)[:500]
            retroceso_hasta_siguiente = cursor.isoformat()
            print("AVISO: el repaso histórico no se completó; se conserva el cursor para reintentarlo:", error_retroceso)
    # Una convocatoria puede aparecer en las dos ventanas. Deduplicar antes de filtrar y enriquecer.
    unicos = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        ident = str(pick(item, "numeroConvocatoria", "codigoBDNS", "id") or "")
        if ident and ident not in unicos:
            unicos[ident] = item
    raw = list(unicos.values())
    filtradas = [it for it in raw if relevante(it)]
    print(f"Recibidas: {len(raw)} · relevantes: {len(filtradas)}")
    if fixture and not raw:
        print("El fixture está vacío: no se modifica ningún dato.")
        return 1
    detalles, det_ok = 0, True
    previo = {str(i["id"]): normalizar_fuente(i) for i in leer("novedades.json", {"items": []}).get("items", []) if isinstance(i, dict) and i.get("id") is not None}
    campos_lista = ("titulo", "organo", "n1", "n2", "n3", "ambito", "territorio", "fecha", "link", "fuente")
    for it in filtradas:
        n = convertir(it, hoy)
        ident = str(n.get("id") or "")
        if not ident:
            continue
        if ident not in previo:
            n["visto"] = hoy.isoformat()
            previo[ident] = n
        else:
            anterior = previo[ident]
            for campo in campos_lista:
                if n.get(campo) not in ("", None):
                    anterior[campo] = n[campo]
            anterior["ultimaVezDetectada"] = hoy.isoformat()
        actual = previo[ident]
        if not actual.get("detalleRevisado") and det_ok and detalles < MAX_DETALLES:
            try:
                detalle = campos_detalle(get(DETALLE.format(ident), intentos=1))
                if detalle:
                    actual.update(detalle)
                    actual["detalleActualizado"] = hoy.isoformat()
                actual["detalleRevisado"] = hoy.isoformat()
                detalles += 1
                time.sleep(0.15)
            except Exception as e:
                actual["detalleRevisado"] = hoy.isoformat()
                print("  detalle no disponible, se sigue sin él:", e)
                det_ok = False
    # Revisar periódicamente detalles antiguos para detectar cambios en plazos, bases o importes.
    hoy_iso = hoy.isoformat()
    def prioridad_detalle(item):
        fin = item.get("plazo_fin") or item.get("cierre") or ""
        if fin and fin >= hoy_iso:
            return (0, fin, item.get("detalleRevisado", ""))
        if not fin:
            return (1, "9999-12-31", item.get("detalleRevisado", ""))
        return (2, fin, item.get("detalleRevisado", ""))
    revisables = []
    for item in previo.values():
        if not es_bdns(item):
            continue
        revisado = item.get("detalleRevisado", "")
        try:
            viejo = not revisado or (hoy - dt.date.fromisoformat(revisado[:10])).days >= 7
        except ValueError:
            viejo = True
        if viejo:
            revisables.append(item)
    revisables.sort(key=prioridad_detalle)
    for item in revisables:
        if not det_ok or detalles >= MAX_DETALLES:
            break
        try:
            detalle = campos_detalle(get(DETALLE.format(item["id"]), intentos=1))
            if detalle:
                item.update(detalle)
                item["detalleActualizado"] = hoy.isoformat()
            item["detalleRevisado"] = hoy.isoformat()
            detalles += 1
            time.sleep(0.15)
        except Exception as e:
            item["detalleRevisado"] = hoy.isoformat()
            print("  revisión de detalle no disponible para", item["id"], ":", e)
            det_ok = False
    limite = (hoy - dt.timedelta(days=RETENCION_DIAS)).isoformat()
    nueva_lim = (hoy - dt.timedelta(days=NUEVA_DIAS)).isoformat()
    items = [i for i in previo.values() if i["fecha"] >= limite or (i.get("plazo_fin") and i["plazo_fin"] >= hoy.isoformat())]
    for i in items:
        i["nueva"] = i["visto"] >= nueva_lim
    items.sort(key=lambda i: (i["fecha"], i["id"]), reverse=True)
    estado_actualizacion = "parcial" if error_retroceso or not det_ok else "correcta"
    escribir("_diagnostico.json", {"fecha": hoy.isoformat(), "recibidas": len(raw), "relevantes": len(filtradas),
        "detalles_pedidos": detalles, "detalle_funciona": det_ok, "estado": estado_actualizacion,
        "retroceso_desde": (retroceso_desde.isoformat() if not fixture else None),
        "retroceso_hasta": (cursor.isoformat() if not fixture else None),
        "error_retroceso": error_retroceso,
        "claves_primer_elemento": sorted(raw[0].keys()) if raw else [], "ejemplo": raw[0] if raw else None})
    escribir("novedades.json", {"actualizado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "estadoActualizacion": estado_actualizacion, "items": items[:MAX_ITEMS]}, compacto=True)
    escribir("estado.json", {"ultima": hoy.isoformat(), "retrocesoHasta": retroceso_hasta_siguiente})
    print(f"Guardadas {min(len(items), MAX_ITEMS)} novedades; actualización {estado_actualizacion}.")
    return 2 if estado_actualizacion == "parcial" else 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("ERROR:", e)
        sys.exit(1)
