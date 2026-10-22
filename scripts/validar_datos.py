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
        exigir(f.get("categoria"), "Ficha sin categoría de objetivo: " + str(f.get("id")))
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
    exigir(all(f.get("estadoManual") or f.get("cerrada") or f.get("cierre") for f in personales), "Ficha personal sin estado o plazo explícito")
    exigir(isinstance(fuentes_doc.get("fuentes"), list) and fuentes_doc["fuentes"], "No hay registro de fuentes")
    fuentes = fuentes_doc["fuentes"]
    territorios = fuentes_doc.get("coberturaTerritorial", [])
    exigir(len(territorios) >= 19, "El registro debe contemplar las 17 comunidades y Ceuta/Melilla")
    nombres_territorio = {x.get("nombre") for x in territorios}
    exigir({"Andalucía", "Cataluña", "Comunidad de Madrid", "Ceuta", "Melilla"}.issubset(nombres_territorio), "Faltan territorios clave en el registro de fuentes")
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
    # Comprobaciones estáticas de rutas y filtros principales de la interfaz.
    for token in ('id="advf"', 'function aplicaPerfil(a)', 'function controlPregunta(k)',
                  'Todos los ámbitos', 'Todos los organismos', 'Todos los objetivos', 'categoriaAyuda', 'Pendientes', 'Por verificar',
                  'nacimientoFecha:"date"', 'menores:"number"', 'compatAyuda'):
        exigir(token in html, "Falta función o control de test/filtros: " + token)
    # Las funciones se declaran más de una vez en index.html; JavaScript usa la última.
    # Comprobar las definiciones efectivas evita falsos positivos por código antiguo sobrescrito.
    def ultima_funcion(nombre):
        inicio_nombre = html.rfind("function " + nombre + "(")
        exigir(inicio_nombre >= 0, "Falta la función de interfaz: " + nombre)
        inicio = html.find("{", inicio_nombre) + 1
        fin = html.find("\nfunction ", inicio)
        return html[inicio:fin if fin >= 0 else len(html)]

    ruta = ultima_funcion("secuencia")
    mostrar = ultima_funcion("mostrar")
    perfil_ui = ultima_funcion("renderProfile")
    estado_ui = ultima_funcion("estado")
    novedades_ui = ultima_funcion("encajeNov")
    perfil_novedades = ultima_funcion("perfilNov")
    exigir('A.perfil==="particular"' in ruta and 'A.perfil==="ambos"' in ruta,
           "Las rutas efectivas deben contemplar particulares y perfil mixto")
    exigir("situacionPersonal" in ruta and "empleoSituacion" in ruta and "tramitar" in ruta and "ccaaResidencia" in ruta,
           "La ruta efectiva no incorpora situación personal, empleo y tramitación")
    exigir("fechaAgotamiento" in mostrar and "fechaRetorno" in mostrar,
           "Faltan condiciones para mostrar fechas de desempleo/retorno solo cuando correspondan")
    exigir("opcionesPregunta(k)" in perfil_ui and "function selCcaaResidencia()" in html and "ccaaResidencia" in perfil_ui and "dgsimulador/introSimulador.do" in perfil_ui and
           "idAmb=100404&idProc=133655" in perfil_ui and "solicitud-informes-riesgos-cirbe-p58.html" in perfil_ui,
           "La interfaz efectiva no presenta los selectores nuevos o el simulador SEPE")
    exigir("usaResidencia" in novedades_ui and "ccaaResidencia" in perfil_novedades,
           "Las novedades no distinguen territorio personal y empresarial")
    exigir(estado_ui.find("if(a.pend)return") >= 0 and
           estado_ui.find("if(a.pend)return") < estado_ui.find("var d="),
           "Una fecha provisional no debe cerrar automáticamente una convocatoria pendiente")

    # Cada requisito usado por las fichas debe tener una pregunta visible en el test.
    question_blocks = re.findall(r"var QUESTIONS\s*=\s*\{([\s\S]*?)\n\};", html)
    question_blocks += re.findall(r"Object\.assign\(QUESTIONS,\s*\{([\s\S]*?)\}\);", html)
    question_keys = set()
    for block in question_blocks:
        question_keys.update(re.findall(r"^\s*([A-Za-z_$][\w$]*):", block, flags=re.M))
    requirement_keys = {key for ficha in fichas for key in (ficha.get("reqs") or {})}
    missing_questions = sorted(requirement_keys - question_keys)
    exigir(not missing_questions, "Faltan preguntas visibles para requisitos de fichas: " + ", ".join(missing_questions))
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, flags=re.I | re.S)
    inline = [code for attrs, code in scripts if not re.search(r"\bsrc\s*=", attrs, flags=re.I) and code.strip()]
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
    prueba_rutas = subprocess.run(["node", str(ROOT / "scripts" / "test_rutas.js")],
                                  capture_output=True, text=True, cwd=ROOT)
    exigir(prueba_rutas.returncode == 0,
           "Fallaron las pruebas de rutas del test: " + (prueba_rutas.stdout + prueba_rutas.stderr).strip())
    print(prueba_rutas.stdout.strip())
    prueba_actualizadores = subprocess.run([sys.executable, str(ROOT / "scripts" / "test_actualizadores.py")],
                                           capture_output=True, text=True, cwd=ROOT)
    exigir(prueba_actualizadores.returncode == 0,
           "Fallaron las pruebas de actualizadores: " + (prueba_actualizadores.stdout + prueba_actualizadores.stderr).strip())
    print(prueba_actualizadores.stdout.strip())
    print("OK: {} fichas ({} personales), {} fuentes, {} territorios, {} provincias, {} municipios; {} bloques JS válidos.".format(
        len(fichas), len(personales), len(fuentes), len(territorios), len(provincias), municipios, len(inline)))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("VALIDACIÓN FALLIDA:", exc)
        sys.exit(1)
