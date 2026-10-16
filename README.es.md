# portfolio-worlds

[English version](README.md)

Mi portfolio contado de cuatro formas. Cada mundo tiene el mismo contenido (sobre mí, experiencia, proyectos y contacto) y lo recorre con una escena 3D distinta, renderizada con three.js sobre WebGPU y con WebGL 2 como respaldo donde WebGPU no está disponible.

| Tecla | Mundo | Cómo se recorre |
| --- | --- | --- |
| 1 | Atlas | El scroll lleva la cámara por una ruta alpina al amanecer: un campamento por trabajo, los proyectos desde la cresta y el contacto en el observatorio de la cumbre. |
| 2 | Aeris | Un dron de carga cruza un estudio oscuro de parada en parada, una por trabajo, llevando colgado de una cadena el monitor donde empezó todo. |
| 3 | Helios | Una lanzadera sale de la Tierra, dibujada con imágenes de la NASA, pasa una baliza por trabajo y atraca en una estación espacial, con telemetría en vivo. |
| 4 | Atrium | Un museo que recorres con un robot: los cuadros son proyectos, las vitrinas guardan los trabajos, la estatua habla de mí y el atril de la entrada es el contacto; una guía te lleva a cualquier pieza. |

Las teclas del 1 al 4 cambian de mundo desde cualquier página y el 0 vuelve al inicio. Cada página existe en inglés (`/atlas`) y en castellano (`/es/atlas`), prerenderizada con su título, descripción, imagen Open Graph y enlaces hreflang.

## Una instantánea, no el portfolio vivo

Este sitio es un experimento técnico, no el portfolio que mantengo al día. Congela mi perfil a octubre de 2026 y no lo seguirá a partir de aquí; la versión vigente está en [pablodiazjorge.com](https://www.pablodiazjorge.com/). Lo construí para probar, sobre una entrega real, una forma de trabajar: WebGPU y TSL en producción, una cadena de activos que ejecuta Blender desde guiones y, sobre todo, el desarrollo con agentes de IA bajo mi dirección, mezclando modelos de generación locales con alojados, servidores MCP y las prácticas que hacen revisable ese trabajo. El resultado queda tal cual, con el estado de las herramientas y de mi experiencia en esa fecha.

## Cómo se ha hecho

El sitio se ha desarrollado de principio a fin con agentes de IA de programación (Claude Code) bajo mi dirección. Elegí los conceptos y las imágenes de referencia, revisé cada captura que producían los agentes, me quedé con lo que funcionaba y descarté lo que no (una estación generada desde una imagen perdió frente a una dibujada por guion; una lanzadera dibujada por guion perdió frente a la generada), e hice cada commit a mano a partir de los mensajes que los agentes preparaban. Los agentes escribieron el código y los guiones de Blender, adaptaron los textos del portfolio clásico y trabajaron con:

- Blender 4.5 en modo headless para la cadena de activos, y [Blender MCP](https://github.com/ahujasid/blender-mcp) para modelar en vivo en mi Blender abierto, comprobando cada pasada contra la imagen de referencia con renders desde cámaras fijas.
- Modelos de generación locales junto a Claude: Qwen-Image a través de ComfyUI para las imágenes de concepto y Microsoft TRELLIS.2 para pasar de imagen a 3D, los dos en mi GPU. De esa cadena salen la lanzadera y la boya de Helios y la estatua, los estandartes y los apliques de Atrium; la estación, el robot y todo lo demás se dibujan por guion.
- Playwright por MCP para verificar cada cambio en un navegador real: capturas del recorrido en cada parada, recortes a 2x antes y después, revisión de consola y red, y build de producción antes de cada commit.
- Solo activos CC0 o de dominio público: texturas de Poly Haven y ambientCG, un modelo de Poly Haven e imágenes de la NASA para la Tierra.
- Prácticas: especificaciones escritas en modo plan, una auditoría independiente del sombreador de la estación por un segundo agente, un registro de commits revisado, hojas de verificación guardadas como registro del proceso y una memoria persistente de lecciones entre sesiones.

## Tecnologías

- Angular 22 (standalone, zoneless y signals) con prerenderizado estático de las diez rutas
- three.js r186 con `WebGPURenderer` y materiales de nodos TSL; en Helios, un bloom selectivo con `RenderPipeline` que solo recoge lo que emite luz
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

Los scripts también se pueden usar de forma interactiva con [Blender MCP](https://github.com/ahujasid/blender-mcp), que es como se modeló la estación de Helios: instala el complemento con `uvx mcp-for-blender install-addon`, registra el servidor con `claude mcp add blender uvx mcp-for-blender` y pulsa Connect en la pestaña MCP for Blender del visor 3D. La compilación solo necesita Blender en modo headless.

### Activos generados y de terceros

- `tools/assets/trellis/` guarda los activos generados con TRELLIS.2 a partir de imágenes de Qwen-Image (la lanzadera y la boya de Helios; la estatua, los estandartes y los apliques de Atrium), y su README explica cómo se preparó cada uno. TRELLIS.2 es MIT, pero incluye componentes de NVIDIA con licencia solo para investigación y evaluación, así que estos activos no están a la venta: son decoración de un portfolio personal.
- `tools/assets/polyhaven/` guarda el modelo Television 02 (CC0).
- `public/textures/atrium/` y `public/textures/helios/` guardan las texturas (Poly Haven y ambientCG, CC0) y los mapas de la Tierra de la NASA (dominio público), cada uno con su fuente en un README.

## Arquitectura

- `src/app/core/engine` gestiona un único renderer y un único canvas que sobreviven a la navegación. Cada mundo monta una `WorldScene` (cargar, construir, actualizar, liberar); el motor compila sus pipelines antes de mostrarla y la libera al salir de la página.
- `src/app/core/scroll` convierte el scroll en una posición de fotograma clave y mantiene la cámara quieta en cada sección mientras se lee. Con movimiento reducido se desactiva el scroll suave y la cámara salta entre paradas.
- `src/app/landings/<mundo>` contiene cada página (el contenido HTML, siempre legible sin WebGL) y su escena.
- `src/app/content` guarda el portfolio en los dos idiomas, tipado para que el castellano mantenga la misma forma que el inglés.

## Despliegue en Vercel

Importa el repositorio como proyecto nuevo. `vercel.json` define el comando de compilación, la carpeta de salida, la caché inmutable de los archivos con hash y algunas cabeceras de seguridad, así que no hace falta tocar nada en el panel. Si el sitio no va a vivir en `https://worlds.pablodiazjorge.com`, cambia `SITE_ORIGIN` en `src/app/core/site.service.ts` para que las URL canónicas y de Open Graph apunten al dominio correcto.

## Créditos

- Texturas: Marble 01 y Blue Metal Plate de Rob Tuytel y Dark Wood de Dario Barresi, Dimitrios Savva y Rico Cilliers (Poly Haven, CC0); Marble 014 y Fabric 061 (ambientCG, CC0). Modelo: Television 02 de Benny Weimer (Poly Haven, CC0).
- Tierra: imágenes Blue Marble, Black Marble y de nubes de la NASA, de dominio público.
- Activos generados: imágenes de concepto de Qwen-Image (Apache-2.0) y mallas de Microsoft TRELLIS.2 (MIT, con componentes de NVIDIA solo para investigación y evaluación); ver `tools/assets/trellis/README.md`.
- Fuentes: Instrument Sans, Fraunces, Unbounded, Syne, Michroma y Cormorant Garamond, todas con licencia SIL Open Font License, servidas con Fontsource.
- three.js, Lenis y glTF Transform con sus respectivas licencias.
