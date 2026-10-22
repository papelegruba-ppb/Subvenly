# Subvenly

Buscador de ayudas, subvenciones y créditos para autónomos y empresas, con test de encaje. Un proyecto de Papelegruba.

## Qué hay en la carpeta
- `index.html`: la aplicación (diseño y test).
- `data/fichas.json`: fichas de ayudas y prestaciones, con reglas de compatibilidad y estado verificable. Las fichas personales llevan `perfil: "personal"`.
- `data/novedades.json`, `data/licitaciones.json`, `data/vigilancia.json` y `data/vigilancia_fuentes.json`: resultados y huellas de seguimiento automático. `data/fuentes.json` registra las fuentes oficiales y el estado de cobertura territorial; la aplicación muestra el catálogo de fuentes para abrirlas desde la web.
- `scripts/actualizar.py`: busca cada noche convocatorias nuevas en la BDNS para todo el Estado y hace un repaso histórico progresivo de los últimos 90 días en bloques de siete días. La cobertura depende de los términos de búsqueda y de los datos publicados; no equivale a un catálogo exhaustivo de ayudas abiertas.
- `scripts/actualizar_ue.py`: busca convocatorias abiertas o próximas de la Unión Europea en Funding & Tenders con consultas temáticas de empresa, investigación, educación, cultura, medioambiente, agricultura, salud, juventud y otros ámbitos. Los títulos suelen venir en inglés; la ficha distingue la fecha de detección de la apertura y muestra el estado del portal cuando está disponible.
- `scripts/actualizar_licitaciones.py`: busca licitaciones abiertas (en plazo de presentar oferta) en la Plataforma de Contratación del Sector Público y las guarda en `data/licitaciones.json`. Procesa pocas páginas por ejecución y guarda el cursor de continuación si necesita más lotes; así no se bloquea la publicación ni se pierde el punto de avance.
- `scripts/vigilar_creditos.py`: pese al nombre histórico, vigila los enlaces oficiales de todas las fichas y registra posibles cambios de fechas, importes o bases en `data/vigilancia.json`. Respeta `robots.txt`.
- `scripts/vigilar_fuentes.py`: vigila las páginas de `data/fuentes.json` y conserva las huellas y muestras antes/después de cambios para revisión.
- `scripts/validar_datos.py`: valida JSON, identificadores, enlaces, cobertura geográfica y sintaxis de los bloques JavaScript antes de publicar.
- `.github/workflows/actualizar.yml`: la tarea programada que ejecuta los importadores, valida los datos y publica la web. El resumen de Actions informa de fuentes fallidas o parciales; una fuente externa inaccesible no debe convertir una publicación correcta en un falso fallo de despliegue.
- `fonts/`, `assets/`, `favicon.svg`: fuentes (Fraunces e Inter, licencia OFL) y logos de Subvenly.

## Puesta en marcha
1. Crea un repositorio en GitHub y sube **todo el contenido**, incluida la carpeta oculta `.github`.
2. En el repositorio: **Settings > Pages > Build and deployment > Source: GitHub Actions**.
3. Ve a la pestaña **Actions > Actualizar y publicar > Run workflow**. Es la primera ejecución y sirve de prueba.
4. Cuando termine, abre la dirección que aparece en el paso «deploy» (`https://TU-USUARIO.github.io/NOMBRE/`).

A partir de ahí se ejecuta solo cada noche, a las 03:17 UTC, y también cada vez que cambies algo en `main`.

## Cobertura y estados de las ayudas

