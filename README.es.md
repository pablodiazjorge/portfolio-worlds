# portfolio-worlds

[English version](README.md)

El portfolio de Pablo Díaz-Jorge contado de cuatro formas. Cada mundo tiene el mismo contenido (sobre mí, experiencia, proyectos y contacto) y lo recorre con una escena 3D distinta, renderizada con three.js sobre WebGPU y con WebGL 2 como respaldo donde WebGPU no está disponible.

| Tecla | Mundo | Cómo se recorre |
| --- | --- | --- |
| 1 | Atlas | El scroll lleva la cámara por una ruta alpina al amanecer: un campamento por trabajo, los proyectos desde la cresta y el contacto en el observatorio de la cumbre. |
| 2 | Aeris | Un dron en un estudio de producto se despieza en cinco capas, una por trabajo, unidas a su texto con una línea de anotación. |
| 3 | Helios | Una lanzadera sale de un planeta procedural, cruza un anillo por trabajo y atraca en una estación espacial, con telemetría en vivo. |
| 4 | Atrium | Un museo que recorres con un robot: los cuadros son proyectos, los paneles iluminados son trabajos y una guía te lleva a cualquier pieza. |

Las teclas del 1 al 4 cambian de mundo desde cualquier página y el 0 vuelve al inicio. Cada página existe en inglés (`/atlas`) y en castellano (`/es/atlas`), prerenderizada con su título, descripción, imagen Open Graph y enlaces hreflang.

## Tecnologías

- Angular 22 (standalone, zoneless y signals) con prerenderizado estático de las doce rutas
- three.js r186 con `WebGPURenderer` y materiales de nodos TSL; bloom con `RenderPipeline` en Helios
- Lenis para el scroll suave, con anclas por sección que mueven un rig de cámara por fotogramas clave
- Tailwind CSS 4, hojas de estilo por mundo y fuentes variables alojadas en el propio sitio
- Blender 4.5 en modo headless para construir cada modelo desde un script de Python, optimizado con glTF Transform y meshopt

## Comandos

```bash
npm install
npm start              # servidor de desarrollo en http://localhost:4200
npm run build          # sitio estático en dist/portfolio-worlds/browser
npm test               # pruebas unitarias con Vitest
npm run assets         # regenera todos los modelos 3D (necesita Blender 4.5)
npm run assets -- atlas --skip-blender   # vuelve a optimizar un modelo desde su exportación
```

`?webgl` fuerza el backend WebGL 2 y `?quality=low|medium|high` sustituye la detección del dispositivo, útil para probar.

## Pipeline de modelos 3D

Cada modelo es un script de Python determinista en `tools/blender/` que construye la escena con `bpy` y `bmesh` y exporta un GLB. `tools/build-assets.mjs` lanza Blender en modo headless, deduplica, instancia las mallas repetidas, suelda, poda y comprime con meshopt, y falla si un modelo supera su presupuesto de tamaño. Los archivos optimizados de `public/models/` se versionan, así que desplegar no necesita Blender.

| Modelo | Tamaño | Presupuesto |
| --- | --- | --- |
| Valle de Atlas | 2583 KB | 2600 KB |
| Dron de Aeris | 109 KB | 900 KB |
| Monitor de Aeris | 41 KB | 400 KB |
| Estación de Helios | 5847 KB | 18000 KB |
| Museo de Atrium | 5600 KB | 6500 KB |
| Robot de Atrium | 154 KB | 500 KB |

Define `BLENDER_PATH` si Blender no está instalado en `C:/Program Files/Blender Foundation/Blender 4.5/`.

Los scripts también se pueden usar de forma interactiva con [Blender MCP](https://github.com/ahujasid/blender-mcp) si quieres que un agente edite un modelo en vivo: instala el complemento con `uvx mcp-for-blender install-addon`, registra el servidor con `claude mcp add blender uvx mcp-for-blender` y pulsa Connect en la pestaña MCP for Blender del visor 3D. La compilación solo necesita Blender en modo headless.

## Arquitectura

- `src/app/core/engine` gestiona un único renderer y un único canvas que sobreviven a la navegación. Cada mundo monta una `WorldScene` (cargar, construir, actualizar, liberar); el motor compila sus pipelines antes de mostrarla y la libera al salir de la página.
- `src/app/core/scroll` convierte el scroll en una posición de fotograma clave y mantiene la cámara quieta en cada sección mientras se lee. Con movimiento reducido se desactiva el scroll suave y la cámara salta entre paradas.
- `src/app/landings/<mundo>` contiene cada página (el contenido HTML, siempre legible sin WebGL) y su escena.
- `src/app/content` guarda el portfolio en los dos idiomas, tipado para que el castellano mantenga la misma forma que el inglés.

## Despliegue en Vercel

Importa el repositorio como proyecto nuevo. `vercel.json` define el comando de compilación, la carpeta de salida, la caché inmutable de los archivos con hash y algunas cabeceras de seguridad, así que no hace falta tocar nada en el panel. Si el sitio no va a vivir en `https://worlds.pablodiazjorge.com`, cambia `SITE_ORIGIN` en `src/app/core/site.service.ts` para que las URL canónicas y de Open Graph apunten al dominio correcto.

## Créditos

- Personaje robot de Tomás Laulhé (Quaternius), CC0 1.0, tomado de los ejemplos de three.js; ver `tools/vendor/README.md`.
- Fuentes: Instrument Sans, Fraunces, Unbounded, Syne, Michroma y Cormorant Garamond, todas con licencia SIL Open Font License, servidas con Fontsource.
- three.js, Lenis y glTF Transform con sus respectivas licencias.
