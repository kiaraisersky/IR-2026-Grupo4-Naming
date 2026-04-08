# IR-2026-Grupo4-Naming
# IR-2026-Grupo4-Tema13 — Test de denominación fonológica (digital)

**Grupo 4 — Cognición y lenguaje — Tema 13**  
Trabajo práctico — Ingeniería de la Rehabilitación (UNSAM).

## Qué mide el test

Evalúa el **acceso léxico-fonológico** en adultos post-ACV mediante **denominación por confrontación visual con elección forzada**: se muestra una imagen de un objeto y el usuario debe elegir la palabra correcta entre **cuatro opciones fonológicamente parecidas**.  
Se registran de forma objetiva la **exactitud (accuracy)**, el **tiempo de reacción** por ensayo, el **tipo de error** (fonológico, no relacionado, omisión) y la **variabilidad** de los tiempos. La salida incluye un **desglose clínico orientativo** (`clinical_breakdown` en JSON) y un resumen breve compatible con versiones previas (`interpretacion_orientativa`). **No sustituye el diagnóstico neuropsicológico formal.**

## Población objetivo

Adultos con **secuela de accidente cerebrovascular (ACV)** y posibles alteraciones del lenguaje compatibles con **afasia / anomia**, que puedan comprender instrucciones simples y responder con un clic o teclas 1–4, con demanda motora reducida respecto de la denominación oral espontánea.

## Cómo instalar y ejecutar (≈ 2 minutos)

1. Clonar o descargar este repositorio en una carpeta local.
2. Tener instalado **Python 3.10 o superior**.
3. En la carpeta del proyecto, instalar dependencias declaradas (aunque no haya paquetes de PyPI, el docente puede validar el entorno):

```bash
pip install -r requirements.txt
```

4. Ejecutar la aplicación:

```bash
python main.py
```

Opcional — carpeta de resultados:

```bash
python main.py --results-dir ./results
```

**Linux:** si falta Tkinter: `sudo apt install python3-tk`

## Rutas relativas (importante)

Las imágenes y recursos se resuelven **respecto de la carpeta del proyecto** (donde está `main.py`), por ejemplo `assets/images/...`. **No se usan rutas absolutas** tipo `C:/Users/...` en el código de estímulos.

## Robustez y datos

- Al **completar un bloque** de ensayos (10 ítems por nivel), los resultados se **agregan** a un JSON por paciente en `results/<id_paciente>.json`.
- Si el usuario **cierra la ventana o el programa antes de terminar el bloque**, **ese bloque no se exporta** (no hay guardado parcial ensayo a ensayo). Los bloques ya guardados en sesiones anteriores **no se borran**.

## Interfaz

Pensada para **pacientes post-ACV**: alto contraste, tipografía grande, botones amplios, pocas opciones (cuatro), instrucciones breves, misma apariencia de fondo en todo el flujo y resultados numéricos detallados solo en la pantalla **“Ver resultados (profesional)”**.

## Estructura relevante

```text
├── main.py              # Aplicación completa (único archivo necesario)
├── requirements.txt
├── README.md
├── assets/images/       # Imágenes PNG de estímulos (rutas relativas)
├── results/             # JSON generados (no versionar datos reales de pacientes)
└── tests/test_metrics.py
```

## Tests automáticos

```bash
python -m unittest discover -s tests
```

## JSON de salida (por evaluación)

Cada elemento de `evaluaciones` incluye, entre otros: `accuracy_pct`, `reaction_time_mean_ms`, `reaction_time_std_ms`, `error_summary`, **`clinical_breakdown`** (dominios: exactitud, RT, errores con % sobre total, variabilidad, criterio global por peor dominio) e **`interpretacion_orientativa`** (`categoria`, `mensaje`).

## Autoras

Cavallaro Giuliana, Isersky Kiara Morena, Bruno Julieta, Pozzatti María Lucila.