- El test pregunta primero si se buscan ayudas como particular/familia, autónomo, empresa/sociedad o en ambos ámbitos. La ruta personal activa preguntas de familia, nacimiento/adopción, alquiler, unidad de convivencia, ingresos y beneficios fiscales solo cuando corresponden. Las rutas empresariales existentes se mantienen.
- Las fichas pueden indicar una próxima convocatoria anunciada sin fecha, una convocatoria pendiente de verificar o un plazo concreto. Una página de información general no se trata como una convocatoria abierta.
- Las páginas oficiales se comprueban a diario. Si cambia el contenido, se guarda una señal de revisión con muestras anteriores y nuevas; el sistema **no** cambia automáticamente los requisitos ni concluye que la convocatoria está abierta. Las bases o PDFs que cambien deben revisarse y confirmarse antes de modificar reglas de compatibilidad.
- BDNS permite descubrir convocatorias estatales, autonómicas y locales en toda España. El catálogo territorial contempla las 17 comunidades autónomas y Ceuta/Melilla. Hay fuentes especializadas registradas para 16 territorios; para Castilla-La Mancha, La Rioja y Ceuta se conserva el portal oficial de entrada y queda pendiente localizar/verificar el buscador especializado. La cobertura municipal directa también debe ampliarse progresivamente; no se anuncia como exhaustiva mientras queden fuentes por incorporar o sin verificar.
- Las ayudas personales, beneficios fiscales, subvenciones empresariales, financiación y licitaciones se deben mantener como categorías distintas. Las licitaciones siguen en sección separada.

## Si una fuente falla
Abre la ejecución de GitHub Actions y consulta el resumen final. Los diagnósticos `data/_diagnostico.json`, `data/_diagnostico_ue.json` y `data/_diagnostico_licitaciones.json` muestran la fecha, los resultados y los errores conocidos. La web puede seguir publicándose con datos previos o parciales, pero la interfaz debe indicarlo; un fallo de fuente no se interpreta como cierre de la convocatoria.

## Cosas a saber
- Para ver la web en tu ordenador, no abras `index.html` con doble clic (el navegador bloquea la carga de los datos). Ejecuta `python -m http.server` dentro de la carpeta y abre `http://localhost:8000`.
- En repositorios públicos, GitHub pausa las tareas programadas si pasan 60 días sin actividad. Si ocurre, actívalas de nuevo en la pestaña Actions.
- **No necesitas instalar ni lanzar Python.** Los scripts se ejecutan solos en los servidores de GitHub cada noche. Python solo hace falta si quieres probarlos en tu ordenador.
- Se automatizan las **subvenciones** (BDNS), las **convocatorias de la UE** y las **licitaciones abiertas**. Los **créditos** (ICF, ICO, Enisa) no tienen ninguna fuente automática: siguen siendo fichas manuales, pero se vigilan sus páginas oficiales y la web avisa cuando algo cambia.
- El test cruza lo que responde la persona (comunidad autónoma, municipio, autónomo o sociedad) con las novedades: muestra primero las de «posible encaje» y oculta las que claramente no encajan. Es un filtro por territorio y tipo de beneficiario, no una garantía: los requisitos concretos (edad, inversión mínima, contratación…) solo están en las fichas que tú validas.
- Las licitaciones no se pueden comprobar contra el test (la solvencia depende de cada pliego): se filtran por sector, importe y zona.
- Los contratos menores no se incluyen: se publican una vez adjudicados, así que ya no se puede concurrir.
- La web muestra las novedades caducadas solo si no se conoce su plazo; las que tienen fecha de cierre pasada desaparecen solas.
- Lo que sale en «Novedades detectadas» no está revisado: pasa a `fichas.json` cuando lo valides. La fecha, el estado y los requisitos deben contrastarse con la convocatoria oficial antes de recomendar la solicitud.
- La sección de prestaciones personales incluye la prestación contributiva por desempleo y los subsidios SEPE por agotamiento, cotización insuficiente, mayores de 52 años y emigración retornada. El test ayuda a orientar, pero no calcula por sí solo cotizaciones, rentas ni todos los plazos legales.
- PIMEC no es una dependencia técnica del catálogo. Si se habilita una exportación o importación autorizada, sus resultados pueden servir como fuente de descubrimiento; la ficha debe enlazar a la convocatoria pública oficial y seguir funcionando sin una suscripción de PIMEC.
