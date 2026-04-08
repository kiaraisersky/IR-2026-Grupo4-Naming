"""
Test de Denominación Fonológica (post-ACV) — aplicación monolítica.

Contenido de este archivo (orden de lectura):
  1) Constantes de apariencia y clínicas (umbrales orientativos).
  2) Modelos de datos: estímulo y resultado por ensayo.
  3) Lista STIMULI (45 ítems) y reparto por dificultad (15+15+15).
  4) Funciones puras: tipo de error, métricas, build_clinical_breakdown() e interpretación orientativa.
  5) Utilidades: logging, fechas, rutas de imagen, exportación JSON.
  6) Interfaz Tkinter (clase NamingApp): pantallas y flujo del usuario.

Flujo del usuario (NamingApp):
  A) Bienvenida: datos del paciente + dificultad → INICIAR EVALUACIÓN.
  B) Diapositiva de explicación → CONTINUAR AL TEST.
  C) Ensayos: imagen + 4 opciones (orden aleatorio); mide tiempo de respuesta.
  D) Fin de bloque: guarda JSON → pantalla con 3 opciones (otro nivel /
     finalizar / resultados para profesional).
  E) Resultados detallados solo en la pantalla "profesional".

Estilo visual alineado al test Stroop del mismo grupo (Calibri, fondo gris
único, botón de acento magenta).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import time
import tkinter as tk
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import pstdev
from typing import Any, Optional

from tkinter import font as tkfont
from tkinter import messagebox

# ---------------------------------------------------------------------------
# Constantes de apariencia (alineadas al Stroop del grupo)
# ---------------------------------------------------------------------------

# Fondo único en todo el flujo (accesibilidad: mismo contexto visual).
FORM_BG = "#4A4343"  # Misma apariencia en todo el test (bienvenida, explicación, ensayos, fin)
PLACEHOLDER_BG = "#333333"  # Marco de imagen ausente (contraste sobre FORM_BG)
FG_DEFAULT = "#FFFFFF"
ACCENT_BTN = "#EF00CB"
FONT_FAMILY = "Calibri"

WINDOW_TITLE = "Denominación Fonológica (post-ACV)"
WINDOW_SIZE = "1200x900"

# Botones de opción (legibles sobre negro; distintos del CTA magenta si se prefiere)
OPTION_BTN_BG = "#0055CC"
OPTION_BTN_FG = "#FFFFFF"

CORRECT_FEEDBACK_COLOR = "#2E7D32"
INCORRECT_FEEDBACK_COLOR = "#C62828"

DEFAULT_TEST_NAME = "naming"
DEFAULT_METRIC_UNIT = "accuracy_pct"
DIFFICULTY_LEVELS = ("facil", "medio", "dificil")

# Mensaje legal/clínico (screening).
SCREENING_DISCLAIMER = (
    "Herramienta de screening; no reemplaza el diagnóstico clínico ni la evaluación neuropsicológica formal."
)

# ---------------------------------------------------------------------------
# Umbrales de interpretación clínica automática (TP Ingeniería Biomédica / post-ACV)
# Toda la lógica nueva está en: build_clinical_breakdown() y funciones domain_*.
# ---------------------------------------------------------------------------

# Exactitud (% aciertos)
ACC_NORMAL_MIN = 90.0
ACC_LIMITE_LOW = 85.0
ACC_LEVE_LOW = 70.0
ACC_MODERADA_LOW = 50.0

# Tiempo de reacción medio (ms). Futuro: ajustar por edad (p. ej. normas por franja etaria).
RT_NORMAL_MAX_MS = 1000.0
RT_LEVE_MAX_MS = 1500.0
RT_MODERADO_MAX_MS = 2000.0

# Errores: % sobre total de ensayos (fonológicos + no relacionados + omisiones)
ERR_NORMAL_MAX_PCT = 10.0
ERR_LEVE_MAX_PCT = 20.0

# Variabilidad (desvío estándar de RT en ms)
VAR_NORMAL_MAX_MS = 120.0
VAR_LEVE_MAX_MS = 150.0

# Rango interno para comparar "peor dominio" (mayor = peor). No se exporta en JSON.
_RANK_ACC = {"normal": 0, "límite": 1, "alteración leve": 2, "alteración moderada": 3, "alteración severa": 4}
_RANK_RT = {"normal": 0, "leve": 2, "moderado": 3, "severo": 4}
_RANK_ERR = {"normal": 0, "leve": 2, "patológico": 4}
_RANK_VAR = {"normal": 0, "leve": 1, "alterado": 3}

# Orden de desempate si dos dominios comparten el mismo rango (el primero en la lista gana).
GLOBAL_TIEBREAK_KEYS = ("tiempo_reaccion", "errores", "variabilidad", "accuracy")

OPTION_BUTTON_WIDTH = 22
OPTION_BUTTON_HEIGHT = 1
IMAGE_FRAME_MAX = 460

LOG_LEVEL = "INFO"

# Raíz del proyecto = carpeta donde está este archivo
BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"

LOGGER = logging.getLogger("denominacion_fonologica")


# ---------------------------------------------------------------------------
# Modelos de datos (estímulo fijo + resultado de cada clic)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NamingStimulus:
    image_path: str
    target: str
    options: list[str]
    phonological_distractors: list[str]


@dataclass
class TrialResult:
    trial_index: int
    image_path: str
    target: str
    options: list[str]
    selected: str | None
    correct: bool
    error_type: str
    reaction_time_ms: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Estímulos: 45 ítems en orden fijo → 0–14 fácil, 15–29 medio, 30–44 difícil
# ---------------------------------------------------------------------------

STIMULI: list[NamingStimulus] = [
    NamingStimulus(
        image_path="assets/images/pato.png",
        target="pato",
        options=["pato", "plato", "dato", "gato"],
        phonological_distractors=["plato", "dato"],
    ),
    NamingStimulus(
        image_path="assets/images/casa.png",
        target="casa",
        options=["casa", "tasa", "cama", "caza"],
        phonological_distractors=["tasa", "caza"],
    ),
    NamingStimulus(
        image_path="assets/images/mesa.png",
        target="mesa",
        options=["mesa", "pesa", "misa", "masa"],
        phonological_distractors=["pesa", "masa"],
    ),
    NamingStimulus(
        image_path="assets/images/luna.png",
        target="luna",
        options=["luna", "lana", "lupa", "cuna"],
        phonological_distractors=["lana", "cuna"],
    ),
    NamingStimulus(
        image_path="assets/images/perro.png",
        target="perro",
        options=["perro", "cerro", "pero", "pelo"],
        phonological_distractors=["cerro", "pero"],
    ),
    NamingStimulus(
        image_path="assets/images/gato.png",
        target="gato",
        options=["gato", "pato", "dato", "gallo"],
        phonological_distractors=["pato", "dato"],
    ),
    NamingStimulus(
        image_path="assets/images/silla.png",
        target="silla",
        options=["silla", "villa", "sello", "silo"],
        phonological_distractors=["villa"],
    ),
    NamingStimulus(
        image_path="assets/images/pan.png",
        target="pan",
        options=["pan", "van", "tan", "paz"],
        phonological_distractors=["van", "tan"],
    ),
    NamingStimulus(
        image_path="assets/images/sol.png",
        target="sol",
        options=["sol", "sal", "son", "col"],
        phonological_distractors=["sal", "son"],
    ),
    NamingStimulus(
        image_path="assets/images/flor.png",
        target="flor",
        options=["flor", "color", "flan", "flar"],
        phonological_distractors=["flan"],
    ),
    # Fácil (continuación 10–14)
    NamingStimulus(
        image_path="assets/images/pez.png",
        target="pez",
        options=["pez", "pecho", "vez", "tez"],
        phonological_distractors=["vez", "tez"],
    ),
    NamingStimulus(
        image_path="assets/images/taza.png",
        target="taza",
        options=["taza", "tasa", "raza", "tata"],
        phonological_distractors=["tasa", "raza"],
    ),
    NamingStimulus(
        image_path="assets/images/sopa.png",
        target="sopa",
        options=["sopa", "copa", "sapa", "sapo"],
        phonological_distractors=["copa", "sapo"],
    ),
    NamingStimulus(
        image_path="assets/images/pelo.png",
        target="pelo",
        options=["pelo", "velo", "celo", "pero"],
        phonological_distractors=["velo", "celo"],
    ),
    NamingStimulus(
        image_path="assets/images/tren.png",
        target="tren",
        options=["tren", "tres", "fren", "treno"],
        phonological_distractors=["tres", "fren"],
    ),
    # Medio (15–29)
    NamingStimulus(
        image_path="assets/images/libro.png",
        target="libro",
        options=["libro", "litro", "liso", "libre"],
        phonological_distractors=["litro", "libre"],
    ),
    NamingStimulus(
        image_path="assets/images/coche.png",
        target="coche",
        options=["coche", "corte", "conte", "cosa"],
        phonological_distractors=["corte", "conte"],
    ),
    NamingStimulus(
        image_path="assets/images/vaso.png",
        target="vaso",
        options=["vaso", "paso", "beso", "vaca"],
        phonological_distractors=["paso", "beso"],
    ),
    NamingStimulus(
        image_path="assets/images/dedo.png",
        target="dedo",
        options=["dedo", "pedo", "dado", "peto"],
        phonological_distractors=["pedo", "dado"],
    ),
    NamingStimulus(
        image_path="assets/images/boca.png",
        target="boca",
        options=["boca", "poca", "bota", "oca"],
        phonological_distractors=["poca", "bota"],
    ),
    NamingStimulus(
        image_path="assets/images/mano.png",
        target="mano",
        options=["mano", "mono", "malo", "mapa"],
        phonological_distractors=["mono", "malo"],
    ),
    NamingStimulus(
        image_path="assets/images/ojo.png",
        target="ojo",
        options=["ojo", "oso", "hoja", "oto"],
        phonological_distractors=["oso"],
    ),
    NamingStimulus(
        image_path="assets/images/pie.png",
        target="pie",
        options=["pie", "bie", "tie", "piel"],
        phonological_distractors=["tie", "piel"],
    ),
    NamingStimulus(
        image_path="assets/images/reloj.png",
        target="reloj",
        options=["reloj", "rojo", "ramon", "rol"],
        phonological_distractors=["rojo"],
    ),
    NamingStimulus(
        image_path="assets/images/puerta.png",
        target="puerta",
        options=["puerta", "huerta", "puerto", "puebla"],
        phonological_distractors=["huerta", "puerto"],
    ),
    NamingStimulus(
        image_path="assets/images/pelota.png",
        target="pelota",
        options=["pelota", "pelado", "pleota", "peluda"],
        phonological_distractors=["pelado", "pleota"],
    ),
    NamingStimulus(
        image_path="assets/images/ventana.png",
        target="ventana",
        options=["ventana", "centena", "betana", "mentira"],
        phonological_distractors=["centena", "betana"],
    ),
    NamingStimulus(
        image_path="assets/images/camisa.png",
        target="camisa",
        options=["camisa", "tamiza", "comisa", "camello"],
        phonological_distractors=["tamiza", "comisa"],
    ),
    NamingStimulus(
        image_path="assets/images/botella.png",
        target="botella",
        options=["botella", "batalla", "botillo", "botijo"],
        phonological_distractors=["batalla", "botillo"],
    ),
    NamingStimulus(
        image_path="assets/images/escalera.png",
        target="escalera",
        options=["escalera", "esfera", "gallera", "esqui"],
        phonological_distractors=["esfera", "gallera"],
    ),
    # Difícil (30–44)
    NamingStimulus(
        image_path="assets/images/agua.png",
        target="agua",
        options=["agua", "aguja", "haga", "fana"],
        phonological_distractors=["aguja"],
    ),
    NamingStimulus(
        image_path="assets/images/cuchara.png",
        target="cuchara",
        options=["cuchara", "cara", "cuchillo", "cucharacha"],
        phonological_distractors=["cara", "cucharacha"],
    ),
    NamingStimulus(
        image_path="assets/images/auto.png",
        target="auto",
        options=["auto", "alto", "acto", "aula"],
        phonological_distractors=["alto", "acto"],
    ),
    NamingStimulus(
        image_path="assets/images/telefono.png",
        target="telefono",
        options=["telefono", "telon", "televisor", "templado"],
        phonological_distractors=["telon"],
    ),
    NamingStimulus(
        image_path="assets/images/zapato.png",
        target="zapato",
        options=["zapato", "plato", "dato", "zapito"],
        phonological_distractors=["zapito"],
    ),
    NamingStimulus(
        image_path="assets/images/cama.png",
        target="cama",
        options=["cama", "cana", "coma", "cima"],
        phonological_distractors=["cana", "coma"],
    ),
    NamingStimulus(
        image_path="assets/images/llave.png",
        target="llave",
        options=["llave", "llama", "nave", "lave"],
        phonological_distractors=["llama", "nave"],
    ),
    NamingStimulus(
        image_path="assets/images/bolsa.png",
        target="bolsa",
        options=["bolsa", "balsa", "bolso", "bomba"],
        phonological_distractors=["balsa", "bolso"],
    ),
    NamingStimulus(
        image_path="assets/images/cuchillo.png",
        target="cuchillo",
        options=["cuchillo", "cuello", "cuchara", "culillo"],
        phonological_distractors=["cuello"],
    ),
    NamingStimulus(
        image_path="assets/images/espejo.png",
        target="espejo",
        options=["espejo", "conejo", "espojo", "espeja"],
        phonological_distractors=["espeja"],
    ),
    NamingStimulus(
        image_path="assets/images/mariposa.png",
        target="mariposa",
        options=["mariposa", "bariposa", "marposa", "mariquita"],
        phonological_distractors=["bariposa", "mariquita"],
    ),
    NamingStimulus(
        image_path="assets/images/paraguas.png",
        target="paraguas",
        options=["paraguas", "baraguas", "parapeto", "faraguas"],
        phonological_distractors=["baraguas", "parapeto"],
    ),
    NamingStimulus(
        image_path="assets/images/termometro.png",
        target="termometro",
        options=["termometro", "termostato", "demometro", "termometra"],
        phonological_distractors=["termostato", "demometro"],
    ),
    NamingStimulus(
        image_path="assets/images/biblioteca.png",
        target="biblioteca",
        options=["biblioteca", "bibliografia", "vivlioteca", "bibliopeya"],
        phonological_distractors=["bibliografia", "bibliopeya"],
    ),
    NamingStimulus(
        image_path="assets/images/ambulancia.png",
        target="ambulancia",
        options=["ambulancia", "abundancia", "ampulancia", "ambulante"],
        phonological_distractors=["abundancia", "ampulancia"],
    ),
]

for _st in STIMULI:
    if len(_st.options) != len(set(_st.options)):
        raise ValueError(f"Cada estímulo debe tener 4 opciones distintas (repetición en «{_st.target}»).")


def get_stimuli_by_difficulty(level: str) -> list[NamingStimulus]:
    """
    Devuelve 15 estímulos según el nivel elegido:
    - fácil: índices 0–14
    - medio: índices 15–29
    - difícil: índices 30–44
    """
    normalized = level.lower().strip()
    if normalized == "facil":
        return STIMULI[:15]
    if normalized == "medio":
        return STIMULI[15:30]
    if normalized == "dificil":
        return STIMULI[30:45]
    raise ValueError(f"Dificultad invalida: {level}")


# ---------------------------------------------------------------------------
# Lógica de ensayo y métricas (sin Tkinter; fácil de testear)
# ---------------------------------------------------------------------------


def classify_error(selected: str | None, stimulus: NamingStimulus) -> str:
    # Los distractores fonológicos vienen definidos a mano en cada estímulo (sin ASR).
    if selected is None:
        return "omision"
    if selected == stimulus.target:
        return "correct"
    if selected in stimulus.phonological_distractors:
        return "fonologico"
    return "no_relacionado"


def is_correct(selected: str | None, stimulus: NamingStimulus) -> bool:
    return selected == stimulus.target


def calculate_accuracy_pct(results: list[TrialResult]) -> float:
    if not results:
        return 0.0
    correct = sum(1 for item in results if item.correct)
    return round((correct / len(results)) * 100, 2)


def calculate_reaction_time_mean_ms(results: list[TrialResult]) -> float:
    reaction_times = [item.reaction_time_ms for item in results if item.reaction_time_ms is not None]
    if not reaction_times:
        return 0.0
    return round(sum(reaction_times) / len(reaction_times), 2)


def summarize_errors(results: list[TrialResult]) -> dict[str, int]:
    base = {"fonologico": 0, "no_relacionado": 0, "omision": 0}
    counts = Counter(item.error_type for item in results if item.error_type in base)
    for key in base:
        base[key] = counts.get(key, 0)
    return base


def calculate_reaction_time_std_ms(results: list[TrialResult]) -> float:
    reaction_times = [item.reaction_time_ms for item in results if item.reaction_time_ms is not None]
    if len(reaction_times) < 2:
        return 0.0
    return round(pstdev(reaction_times), 2)


def count_valid_reaction_times(results: list[TrialResult]) -> int:
    return sum(1 for item in results if item.reaction_time_ms is not None)


# --- Dominios clínicos (interpretación automática; criterios del TP) ---


def _classify_accuracy_domain(accuracy_pct: float) -> tuple[str, str, int]:
    """Devuelve (nivel, descripción, rango interno para comparar peor dominio)."""
    if accuracy_pct >= ACC_NORMAL_MIN:
        return (
            "normal",
            f"Exactitud ≥ {ACC_NORMAL_MIN:g} % (rango esperado).",
            _RANK_ACC["normal"],
        )
    if accuracy_pct >= ACC_LIMITE_LOW:
        return (
            "límite",
            f"Exactitud entre {ACC_LIMITE_LOW:g} % y {ACC_NORMAL_MIN - 0.01:g} % (zona límite).",
            _RANK_ACC["límite"],
        )
    if accuracy_pct >= ACC_LEVE_LOW:
        return (
            "alteración leve",
            f"Exactitud entre {ACC_LEVE_LOW:g} % y {ACC_LIMITE_LOW - 0.01:g} %.",
            _RANK_ACC["alteración leve"],
        )
    if accuracy_pct >= ACC_MODERADA_LOW:
        return (
            "alteración moderada",
            f"Exactitud entre {ACC_MODERADA_LOW:g} % y {ACC_LEVE_LOW - 0.01:g} %.",
            _RANK_ACC["alteración moderada"],
        )
    return (
        "alteración severa",
        f"Exactitud < {ACC_MODERADA_LOW:g} %.",
        _RANK_ACC["alteración severa"],
    )


def _classify_rt_domain(rt_mean_ms: float, n_rt_valid: int) -> tuple[str, str, int]:
    # Futuro: ajustar umbrales según edad (p. ej. RT más altos aceptables en adultos mayores).
    if n_rt_valid <= 0:
        return "normal", "No hay tiempos de reacción válidos registrados.", _RANK_RT["normal"]
    if rt_mean_ms <= RT_NORMAL_MAX_MS:
        return "normal", f"RT medio ≤ {RT_NORMAL_MAX_MS:g} ms.", _RANK_RT["normal"]
    if rt_mean_ms <= RT_LEVE_MAX_MS:
        return "leve", f"RT medio entre {RT_NORMAL_MAX_MS:g} y {RT_LEVE_MAX_MS:g} ms.", _RANK_RT["leve"]
    if rt_mean_ms <= RT_MODERADO_MAX_MS:
        return (
            "moderado",
            f"RT medio entre {RT_LEVE_MAX_MS:g} y {RT_MODERADO_MAX_MS:g} ms.",
            _RANK_RT["moderado"],
        )
    return "severo", f"RT medio > {RT_MODERADO_MAX_MS:g} ms.", _RANK_RT["severo"]


def _classify_errors_domain(
    error_summary: dict[str, int],
    n_trials: int,
) -> tuple[dict[str, Any], int]:
    """Porcentajes de error sobre el total de ensayos; clasificación del dominio errores."""
    if n_trials <= 0:
        pct = {
            "fonologico_pct": 0.0,
            "no_relacionado_pct": 0.0,
            "omision_pct": 0.0,
            "total_errores_pct": 0.0,
        }
        return {
            "nivel": "normal",
            "descripcion": "Sin ensayos: no aplica cálculo de errores.",
            "porcentajes": pct,
        }, _RANK_ERR["normal"]

    f = error_summary.get("fonologico", 0)
    nr = error_summary.get("no_relacionado", 0)
    om = error_summary.get("omision", 0)
    fp = round(100.0 * f / n_trials, 2)
    nrp = round(100.0 * nr / n_trials, 2)
    op = round(100.0 * om / n_trials, 2)
    total = round(fp + nrp + op, 2)

    if total < ERR_NORMAL_MAX_PCT:
        nivel, desc = "normal", f"Proporción total de errores < {ERR_NORMAL_MAX_PCT:g} %."
    elif total <= ERR_LEVE_MAX_PCT:
        nivel, desc = "leve", (
            f"Proporción total de errores entre {ERR_NORMAL_MAX_PCT:g} % y {ERR_LEVE_MAX_PCT:g} %."
        )
    else:
        nivel, desc = "patológico", f"Proporción total de errores > {ERR_LEVE_MAX_PCT:g} %."

    block: dict[str, Any] = {
        "nivel": nivel,
        "descripcion": desc,
        "porcentajes": {
            "fonologico_pct": fp,
            "no_relacionado_pct": nrp,
            "omision_pct": op,
            "total_errores_pct": total,
        },
    }
    return block, _RANK_ERR[nivel]


def _classify_variability_domain(std_ms: float, n_rt_valid: int) -> tuple[str, str, int]:
    if n_rt_valid < 2:
        return (
            "normal",
            "Variabilidad no estimable (menos de dos RT válidos).",
            _RANK_VAR["normal"],
        )
    if std_ms <= VAR_NORMAL_MAX_MS:
        return "normal", f"Desvío estándar de RT ≤ {VAR_NORMAL_MAX_MS:g} ms.", _RANK_VAR["normal"]
    if std_ms <= VAR_LEVE_MAX_MS:
        return (
            "leve",
            f"Desvío estándar de RT entre {VAR_NORMAL_MAX_MS:g} y {VAR_LEVE_MAX_MS:g} ms.",
            _RANK_VAR["leve"],
        )
    return "alterado", f"Desvío estándar de RT > {VAR_LEVE_MAX_MS:g} ms.", _RANK_VAR["alterado"]


def build_clinical_breakdown(
    accuracy_pct: float,
    reaction_time_mean_ms: float,
    reaction_time_std_ms: float,
    error_summary: dict[str, int],
    n_trials: int,
    n_rt_valid: int,
) -> tuple[dict[str, Any], int]:
    """
    Interpretación multicomponente. Retorna (dict para JSON, peor_rango_interno).

    Criterio global: el nivel del dominio con peor desempeño (mayor rango interno);
    empate: orden en GLOBAL_TIEBREAK_KEYS.
    """
    an, ad, ar = _classify_accuracy_domain(accuracy_pct)
    tn, td, tr = _classify_rt_domain(reaction_time_mean_ms, n_rt_valid)
    err_block, er = _classify_errors_domain(error_summary, n_trials)
    vn, vd, vr = _classify_variability_domain(reaction_time_std_ms, n_rt_valid)

    ranks = {
        "accuracy": ar,
        "tiempo_reaccion": tr,
        "errores": er,
        "variabilidad": vr,
    }
    max_rank = max(ranks.values())
    candidates = [k for k, r in ranks.items() if r == max_rank]
    dom_peor = next(k for k in GLOBAL_TIEBREAK_KEYS if k in candidates)
    niveles_por_dominio = {
        "accuracy": an,
        "tiempo_reaccion": tn,
        "errores": err_block["nivel"],
        "variabilidad": vn,
    }
    global_nivel = niveles_por_dominio[dom_peor]

    out: dict[str, Any] = {
        "accuracy": {"nivel": an, "descripcion": ad},
        "tiempo_reaccion": {"nivel": tn, "descripcion": td},
        "errores": err_block,
        "variabilidad": {"nivel": vn, "descripcion": vd},
        "global": {"nivel": global_nivel, "criterio": "peor dominio"},
        "aviso_screening": SCREENING_DISCLAIMER,
    }
    return out, max_rank


def interpretacion_orientativa_from_worst_rank(worst_rank: int) -> dict[str, str]:
    """
    Compatibilidad con evaluaciones previas: categoria + mensaje corto.
    Mapeo del peor rango interno a tres categorías clásicas.
    """
    if worst_rank <= 1:
        cat = "dentro_rango_esperado"
        msg = "Desempeño global orientativamente dentro de rango esperado."
    elif worst_rank <= 2:
        cat = "intermedio_orientativo"
        msg = "Desempeño global orientativamente intermedio."
    else:
        cat = "alterado_orientativo"
        msg = "Desempeño global orientativamente alterado."
    msg = f"{msg} {SCREENING_DISCLAIMER}"
    return {"categoria": cat, "mensaje": msg}


def generate_brief_orientative_conclusion(bd: dict[str, Any]) -> str:
    """Una línea orientativa según el nivel global (peor dominio) del desglose clínico."""
    g = (bd or {}).get("global") or {}
    raw = str(g.get("nivel") or "").strip()
    if not raw:
        return "Sin datos suficientes para conclusión automática."
    nivel = raw.lower()
    severe = {
        "alteración severa",
        "severo",
        "patológico",
        "alterado",
    }
    moderate = {"alteración moderada", "moderado"}
    leve = {"alteración leve", "leve"}
    if nivel == "normal":
        return "Desempeño dentro de rango esperado."
    if nivel in ("límite", "limite"):
        return "Rendimiento limítrofe en denominación."
    if nivel in leve:
        return "Alteración leve del acceso léxico-fonológico."
    if nivel in moderate:
        return "Alteración moderada compatible con dificultades de denominación."
    if nivel in severe:
        return "Alteración severa compatible con compromiso significativo del acceso léxico."
    return "Resultado orientativo; revisar desglose por dominio."


def classify_clinical_performance(
    accuracy_pct: float,
    reaction_time_mean_ms: float,
    *,
    reaction_time_std_ms: float = 0.0,
    error_summary: Optional[dict[str, int]] = None,
    n_trials: int = 0,
    n_rt_valid: int = 0,
) -> dict[str, str]:
    """
    Resumen breve para JSON (interpretacion_orientativa).
    Con parámetros completos usa build_clinical_breakdown; sin ensayos, solo accuracy y RT.
    """
    es = error_summary if error_summary is not None else {"fonologico": 0, "no_relacionado": 0, "omision": 0}
    if n_trials <= 0:
        # Compatibilidad llamadas antiguas (p. ej. tests): solo exactitud y RT medio.
        nt = 1
        es = {"fonologico": 0, "no_relacionado": 0, "omision": 0}
        nrv = max(1, n_rt_valid) if n_rt_valid > 0 else 1
    else:
        nt = n_trials
        nrv = n_rt_valid

    _bd, worst = build_clinical_breakdown(
        accuracy_pct,
        reaction_time_mean_ms,
        reaction_time_std_ms,
        es,
        nt,
        nrv,
    )
    return interpretacion_orientativa_from_worst_rank(worst)


# ---------------------------------------------------------------------------
# Utilidades: logging, tiempo, rutas y persistencia JSON
# ---------------------------------------------------------------------------


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def resolve_image_path(relative: str) -> Path:
    # Rutas relativas al proyecto (TP: no usar rutas absolutas tipo C:/Users/...).
    p = Path(relative)
    if p.is_absolute():
        return Path(os.path.normpath(str(p)))
    parts = relative.replace("\\", "/").split("/")
    joined = os.path.normpath(os.path.join(str(BASE_DIR), *parts))
    return Path(joined)


def export_results_to_json(patient_id: str, payload: dict[str, Any], results_dir: Path) -> Path:
    """Un archivo JSON por paciente; cada bloque se agrega en la lista 'evaluaciones'."""
    ensure_directory(results_dir)
    safe_patient_id = patient_id.strip().replace(" ", "_")
    output_path = results_dir / f"{safe_patient_id}.json"

    stored_payload: dict[str, Any]
    if output_path.exists():
        with output_path.open("r", encoding="utf-8") as fp:
            existing = json.load(fp)
        if "evaluaciones" in existing and isinstance(existing["evaluaciones"], list):
            stored_payload = existing
        else:
            stored_payload = {
                "id_paciente": existing.get("id_paciente", patient_id),
                "paciente": existing.get("paciente", payload.get("paciente")),
                "evaluaciones": [existing],
            }
    else:
        stored_payload = {
            "id_paciente": patient_id,
            "paciente": payload.get("paciente"),
            "evaluaciones": [],
        }

    stored_payload["id_paciente"] = patient_id
    if payload.get("paciente"):
        stored_payload["paciente"] = payload["paciente"]
    stored_payload["evaluaciones"].append(payload)

    with output_path.open("w", encoding="utf-8") as fp:
        json.dump(stored_payload, fp, ensure_ascii=False, indent=2)

    return output_path


# ---------------------------------------------------------------------------
# Interfaz gráfica (Tkinter): pantallas y control del flujo
# ---------------------------------------------------------------------------


class NamingApp:
    """Orquesta las pantallas: bienvenida → explicación → ensayos → fin → opciones."""

    def __init__(self, root: tk.Tk, results_dir: Path) -> None:
        self.root = root
        self.results_dir = results_dir
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.configure(bg=FORM_BG)

        self.difficulty_var = tk.StringVar(value="facil")
        self.patient_data: dict[str, str] = {}

        self.current_trial_idx = 0
        self.trial_start_time: float | None = None
        self.trial_results: list[TrialResult] = []
        self.stimuli: list[NamingStimulus] = []
        self.current_image_ref: tk.PhotoImage | None = None
        self.current_options: list[str] = []
        self.response_locked = False

        # Última evaluación completada (para pantalla "resultados profesional")
        self._last_accuracy_pct: float = 0.0
        self._last_rt_mean_ms: float = 0.0
        self._last_rt_std_ms: float = 0.0
        self._last_error_summary: dict[str, int] = {}
        self._last_clinical: dict[str, str] = {}
        self._last_clinical_breakdown: dict[str, Any] = {}
        self._last_output_path: Optional[Path] = None
        self._last_report_meta: dict[str, Any] = {}

        # Fuentes (estilo Stroop)
        self.f_title = tkfont.Font(family=FONT_FAMILY, size=22, weight="bold")
        self.f_sub = tkfont.Font(family=FONT_FAMILY, size=15)
        self.f_label = tkfont.Font(family=FONT_FAMILY, size=14)
        self.f_entry = tkfont.Font(family=FONT_FAMILY, size=14)
        self.f_body = tkfont.Font(family=FONT_FAMILY, size=18)
        self.f_body_bold = tkfont.Font(family=FONT_FAMILY, size=18, weight="bold")
        self.f_btn = tkfont.Font(family=FONT_FAMILY, size=16, weight="bold")

        self._build_welcome_screen()

        # Contenedor de todo lo que no es la bienvenida (explicación, ensayos, fin).
        self.main_frame = tk.Frame(self.root, bg=FORM_BG)

    def _entry_opts(self) -> dict[str, Any]:
        return {
            "font": self.f_entry,
            "width": 36,
            "bg": "#FFFFFF",
            "fg": "#000000",
            "insertbackground": "#000000",
            "relief": tk.FLAT,
            "highlightthickness": 1,
            "highlightbackground": "#555555",
        }

    def _label_opts(self) -> dict[str, Any]:
        return {
            "bg": FORM_BG,
            "fg": FG_DEFAULT,
            "font": self.f_label,
            "anchor": "e",
        }

    def _build_welcome_screen(self) -> None:
        # Paso A: identificación del paciente, evaluador y nivel (15 ensayos por bloque).
        self.welcome_frame = tk.Frame(self.root, bg=FORM_BG)

        title = tk.Label(
            self.welcome_frame,
            text="Test — Denominación Fonológica",
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_title,
        )
        title.pack(pady=(40, 8))

        subtitle = tk.Label(
            self.welcome_frame,
            text="Complete los datos del paciente para comenzar.",
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_sub,
        )
        subtitle.pack(pady=(0, 36))

        form = tk.Frame(self.welcome_frame, bg=FORM_BG)
        form.pack()
        pad_y = 10
        eo = self._entry_opts()
        lo = self._label_opts()

        row0 = tk.Frame(form, bg=FORM_BG)
        row0.grid(row=0, column=0, columnspan=2, sticky="ew", pady=pad_y)
        tk.Label(row0, text="ID Paciente:", width=14, **lo).pack(side=tk.LEFT, padx=(0, 12))
        self._entry_patient_id = tk.Entry(row0, **eo)
        self._entry_patient_id.pack(side=tk.LEFT)

        row1 = tk.Frame(form, bg=FORM_BG)
        row1.grid(row=1, column=0, columnspan=2, sticky="ew", pady=pad_y)
        tk.Label(row1, text="Nombre:", width=14, **lo).pack(side=tk.LEFT, padx=(0, 12))
        self._entry_nombre = tk.Entry(row1, **eo)
        self._entry_nombre.pack(side=tk.LEFT)

        row2 = tk.Frame(form, bg=FORM_BG)
        row2.grid(row=2, column=0, columnspan=2, sticky="ew", pady=pad_y)
        tk.Label(row2, text="Edad:", width=14, **lo).pack(side=tk.LEFT, padx=(0, 12))
        self._entry_edad = tk.Entry(row2, **eo)
        self._entry_edad.pack(side=tk.LEFT)

        row3 = tk.Frame(form, bg=FORM_BG)
        row3.grid(row=3, column=0, columnspan=2, sticky="ew", pady=pad_y)
        tk.Label(row3, text="Evaluador/a:", width=14, **lo).pack(side=tk.LEFT, padx=(0, 12))
        self._entry_evaluador = tk.Entry(row3, **eo)
        self._entry_evaluador.pack(side=tk.LEFT)

        row4 = tk.Frame(form, bg=FORM_BG)
        row4.grid(row=4, column=0, columnspan=2, sticky="ew", pady=pad_y)
        tk.Label(row4, text="Dificultad:", width=14, **lo).pack(side=tk.LEFT, padx=(0, 12))
        diff_frame = tk.Frame(row4, bg=FORM_BG)
        diff_frame.pack(side=tk.LEFT)
        for level in DIFFICULTY_LEVELS:
            tk.Radiobutton(
                diff_frame,
                text=level.capitalize(),
                value=level,
                variable=self.difficulty_var,
                font=self.f_label,
                bg=FORM_BG,
                fg=FG_DEFAULT,
                selectcolor=FORM_BG,
                activebackground=FORM_BG,
                activeforeground=FG_DEFAULT,
            ).pack(side=tk.LEFT, padx=8)

        self._welcome_error = tk.Label(
            self.welcome_frame,
            text="",
            bg=FORM_BG,
            fg="#FF6B6B",
            font=tkfont.Font(family=FONT_FAMILY, size=12),
        )
        self._welcome_error.pack(pady=(16, 8))

        btn = tk.Button(
            self.welcome_frame,
            text="INICIAR EVALUACIÓN",
            font=tkfont.Font(family=FONT_FAMILY, size=14, weight="bold"),
            bg=ACCENT_BTN,
            fg=FG_DEFAULT,
            activebackground="#0090C8",
            activeforeground=FG_DEFAULT,
            relief=tk.FLAT,
            padx=32,
            pady=12,
            cursor="hand2",
            command=self._on_welcome_submit,
        )
        btn.pack(pady=12)

        self.welcome_frame.pack(fill=tk.BOTH, expand=True)
        self.root.after(150, lambda: self._entry_patient_id.focus_set())

    def _on_welcome_submit(self) -> None:
        # Validación mínima; luego se muestra la diapositiva de explicación (paso B).
        patient_id = self._entry_patient_id.get().strip()
        nombre = self._entry_nombre.get().strip()
        edad = self._entry_edad.get().strip()
        if not patient_id:
            self._welcome_error.config(text="Ingrese el ID del paciente.")
            return
        if not nombre:
            self._welcome_error.config(text="Ingrese el nombre del paciente.")
            return
        if edad and not edad.isdigit():
            self._welcome_error.config(text="La edad debe ser numérica.")
            return

        self._welcome_error.config(text="")
        self.patient_data = {
            "patient_id": patient_id,
            "nombre": nombre,
            "edad": edad,
            "evaluador": self._entry_evaluador.get().strip(),
        }

        self.welcome_frame.pack_forget()
        self.root.configure(bg=FORM_BG)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.root.after(100, self.root.focus_force)

        self._show_instruction_slide()

    def _show_instruction_slide(self) -> None:
        """Paso B: instrucciones breves (solo tras la bienvenida inicial, antes del primer bloque)."""
        self._clear_main_frame()

        tk.Label(
            self.main_frame,
            text="Antes de comenzar",
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_title,
        ).pack(pady=(32, 12))

        explanation = (
            "Este test mide cómo elige la palabra correcta para nombrar lo que ve.\n\n"
            "Verá una imagen y cuatro palabras. Solo una es la adecuada.\n"
            "Debe elegir con un solo clic (o con las teclas 1, 2, 3 o 4).\n\n"
            "No hay límite de tiempo. Tome el tiempo que necesite.\n"
            "Si no está seguro/a, puede elegir la opción que le parezca mejor."
        )
        tk.Label(
            self.main_frame,
            text=explanation,
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_body,
            justify="center",
            wraplength=920,
        ).pack(pady=24, padx=40)

        tk.Button(
            self.main_frame,
            text="CONTINUAR AL TEST",
            font=tkfont.Font(family=FONT_FAMILY, size=14, weight="bold"),
            bg=ACCENT_BTN,
            fg=FG_DEFAULT,
            activebackground="#0090C8",
            activeforeground=FG_DEFAULT,
            relief=tk.FLAT,
            padx=32,
            pady=12,
            cursor="hand2",
            command=self._on_instruction_continue,
        ).pack(pady=28)

    def _on_instruction_continue(self) -> None:
        self.start_evaluation()

    def start_evaluation(self) -> None:
        # Carga 15 estímulos del nivel, orden aleatorio, reinicia acumuladores del bloque.
        pid = self.patient_data.get("patient_id", "").strip()
        if not pid:
            messagebox.showwarning("Dato faltante", "Falta ID de paciente.")
            return

        try:
            self.stimuli = list(get_stimuli_by_difficulty(self.difficulty_var.get()))
        except ValueError as exc:
            messagebox.showwarning("Dato inválido", str(exc))
            return

        random.shuffle(self.stimuli)  # orden de presentación distinto en cada corrida
        self.current_trial_idx = 0
        self.trial_results = []
        self.response_locked = False
        LOGGER.info(
            "Inicio evaluación patient_id=%s dificultad=%s trials=%d",
            pid,
            self.difficulty_var.get(),
            len(self.stimuli),
        )
        self.show_trial()

    def _clear_main_frame(self) -> None:
        for w in self.main_frame.winfo_children():
            w.destroy()

    def show_trial(self) -> None:
        # Paso C: un ensayo = imagen + 4 palabras; t0 al terminar de dibujar (aprox. onset).
        if self.current_trial_idx >= len(self.stimuli):
            self.finish_evaluation()
            return

        stimulus = self.stimuli[self.current_trial_idx]
        self._clear_main_frame()
        self.root.update_idletasks()

        progress = tk.Label(
            self.main_frame,
            text=f"Ensayo {self.current_trial_idx + 1} / {len(self.stimuli)}",
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_body_bold,
        )
        progress.pack(pady=(12, 4))

        # Tamaño de imagen adaptable para que quepan las 4 opciones en pantalla.
        window_height = max(self.root.winfo_height(), 700)
        reserved_height = 360
        dynamic_image_size = max(240, min(IMAGE_FRAME_MAX, window_height - reserved_height))

        image_frame = tk.Frame(self.main_frame, bg=FORM_BG, width=dynamic_image_size, height=dynamic_image_size)
        image_frame.pack(pady=(0, 6))
        image_frame.pack_propagate(False)

        image_path = resolve_image_path(stimulus.image_path)
        if image_path.exists():
            try:
                self.current_image_ref = self._load_image_to_fit(
                    str(image_path), dynamic_image_size, dynamic_image_size
                )
                tk.Label(image_frame, image=self.current_image_ref, bg=FORM_BG).pack(expand=True)
            except tk.TclError:
                self._show_image_placeholder(image_frame, f"Imagen no compatible:\n{stimulus.image_path}")
        else:
            self._show_image_placeholder(image_frame, f"Imagen no disponible:\n{stimulus.image_path}")

        tk.Label(
            self.main_frame,
            text="Consigna: seleccione la palabra correcta (o teclas 1–4).",
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_body,
            justify="center",
        ).pack(pady=(0, 6))

        options_container = tk.Frame(self.main_frame, bg=FORM_BG)
        options_container.pack(pady=(0, 6))

        # Orden aleatorio de opciones para que la correcta no quede siempre en el mismo botón.
        self.current_options = stimulus.options.copy()
        random.shuffle(self.current_options)

        for index, option in enumerate(self.current_options, start=1):
            tk.Button(
                options_container,
                text=f"Opción {index}: {option}",
                font=self.f_btn,
                width=OPTION_BUTTON_WIDTH,
                height=OPTION_BUTTON_HEIGHT,
                bg=OPTION_BTN_BG,
                fg=OPTION_BTN_FG,
                activebackground=OPTION_BTN_BG,
                activeforeground=OPTION_BTN_FG,
                relief=tk.FLAT,
                cursor="hand2",
                command=lambda sel=option: self.on_response(sel),
            ).pack(pady=3)

        self._bind_response_keys()

        # Inicio del cronómetro de reacción (ms hasta el clic o tecla).
        self.trial_start_time = time.perf_counter()

    def _show_image_placeholder(self, parent: tk.Widget, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            font=self.f_body,
            bg=PLACEHOLDER_BG,
            fg=FG_DEFAULT,
            width=40,
            height=8,
            justify="center",
            relief=tk.SOLID,
            bd=2,
        ).pack(expand=True)

    def _load_image_to_fit(self, image_path: str, max_width: int, max_height: int) -> tk.PhotoImage:
        # PhotoImage solo reduce por subsample entero; la imagen completa debe caber en el marco.
        image = tk.PhotoImage(file=image_path)
        w, h = image.width(), image.height()
        scale = max(1, math.ceil(w / max_width), math.ceil(h / max_height))
        if scale > 1:
            image = image.subsample(scale, scale)
        return image

    def on_response(self, selected_option: str) -> None:
        # Evita doble registro si el usuario pulsa dos veces antes del siguiente ensayo.
        if self.response_locked:
            return
        self.response_locked = True

        if self.trial_start_time is None:
            reaction_time_ms: Optional[int] = None
        else:
            reaction_time_ms = int((time.perf_counter() - self.trial_start_time) * 1000)

        stimulus = self.stimuli[self.current_trial_idx]
        correct = is_correct(selected_option, stimulus)
        err = classify_error(selected_option, stimulus)

        self.trial_results.append(
            TrialResult(
                trial_index=self.current_trial_idx + 1,
                image_path=stimulus.image_path,
                target=stimulus.target,
                options=list(self.current_options),
                selected=selected_option,
                correct=correct,
                error_type=err,
                reaction_time_ms=reaction_time_ms,
            )
        )

        self.main_frame.update_idletasks()
        self.root.after(120, self._next_trial)

    def _next_trial(self) -> None:
        self.response_locked = False
        self.current_trial_idx += 1
        self.show_trial()

    def _bind_response_keys(self) -> None:
        # Teclas 1–4 y teclado numérico; deben coincidir con el orden actual de current_options.
        for idx in range(1, 5):
            self.root.unbind(str(idx))
            self.root.unbind(f"KP_{idx}")
        for index, option in enumerate(self.current_options, start=1):
            self.root.bind(str(index), lambda _e, sel=option: self.on_response(sel))
            self.root.bind(f"KP_{index}", lambda _e, sel=option: self.on_response(sel))

    def _unbind_response_keys(self) -> None:
        for idx in range(1, 5):
            self.root.unbind(str(idx))
            self.root.unbind(f"KP_{idx}")

    def finish_evaluation(self) -> None:
        # Paso D: agrega métricas al JSON, guarda en disco y muestra opciones (sin números al paciente).
        pid = self.patient_data.get("patient_id", "").strip()
        nombre = self.patient_data.get("nombre", "").strip()
        edad_s = self.patient_data.get("edad", "").strip()
        ev = self.patient_data.get("evaluador", "").strip()

        acc = calculate_accuracy_pct(self.trial_results)
        rt_mean = calculate_reaction_time_mean_ms(self.trial_results)
        rt_std = calculate_reaction_time_std_ms(self.trial_results)
        err_sum = summarize_errors(self.trial_results)
        n_trials = len(self.trial_results)
        n_rt_valid = count_valid_reaction_times(self.trial_results)

        clinical_breakdown, worst_rank = build_clinical_breakdown(
            acc,
            rt_mean,
            rt_std,
            err_sum,
            n_trials,
            n_rt_valid,
        )
        clin = interpretacion_orientativa_from_worst_rank(worst_rank)

        payload: dict[str, Any] = {
            "id_paciente": pid,
            "paciente": {
                "id": pid,
                "nombre": nombre,
                "edad": int(edad_s) if edad_s.isdigit() else None,
                "evaluador": ev or None,
            },
            "fecha": now_iso(),
            "test": DEFAULT_TEST_NAME,
            "dificultad": self.difficulty_var.get(),
            "metrica_principal": acc,
            "unidad": DEFAULT_METRIC_UNIT,
            "intentos": n_trials,
            "accuracy_pct": acc,
            "reaction_time_mean_ms": rt_mean,
            "reaction_time_std_ms": rt_std,
            "error_summary": err_sum,
            "clinical_breakdown": clinical_breakdown,
            "interpretacion_orientativa": clin,
            "trial_results": [t.to_dict() for t in self.trial_results],
        }

        try:
            out = export_results_to_json(pid, payload, self.results_dir)
            LOGGER.info("Resultados exportados: %s", out)
        except Exception as exc:
            LOGGER.exception("Error al exportar JSON")
            messagebox.showerror("Error", f"No se pudo exportar el JSON.\n{exc}")
            return

        self._last_accuracy_pct = acc
        self._last_rt_mean_ms = rt_mean
        self._last_rt_std_ms = rt_std
        self._last_error_summary = err_sum
        self._last_clinical = clin
        self._last_clinical_breakdown = clinical_breakdown
        self._last_output_path = out
        self._last_report_meta = {
            "nombre": nombre or "—",
            "id": pid or "—",
            "edad": edad_s or "—",
            "evaluador": ev or "—",
            "fecha": payload["fecha"],
            "dificultad": payload["dificultad"],
        }

        self._unbind_response_keys()  # evita respuestas fantasma al salir de los ensayos
        self._show_finish_choice_screen()

    def _show_finish_choice_screen(self) -> None:
        """Tras el bloque: sin mostrar diagnóstico al paciente; solo tres botones de navegación."""
        self._clear_main_frame()

        tk.Label(
            self.main_frame,
            text="Bloque completado",
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_title,
        ).pack(pady=(36, 16))

        tk.Label(
            self.main_frame,
            text=(
                "Gracias.\n\n"
                "Los datos de esta parte ya están guardados.\n"
                "Elija qué desea hacer a continuación."
            ),
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_body,
            justify="center",
            wraplength=900,
        ).pack(pady=20, padx=40)

        btn_opts = {
            "font": tkfont.Font(family=FONT_FAMILY, size=14, weight="bold"),
            "bg": ACCENT_BTN,
            "fg": FG_DEFAULT,
            "activebackground": "#0090C8",
            "activeforeground": FG_DEFAULT,
            "relief": tk.FLAT,
            "padx": 24,
            "pady": 10,
            "cursor": "hand2",
        }

        tk.Button(
            self.main_frame,
            text="Continuar con otro nivel",
            command=self._continue_same_patient,
            **btn_opts,
        ).pack(pady=10)

        tk.Button(
            self.main_frame,
            text="Finalizar y volver al inicio",
            command=self._back_to_welcome,
            **btn_opts,
        ).pack(pady=10)

        tk.Button(
            self.main_frame,
            text="Ver resultados (profesional)",
            command=self._show_doctor_results_screen,
            **btn_opts,
        ).pack(pady=(10, 28))

    def _show_doctor_results_screen(self) -> None:
        """Vista breve y clara; vuelve al menú del bloque con el botón superior o inferior."""
        self._clear_main_frame()

        acc = self._last_accuracy_pct
        rt_mean = self._last_rt_mean_ms
        rt_std = self._last_rt_std_ms
        bd = self._last_clinical_breakdown
        out = self._last_output_path
        meta = self._last_report_meta or {}

        def _meta(key: str, fallback_key: str) -> str:
            v = meta.get(key)
            if v is not None and str(v).strip():
                return str(v).strip()
            return str(self.patient_data.get(fallback_key, "") or "—").strip() or "—"

        nombre = _meta("nombre", "nombre")
        pid = _meta("id", "patient_id")
        edad = _meta("edad", "edad")
        ev = _meta("evaluador", "evaluador")
        fecha = meta.get("fecha") or "—"
        diff_raw = str(meta.get("dificultad") or self.difficulty_var.get() or "—").lower()
        diff_label = {"facil": "Fácil", "medio": "Medio", "dificil": "Difícil"}.get(diff_raw, diff_raw)

        pct = (bd.get("errores") or {}).get("porcentajes") or {}
        total_err_pct = pct.get("total_errores_pct", 0)
        brief = generate_brief_orientative_conclusion(bd)

        a_n = bd.get("accuracy", {}).get("nivel", "—")
        t_n = bd.get("tiempo_reaccion", {}).get("nivel", "—")
        e_n = bd.get("errores", {}).get("nivel", "—")
        v_n = bd.get("variabilidad", {}).get("nivel", "—")

        card_bg = "#5A5252"
        muted = "#C8C0C0"
        sep = "#7A7272"

        btn_back = {
            "font": tkfont.Font(family=FONT_FAMILY, size=13, weight="bold"),
            "bg": ACCENT_BTN,
            "fg": FG_DEFAULT,
            "activebackground": "#0090C8",
            "activeforeground": FG_DEFAULT,
            "relief": tk.FLAT,
            "padx": 20,
            "pady": 8,
            "cursor": "hand2",
        }

        top_bar = tk.Frame(self.main_frame, bg=FORM_BG)
        top_bar.pack(fill=tk.X, padx=20, pady=(16, 8))
        tk.Button(
            top_bar,
            text="← Volver al menú del bloque",
            command=self._show_finish_choice_screen,
            **btn_back,
        ).pack(side=tk.LEFT)

        tk.Label(
            self.main_frame,
            text="Resumen orientativo",
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_title,
        ).pack(pady=(4, 12))

        card = tk.Frame(self.main_frame, bg=card_bg, highlightbackground=sep, highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=40, pady=(0, 12))

        pad = tk.Frame(card, bg=card_bg)
        pad.pack(fill=tk.BOTH, expand=True, padx=28, pady=24)

        tk.Label(
            pad,
            text=f"{nombre}  ·  ID {pid}  ·  Edad {edad}  ·  {diff_label}",
            bg=card_bg,
            fg=FG_DEFAULT,
            font=self.f_sub,
            anchor="w",
            justify="left",
        ).pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            pad,
            text=f"Evaluador/a: {ev}  ·  {fecha}",
            bg=card_bg,
            fg=muted,
            font=self.f_label,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 16))

        tk.Label(
            pad,
            text=brief,
            bg=card_bg,
            fg=FG_DEFAULT,
            font=tkfont.Font(family=FONT_FAMILY, size=17),
            wraplength=820,
            justify="left",
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 20))

        tk.Frame(pad, height=1, bg=sep).pack(fill=tk.X, pady=(0, 16))

        tk.Label(
            pad,
            text=f"Exactitud {acc} %   ·   RT medio {rt_mean} ms   ·   Errores (total) {total_err_pct} %",
            bg=card_bg,
            fg=FG_DEFAULT,
            font=self.f_body,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 6))
        tk.Label(
            pad,
            text=f"Variabilidad (RT): {rt_std} ms",
            bg=card_bg,
            fg=muted,
            font=self.f_label,
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 14))

        tk.Label(
            pad,
            text=f"Clasificación por dominio:  exactitud «{a_n}»  ·  tiempo «{t_n}»  ·  errores «{e_n}»  ·  variabilidad «{v_n}»",
            bg=card_bg,
            fg=muted,
            font=self.f_label,
            wraplength=820,
            justify="left",
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 18))

        tk.Label(
            pad,
            text="Screening orientativo; no sustituye una evaluación clínica completa.",
            bg=card_bg,
            fg="#E8B86D",
            font=tkfont.Font(family=FONT_FAMILY, size=11),
            wraplength=820,
            justify="left",
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 8))

        if out is not None:
            tk.Label(
                pad,
                text=f"Datos completos en: {out.name}",
                bg=card_bg,
                fg=muted,
                font=tkfont.Font(family=FONT_FAMILY, size=11),
                anchor="w",
            ).pack(fill=tk.X)

        tk.Button(
            self.main_frame,
            text="Volver al menú del bloque",
            command=self._show_finish_choice_screen,
            font=tkfont.Font(family=FONT_FAMILY, size=14, weight="bold"),
            bg=ACCENT_BTN,
            fg=FG_DEFAULT,
            relief=tk.FLAT,
            padx=24,
            pady=10,
            cursor="hand2",
        ).pack(pady=(8, 24))

    def _back_to_welcome(self) -> None:
        self.main_frame.pack_forget()
        self.root.configure(bg=FORM_BG)
        # Destruir y volver a crear el formulario vacío para un nuevo paciente o sesión.
        self.welcome_frame.destroy()
        self._build_welcome_screen()

    def _continue_same_patient(self) -> None:
        # Mismo patient_data; solo se elige otra dificultad y se llama start_evaluation de nuevo.
        self._clear_main_frame()
        tk.Label(
            self.main_frame,
            text="Continuar evaluación",
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_title,
        ).pack(pady=20)
        tk.Label(
            self.main_frame,
            text="Mismo paciente. Elija el nuevo nivel.",
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_body,
        ).pack(pady=10)
        pid = self.patient_data.get("patient_id", "")
        nom = self.patient_data.get("nombre", "")
        tk.Label(
            self.main_frame,
            text=f"ID: {pid}    Nombre: {nom}",
            bg=FORM_BG,
            fg=FG_DEFAULT,
            font=self.f_body,
        ).pack(pady=(0, 16))

        diff_frame = tk.Frame(self.main_frame, bg=FORM_BG)
        diff_frame.pack(pady=8)
        for level in DIFFICULTY_LEVELS:
            tk.Radiobutton(
                diff_frame,
                text=level.capitalize(),
                value=level,
                variable=self.difficulty_var,
                font=self.f_body,
                bg=FORM_BG,
                fg=FG_DEFAULT,
                selectcolor=FORM_BG,
                activebackground=FORM_BG,
                activeforeground=FG_DEFAULT,
            ).pack(side=tk.LEFT, padx=10)

        tk.Button(
            self.main_frame,
            text="Iniciar siguiente nivel",
            font=tkfont.Font(family=FONT_FAMILY, size=14, weight="bold"),
            bg=ACCENT_BTN,
            fg=FG_DEFAULT,
            relief=tk.FLAT,
            padx=24,
            pady=10,
            cursor="hand2",
            command=self.start_evaluation,
        ).pack(pady=20)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    # Punto de entrada: crea ventana, carpeta de resultados y arranca el bucle de eventos.
    parser = argparse.ArgumentParser(description="Test Denominación Fonológica (post-ACV)")
    parser.add_argument(
        "--results-dir",
        type=str,
        default=None,
        help="Carpeta para JSON (por defecto: ./results junto a este archivo).",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir) if args.results_dir else RESULTS_DIR

    setup_logging()
    root = tk.Tk()
    app = NamingApp(root, results_dir)
    root.bind("<Escape>", lambda e: root.destroy())
    app.run()


if __name__ == "__main__":
    main()
