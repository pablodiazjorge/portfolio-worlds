import { Portfolio } from './portfolio.model';
import { PORTFOLIO_EN } from './portfolio.en';

const en = PORTFOLIO_EN;
const project = (slug: string) => {
  const found = en.projects.find((p) => p.slug === slug);
  if (!found) throw new Error(`Unknown project ${slug}`);
  return found;
};

export const PORTFOLIO_ES: Portfolio = {
  name: 'Pablo Díaz-Jorge',
  role: 'Software Engineer & AI Engineer',
  focus: 'Agentes de IA, MCP y arquitectura frontend',
  focusAreas: ['Agentes de IA', 'MCP', 'Arquitectura frontend'],
  intro:
    'Diseño y construyo software escalable con un enfoque orientado a la arquitectura y la calidad, y aplico la ingeniería de IA al desarrollo: agentes, MCP y evaluación de lo que aportan.',
  location: 'Valencia, España',
  about: [
    'Lo que empezó en el instituto como un simple experimento se ha convertido en mi vocación. Hoy trabajo como ingeniero de software e ingeniero de IA: diseño y construyo sistemas escalables con un enfoque orientado a la arquitectura, la calidad del diseño y las buenas prácticas de ingeniería, y aplico la inteligencia artificial para mejorar la forma en que se desarrolla el software.',
    'Soy Frontend Engineer en Infoport Valencia, donde creo interfaces accesibles y escalables para la logística portuaria con Angular y TypeScript. En código abierto construyo herramientas para agentes de IA y mido lo que aportan: contribuyo a rea, un proyecto de ingeniería inversa con más de 130.000 estrellas, y en rea-lab medí con un estudio preregistrado qué le aporta a un agente de programación.',
    'Fuera del código suelo hacer deporte: puede que me veas sufrir en el gimnasio o haciendo senderismo por la montaña, y si no, leyendo novelas o sentado en un bar con amigos.',
  ],
  experience: [
    {
      ...en.experience[0],
      period: 'Sept 2025 - Actualidad',
      contract: 'Contrato indefinido - Jornada completa',
      summary:
        'Interfaces accesibles y escalables para la logística portuaria con Angular y TypeScript, con el desarrollo asistido por IA integrado en el flujo de trabajo.',
      description:
        'Contribuyo al desarrollo de soluciones digitales que optimizan la operativa del sector logístico portuario, creando interfaces accesibles, escalables y centradas en el usuario con Angular y TypeScript, apoyándome en tecnologías como SCSS, RxJS y librerías de componentes personalizadas. Integro herramientas de asistencia al desarrollo basadas en IA para acelerar tareas de desarrollo, refactorización y revisión de código, manteniendo altos estándares de calidad. Trabajo en un entorno ágil, en estrecha colaboración con analistas y desarrolladores backend.',
      tech: ['Angular', 'TypeScript', 'SCSS', 'RxJS', 'Signals', 'Kendo UI', 'Web Components', 'Desarrollo asistido por IA'],
      others: ['Scrum', 'Jira', 'Accesibilidad web'],
    },
    {
      ...en.experience[1],
      period: 'Ene 2026 - Actualidad',
      role: 'AI Engineer (código abierto)',
      company: 'Código abierto',
      contract: 'Proyectos propios y contribuciones de código abierto',
      summary:
        'Herramientas para agentes de IA y pruebas de lo que aportan: tres PR fusionadas en rea, el banco de evaluación rea-lab con su estudio preregistrado y dos mods publicados para Claude Code.',
      description:
        'Construyo herramientas para agentes de IA y mido lo que aportan. En rea (más de 130.000 estrellas) tengo tres PR fusionadas, que devolvieron a verde las pruebas reales de Ghidra en Windows y llevaron las de Claude Code y Gemini CLI a Windows nativo, además de una PR abierta en la validación del servidor MCP. En rea-lab monté un entorno reproducible, 40 retos con respuesta conocida y un banco de evaluación en TypeScript; su estudio preregistrado de 70 ejecuciones con Claude Code, calificado sin ningún LLM como juez, mostró que rea no cambiaba la tasa de resolución, duplicaba tiempo y coste, y que todas las evidencias citadas eran auténticas. He publicado dos mods de Claude Code, rea-casebook e impact-radius, con CI en Windows, macOS y Ubuntu.',
      tech: ['TypeScript', 'Node.js', 'Model Context Protocol', 'Claude Code (mods y skills)', 'Evaluación de agentes', 'Angular 22', 'Vitest', 'GitHub Actions'],
      others: ['Código abierto', 'Estudios preregistrados', 'Documentación técnica'],
    },
    {
      ...en.experience[2],
      role: 'Ingeniero de software independiente (I+D en IA y frontend)',
      company: 'Proyectos de código abierto',
      contract: 'Investigación aplicada y desarrollo independiente',
      summary:
        'Cuatro prototipos de código abierto donde la arquitectura frontend se cruza con la ingeniería de IA: matrices de atención, búsqueda semántica, un orquestador de agentes ReAct y un analizador de costes de tokens.',
      description:
        'Investigación aplicada centrada en la convergencia entre la arquitectura de sistemas frontend y la ingeniería de IA. Diseñé y prototipé Attention Matrix Explorer (2023), una visualización interactiva de la atención de transformers con D3.js y Web Workers; Semantic Search Engine (2024), con PostgreSQL, pgvector e indexación HNSW; Cognitive Agent Orchestrator (2024-2025), con patrón ReAct y streaming en tiempo real vía SSE; y Token Cost Analyzer (2025), con tiktoken en WebAssembly.',
      others: ['Código abierto', 'I+D', 'Documentación técnica'],
    },
    {
      ...en.experience[3],
      contract: 'Contrato de prácticas - Jornada completa',
      summary:
        'Servicios REST y un módulo interactivo de visualización de datos para una plataforma corporativa de gestión de personal.',
      description:
        'Colaboré en el desarrollo de principio a fin de una solución corporativa de gestión de personal en NTT DATA Valencia. Implementé servicios REST en el backend y desarrollé un módulo interactivo en el frontend centrado en la visualización dinámica de datos estructurados, manteniendo el código bajo los estándares de calidad del equipo.',
    },
    {
      ...en.experience[4],
      role: 'Analista de datos',
      contract: 'Contrato de prácticas - Jornada completa',
      summary: 'Análisis y diseño de bases de datos para los planes retributivos de dos unidades de negocio.',
      description:
        'Análisis y diseño de base de datos para el plan retributivo de las unidades de negocio de Consultoría y Sistemas de Información y de Automatización y Control.',
    },
  ],
  projects: [
    {
      ...project('rea-lab'),
      tagline: 'Un laboratorio de ingeniería inversa para agentes de IA, con un estudio preregistrado de 70 ejecuciones.',
      description:
        'Laboratorio público de ingeniería inversa con agentes de IA en Windows, sobre rea y Ghidra. Entorno reproducible con versiones y hashes fijados, 40 retos en C con respuesta conocida y un banco de evaluación en TypeScript que aísla cada ejecución y califica sin ningún LLM como juez. Su primer estudio, preregistrado y con 70 ejecuciones de Claude Code, mostró que rea no cambiaba la tasa de resolución (28 de 30 con y sin), duplicaba tiempo y coste, y que las 80 evidencias citadas eran auténticas.',
      tech: ['TypeScript', 'Node.js', 'Model Context Protocol', 'Claude Code', 'Ghidra', 'Evaluación de agentes', 'Estadística (Wilson, McNemar)'],
    },
    {
      ...project('rea-casebook'),
      tagline: 'Un mod de Claude Code que muestra en directo la evidencia que rea entrega al agente.',
      description:
        'Mod de Claude Code que muestra en un panel, en directo, la evidencia que rea entrega al agente: la espera de Ghidra, los hallazgos, las preguntas abiertas y la línea de tiempo de la evidencia. Los hallazgos se registran con una herramienta que rechaza cualquier evidence_id que rea no haya entregado, y la sesión se exporta a Markdown o a un artifact. TypeScript, 43 tests y CI en Windows, macOS y Ubuntu.',
      tech: ['TypeScript', 'Claude Code (mod)', 'Model Context Protocol', 'Vitest', 'GitHub Actions (3 sistemas)'],
    },
    {
      ...project('impact-radius'),
      tagline: 'Un mod de Claude Code que retiene las órdenes de consola arriesgadas hasta que las apruebas.',
      description:
        'Mod de Claude Code que retiene las órdenes de consola arriesgadas antes de ejecutarlas (rm -rf, git reset --hard, push forzados, migraciones, instalaciones globales, curl | sh), enseña lo que cambiarían y espera a que pulses Ejecutar o Cancelar. Funciona con Bash y PowerShell en Windows, macOS y Linux, en inglés y en castellano, con contraste AAA y CI en tres sistemas.',
      tech: ['TypeScript', 'Claude Code (mod)', 'Bash y PowerShell', 'Accesibilidad AAA', 'i18n EN/ES'],
    },
    {
      ...project('candle-ai'),
      tagline: 'Análisis de velas en el navegador con un motor de confluencia bayesiano.',
      description:
        'Gráficos de velas y análisis técnico de calidad profesional que se ejecutan por completo en el navegador: sin cuentas, sin suscripciones y sin que tus datos salgan de tu máquina. Un motor de confluencia bayesiano determinista puntúa más de 15 patrones en 7 jerarquías de señales, y una capa de IA opcional explica el análisis en lenguaje natural sin anularlo nunca. Angular 22 (zoneless y Signals), Lightweight Charts v5, Web Workers, caché IndexedDB, exportación a Pine Script v5 y 165 tests.',
      tech: ['Angular 22 (Zoneless + Signals)', 'Motor de confluencia bayesiano', 'Web Workers', 'Lightweight Charts v5', 'Integración LLM', 'Exportación Pine Script v5', 'Playwright + Vitest'],
    },
    {
      ...project('prompt-forge'),
      tagline: 'Memoria compartida y revisada para los agentes de IA de un equipo.',
      description:
        'Memoria compartida y revisada para los agentes de IA de un equipo. Cuando la misma lección aparece en dos o más personas, un paso de curación la convierte en una regla breve que leen los agentes de todo el equipo, sea Claude Code, GitHub Copilot, Codex, Cursor o Gemini CLI. La promoción pasa por una pull request normal, así que siempre la revisa una persona. Solo Markdown y git, con instaladores para Bash y PowerShell y CI en Linux, macOS y Windows.',
      tech: ['Agent Skills', 'AGENTS.md', 'Memoria compartida de equipo', 'Revisión por pull request', 'Multiagente', 'CI en 3 sistemas'],
    },
    {
      ...project('gym-log'),
      tagline: 'Una aplicación mobile-first para entrenar con objetivos de progresión calculados.',
      description:
        'Aplicación mobile-first para registrar entrenamientos en el gimnasio: objetivos de progresión calculados para la siguiente sesión (doble progresión ajustada por RIR), análisis de volumen y estancamiento, exportación de informes y todos los datos en el propio dispositivo. Angular 22 con Signals y zoneless, Tailwind CSS 4, Chart.js y Vitest.',
    },
    {
      ...project('test-maker'),
      tagline: 'Una plataforma de exámenes segura con bancos de preguntas cifrados.',
      description:
        'Plataforma de exámenes segura con acceso multiusuario y bancos de preguntas cifrados (AES-256-CBC). Desarrollada con Angular 21 (Signals) y una API serverless en Vercel, con autenticación, sesiones por temas, atajos de teclado, exportación de resultados a PDF, internacionalización ES/EN y tests unitarios con Vitest.',
    },
    {
      ...project('token-cost-analyzer'),
      tagline: 'Coste y tokenización de prompts para LLM, calculados en el navegador con WebAssembly.',
      description:
        'Analizador de costes y tokenización de prompts para LLM, por completo en el lado del cliente. Ejecuta tiktoken en WebAssembly dentro de un Web Worker para tokenizar sin bloquear la interfaz, visualiza la distribución de tokens con D3.js y estima el coste para 10 modelos. Angular 19 con detección de cambios zoneless.',
    },
    {
      ...project('cognitive-agent-orchestrator'),
      tagline: 'Un orquestador de agentes ReAct que transmite cada pensamiento por SSE.',
      description:
        'Orquestador de agentes cognitivos con patrón ReAct (Reasoning + Acting) y streaming en tiempo real mediante Server-Sent Events. Una máquina de estados determinista razona, invoca herramientas, observa resultados y transmite cada pensamiento a un frontend Angular 18 zoneless, con modo simulado y Ollama + Qwen 2.5 Coder.',
    },
    {
      ...project('semantic-search-engine'),
      tagline: 'Búsqueda semántica sobre PostgreSQL con pgvector e indexación HNSW.',
      description:
        'Motor de búsqueda semántica de pila completa con almacenamiento vectorial en PostgreSQL mediante pgvector. Búsqueda por similitud coseno con indexación HNSW sobre embeddings de 384 dimensiones, backend con Java 21 y Spring Boot, y frontend con Angular 17 y carga diferida de resultados mediante @defer.',
    },
    {
      ...project('attention-matrix-explorer'),
      tagline: 'Mapas de calor interactivos de la atención de un transformer con D3.js.',
      description:
        'Visualizador interactivo de matrices de atención de transformers (Query, Key, Value) inspirado en "Attention Is All You Need". Mapas de calor en tiempo real con D3.js y cálculos matriciales (softmax, transpuesta, multiplicación) en un Web Worker dedicado. Angular 16 con Signals en vista previa.',
    },
    {
      ...project('portfolio'),
      title: 'Mi portfolio',
      tagline: 'La edición clásica de este portfolio, con SSR y dos idiomas.',
      description:
        'Portfolio personal construido con Angular y Tailwind CSS 4, con prerenderizado por idioma, i18n (ES/EN), tema claro y oscuro y carga diferida para una experiencia rápida y accesible.',
      tech: ['Angular', 'SSR y prerenderizado', 'Tailwind CSS 4', 'ngx-translate', 'PostCSS'],
    },
    {
      ...project('palaze'),
      tagline: 'Una biblioteca de componentes web hecha con Stencil.js, mi trabajo de fin de grado.',
      description:
        'Biblioteca de componentes web nativos desarrollada con Stencil.js. Componentes ligeros, fáciles de implementar y con carga rápida, instalables vía npm o CDN y con documentación propia. Surgió como trabajo de fin de grado para adentrarme en el desarrollo web.',
    },
  ],
  contact: {
    ...en.contact,
    cv: 'docs/cv-es.pdf',
  },
};
