#!/usr/bin/env python3
"""Validaciones de integridad para Subvenly. No requiere dependencias externas."""
import json, pathlib, re, subprocess, tempfile, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

def cargar(nombre):
    ruta = DATA / nombre
    with ruta.open(encoding="utf-8") as f:
        return json.load(f)

def exigir(condicion, mensaje):
    if not condicion:
        raise ValueError(mensaje)

def main():
    fichas = cargar("fichas.json")
    fuentes_doc = cargar("fuentes.json")
    geo = cargar("geografia.json")
    novedades = cargar("novedades.json")
    licitaciones = cargar("licitaciones.json")
    exigir(isinstance(fichas, list), "data/fichas.json debe ser una lista")
    ids = [str(x.get("id")) for x in fichas]
    exigir(len(ids) == len(set(ids)), "Hay IDs de fichas duplicados")
    for f in fichas:
        exigir(f.get("id") is not None and f.get("titulo") and isinstance(f.get("reqs", {}), dict),
               "Ficha sin id, título o requisitos válidos: " + str(f.get("id")))
        exigir(isinstance(f.get("requisitos", []), list), "requisitos debe ser una lista: " + str(f.get("id")))
        links = f.get("links") or ([["Trámite", f.get("link")]] if f.get("link") else [])
        for item in links:
            exigir(isinstance(item, list) and len(item) >= 2, "Enlace mal formado en ficha " + str(f.get("id")))
            exigir(str(item[1]).startswith(("https://", "http://", "#")), "URL mal formada en ficha " + str(f.get("id")))
        if f.get("pend"):
            exigir(f.get("plazo") or f.get("estadoManual"), "Ficha pendiente sin estado explicativo: " + str(f.get("id")))
    personales = [f for f in fichas if f.get("perfil") == "personal"]
    exigir(len(personales) >= 5, "Faltan fichas personales/familiares")
    exigir(isinstance(fuentes_doc.get("fuentes"), list) and fuentes_doc["fuentes"], "No hay registro de fuentes")
    fuentes = fuentes_doc["fuentes"]
    sids = [x.get("id") for x in fuentes]
    exigir(len(sids) == len(set(sids)), "Hay IDs de fuentes duplicados")
    urls = [x.get("url") for x in fuentes]
    exigir(len(urls) == len(set(urls)), "Hay URLs duplicadas en data/fuentes.json")
    for x in fuentes:
        exigir(x.get("id") and x.get("nombre") and x.get("categoria"), "Fuente incompleta: " + str(x.get("id")))
        exigir(str(x.get("url", "")).startswith("https://"), "Fuente sin URL HTTPS: " + str(x.get("id")))
    provincias = geo.get("provinces", [])
    exigir(len(provincias) >= 50, "El catálogo geográfico no contiene todas las provincias")
    municipios = sum(len(p.get("m", [])) for p in provincias)
    comunidades = {p.get("c") for p in provincias}
    exigir(municipios >= 8000, "El catálogo geográfico parece incompleto: " + str(municipios) + " municipios")
    exigir(len(comunidades) >= 17, "El catálogo geográfico no cubre todas las comunidades y ciudades autónomas")
    exigir(isinstance(novedades, dict) and isinstance(licitaciones, dict), "Estructura de novedades o licitaciones inválida")
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, flags=re.I | re.S)
    inline = [code for attrs, code in scripts if not re.search(r"\bsrc\\s*=", attrs, flags=re.I) and code.strip()]
    exigir(inline, "No se encontraron scripts JavaScript inline para validar")
    node = subprocess.run(["node", "--version"], capture_output=True, text=True)
    exigir(node.returncode == 0, "Node.js no está disponible para validar JavaScript")
    for i, code in enumerate(inline, 1):
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as tmp:
            tmp.write(code)
            ruta = tmp.name
        try:
            r = subprocess.run(["node", "--check", ruta], capture_output=True, text=True)
            exigir(r.returncode == 0, "Error de sintaxis JS en bloque " + str(i) + ": " + r.stderr)
        finally:
            pathlib.Path(ruta).unlink(missing_ok=True)
    print("OK: {} fichas ({} personales), {} fuentes, {} provincias, {} municipios; {} bloques JS válidos.".format(
        len(fichas), len(personales), len(fuentes), len(provincias), municipios, len(inline)))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("VALIDACIÓN FALLIDA:", exc)
        sys.exit(1)
