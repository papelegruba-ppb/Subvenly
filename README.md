# Subvenly

Buscador de ayudas, subvenciones y créditos para autónomos y empresas, con test de encaje. Un proyecto de Papelegruba.

## Qué hay en la carpeta
- `index.html`: la aplicación (diseño y test).
- `data/fichas.json`: las fichas revisadas a mano. Para añadir una ayuda, copia una ficha y cambia sus textos.
- `data/novedades.json`, `data/licitaciones.json`, `data/vigilancia.json`: lo que encuentran las búsquedas automáticas (los rellenan los scripts, no los toques).
- `scripts/actualizar.py`: busca cada noche convocatorias nuevas en la BDNS: estatales, de todas las comunidades autónomas y de ayuntamientos. Los filtros (temas, territorios) están arriba del todo, en `AJUSTES`.
- `scripts/actualizar_ue.py`: busca convocatorias abiertas o próximas de la Unión Europea para pymes, startups y emprendedores (portal Funding & Tenders). Los títulos vienen en inglés.
- `scripts/actualizar_licitaciones.py`: busca licitaciones abiertas (en plazo de presentar oferta) en la Plataforma de Contratación del Sector Público y las guarda en `data/licitaciones.json`.
- `scripts/vigilar_creditos.py`: visita las páginas oficiales de las fichas de tipo «Crédito» y avisa en la web si parecen haber cambiado (`data/vigilancia.json`). Respeta el `robots.txt` de cada sitio: si una web no permite visitas automáticas, no se vigila.
- `.github/workflows/actualizar.yml`: la tarea programada que ejecuta el script y publica la web.
- `fonts/`, `assets/`, `favicon.svg`: fuentes (Fraunces e Inter, licencia OFL) y logos de Subvenly.

## Puesta en marcha
1. Crea un repositorio en GitHub y sube **todo el contenido**, incluida la carpeta oculta `.github`.
2. En el repositorio: **Settings > Pages > Build and deployment > Source: GitHub Actions**.
3. Ve a la pestaña **Actions > Actualizar y publicar > Run workflow**. Es la primera ejecución y sirve de prueba.
4. Cuando termine, abre la dirección que aparece en el paso «deploy» (`https://TU-USUARIO.github.io/NOMBRE/`).

A partir de ahí se ejecuta solo cada noche, a las 03:17 UTC, y también cada vez que cambies algo en `main`.

## Si la primera ejecución falla
Abre la ejecución, entra en el paso **Buscar convocatorias nuevas** y copia el texto del registro. Si llegó a descargar datos, mira también `data/_diagnostico.json`: muestra los campos reales que devuelve la BDNS. Si falla la parte de la UE, mira también `data/_diagnostico_ue.json`. Con eso se ajustan los scripts. Aunque la búsqueda falle, la web se publica con los datos anteriores.

## Cosas a saber
- Para ver la web en tu ordenador, no abras `index.html` con doble clic (el navegador bloquea la carga de los datos). Ejecuta `python -m http.server` dentro de la carpeta y abre `http://localhost:8000`.
- En repositorios públicos, GitHub pausa las tareas programadas si pasan 60 días sin actividad. Si ocurre, actívalas de nuevo en la pestaña Actions.
- **No necesitas instalar ni lanzar Python.** Los scripts se ejecutan solos en los servidores de GitHub cada noche. Python solo hace falta si quieres probarlos en tu ordenador.
- Se automatizan las **subvenciones** (BDNS), las **convocatorias de la UE** y las **licitaciones abiertas**. Los **créditos** (ICF, ICO, Enisa) no tienen ninguna fuente automática: siguen siendo fichas manuales, pero se vigilan sus páginas oficiales y la web avisa cuando algo cambia.
- El test cruza lo que responde la persona (comunidad autónoma, municipio, autónomo o sociedad) con las novedades: muestra primero las de «posible encaje» y oculta las que claramente no encajan. Es un filtro por territorio y tipo de beneficiario, no una garantía: los requisitos concretos (edad, inversión mínima, contratación…) solo están en las fichas que tú validas.
- Las licitaciones no se pueden comprobar contra el test (la solvencia depende de cada pliego): se filtran por sector, importe y zona.
- Los contratos menores no se incluyen: se publican una vez adjudicados, así que ya no se puede concurrir.
- La web muestra las novedades caducadas solo si no se conoce su plazo; las que tienen fecha de cierre pasada desaparecen solas.
- Lo que sale en «Novedades detectadas» no está revisado: pasa a `fichas.json` cuando lo valides.
