"""Контролируемый словарь функций и метаданные батчей для корпуса физэффектов."""

from __future__ import annotations

import logging
import re
from typing import TypedDict

from backend.llm.models import PhysicalEffect

logger = logging.getLogger(__name__)

EFFECT_FUNCTIONS: tuple[str, ...] = (
    "нагрев",
    "охлаждение",
    "перемещение объекта",
    "дозирование",
    "измерение температуры",
    "измерение перемещения",
    "измерение давления",
    "измерение силы",
    "создание усилия",
    "разделение смесей",
    "смешивание",
    "изменение трения",
    "изменение прозрачности",
    "фиксация/освобождение",
    "генерация колебаний",
    "стабилизация положения",
    "накопление энергии",
    "управление потоком жидкости/газа",
    "изменение формы",
    "обнаружение дефектов",
    "изменение адгезии",
    "электризация/нейтрализация заряда",
    "изменение вязкости",
    "фильтрация",
    "герметизация",
    "преобразование энергии",
    "усиление сигнала",
    "создание вакуума/давления",
    "изменение проводимости",
    "локальный нагрев",
)

EFFECT_FUNCTIONS_SET: frozenset[str] = frozenset(EFFECT_FUNCTIONS)

CORPUS_VERSION = "1.1.0"


class GenerationBatch(TypedDict):
    key: str
    title: str
    category_hint: str
    topics: str
    suggested_ids: dict[str, str]
    target_count: int


BATCH_COVERAGE_THRESHOLD = 0.8
MAX_BATCH_GENERATION_ATTEMPTS = 2


_RAW_GENERATION_BATCHES: list[dict] = [
    {
        "key": "thermal_basic",
        "title": "Термические эффекты (расширение, фазы, теплоперенос)",
        "category_hint": "физический",
        "topics": (
            "тепловое расширение, фазовые переходы, эффект Пельтье, эффект Томсона, "
            "эффект Ранка, тепловые трубы, термодиффузия, сверхтекучесть гелия, "
            "эффект Лedenfrost, термоэлектрический эффект, тепловое излучение, "
            "конvection, теплопроводность анизотропная, термохромизм, "
            "эффект Джоуля–Томсона, криогенное сжатие, испарительное охлаждение"
        ),
        "suggested_ids": [
            "thermal_expansion",
            "phase_transition",
            "peltier_effect",
            "thomson_effect",
            "rank_effect",
            "heat_pipe",
            "thermodiffusion",
            "superfluidity",
            "leidenfrost_effect",
            "thermoelectric_effect",
            "thermal_radiation",
            "natural_convection",
            "anisotropic_thermal_conductivity",
            "thermochromism",
            "joule_thomson_effect",
            "cryogenic_shrink_fit",
            "evaporative_cooling",
        ],
        "target_count": 17,
    },
    {
        "key": "electrical_magnetic",
        "title": "Электрические и магнитные эффекты",
        "category_hint": "физический",
        "topics": (
            "пьезоэффект, обратный пьезоэффект, магнитострикция, электрострикция, "
            "эффект Холла, электростатическое притяжение, электрофорез, "
            "электромагнитная индукция, эффект Магgi-Righi, ЭГД-эффект, МГД-эффект, "
            "эффект Баркhausen, сверхпроводимость, эффект Мейсснера, "
            "электролюминесценция, туннельный эффект, эффект Зеебека, "
            "электромагнитное удержание, вихревые токи"
        ),
        "suggested_ids": [
            "piezoelectric_effect",
            "inverse_piezoelectric_effect",
            "magnetostriction",
            "electrostriction",
            "hall_effect",
            "electrostatic_attraction",
            "electrophoresis",
            "electromagnetic_induction",
            "maggi_righi_effect",
            "egd_effect",
            "mhd_effect",
            "barkhausen_effect",
            "superconductivity",
            "meissner_effect",
            "electroluminescence",
            "quantum_tunneling",
            "seebeck_effect",
            "electromagnetic_levitation",
            "eddy_currents",
        ],
        "target_count": 18,
    },
    {
        "key": "optical",
        "title": "Оптические эффекты",
        "category_hint": "физический",
        "topics": (
            "люминесценция, флуоресценция, поляризация света, полное внутреннее отражение, "
            "фотохромизм, интерференция, дифракция, эффект Доплера для света, "
            "оптическое волокно, фотоэлектрический эффект, эффект Керра, "
            "голография, рассеяние Рэлея, эффект Фарадея (оптический), "
            "световоды на основе TIR, люминофорная индикация, фототропизм материалов"
        ),
        "suggested_ids": [
            "luminescence",
            "fluorescence",
            "light_polarization",
            "total_internal_reflection",
            "photochromism",
            "optical_interference",
            "diffraction",
            "optical_doppler",
            "optical_fiber_guiding",
            "photoelectric_effect",
            "kerr_effect",
            "holography",
            "rayleigh_scattering",
            "faraday_optical_rotation",
            "tir_light_guide",
            "phosphor_indication",
            "phototropic_materials",
        ],
        "target_count": 17,
    },
    {
        "key": "mechanical",
        "title": "Механические эффекты",
        "category_hint": "физический",
        "topics": (
            "резонанс, кавитация, эффект Александрова, гироскопический эффект, "
            "эластичность, пластическая деформация, эффект Бauschinger, "
            "сверхэластичность, эффект памяти формы (механическая часть), "
            "виброуплотнение, акустическая эмиссия, эффект Мagnus, "
            "гидродинамическая смазка, эффект Кельвина, ударная волна, "
            "эффект Пуассона, предварительное напряжение"
        ),
        "suggested_ids": [
            "mechanical_resonance",
            "cavitation",
            "alexandrov_effect",
            "gyroscopic_effect",
            "elasticity",
            "plastic_deformation",
            "bauschinger_effect",
            "superelasticity",
            "shape_memory_mechanical",
            "vibrocompaction",
            "acoustic_emission",
            "magnus_effect",
            "hydrodynamic_lubrication",
            "kelvin_effect",
            "shock_wave",
            "poisson_effect",
            "prestressing",
        ],
        "target_count": 17,
    },
    {
        "key": "chemical",
        "title": "Химические эффекты",
        "category_hint": "химический",
        "topics": (
            "гидриды, гели, экзотермические реакции, эндотермические реакции, "
            "катализ, автокatalysis, корrosion, пассивация, окисление, "
            "полимеризация, гидролиз, хемisorption, эффект pH, "
            "электрохимическая корrosion, топochemical reaction, "
            "гидrogel swelling, цемent hydration"
        ),
        "suggested_ids": [
            "metal_hydrides",
            "chemical_gels",
            "exothermic_reaction",
            "endothermic_reaction",
            "catalysis",
            "autocatalysis",
            "corrosion",
            "passivation",
            "oxidation",
            "polymerization",
            "hydrolysis",
            "chemisorption",
            "ph_effect",
            "electrochemical_corrosion",
            "topochemical_reaction",
            "hydrogel_swelling",
            "cement_hydration",
        ],
        "target_count": 17,
    },
    {
        "key": "surface",
        "title": "Поверхностные эффекты",
        "category_hint": "физический",
        "topics": (
            "капиллярность, электроосмос, эффект Ребиндера, поверхностное натяжение, "
            "адhesion, дисjoining pressure, эффект Marangoni, "
            "смачиваемость, лотос-эффект, эффект Cassie-Baxter, "
            "электрокапиллярность, поверхностная диффузия, "
            "эффект Stern, самосборка монослоёв, плазменная обработка поверхности"
        ),
        "suggested_ids": [
            "capillarity",
            "electroosmosis",
            "rehbinder_effect",
            "surface_tension",
            "adhesion",
            "disjoining_pressure",
            "marangoni_effect",
            "wettability",
            "lotus_effect",
            "cassie_baxter_effect",
            "electrocapillarity",
            "surface_diffusion",
            "stern_layer",
            "self_assembled_monolayer",
            "plasma_surface_treatment",
        ],
        "target_count": 15,
    },
    {
        "key": "acoustic_ultrasound",
        "title": "Акустические и ультразвуковые эффекты",
        "category_hint": "физический",
        "topics": (
            "ультразвук, акустическая кavitация, акустическое levitation, "
            "эффект SAW (поверхностные акустические волны), акустическая эмиссия, "
            "sonochemistry, акустическая streaming, эффект Doppler (звук), "
            "резонанс Helmholtz, акустическая фильтрация, "
            "piezoacoustic transduction, акустическая tomography"
        ),
        "suggested_ids": [
            "ultrasound",
            "acoustic_cavitation",
            "acoustic_levitation",
            "surface_acoustic_waves",
            "acoustic_emission_detection",
            "sonochemistry",
            "acoustic_streaming",
            "acoustic_doppler",
            "helmholtz_resonance",
            "acoustic_filtration",
            "piezoacoustic_transduction",
            "acoustic_tomography",
        ],
        "target_count": 12,
    },
    {
        "key": "fluid_gas",
        "title": "Гидро- и газодинамические эффекты",
        "category_hint": "физический",
        "topics": (
            "эффект Bernoulli, эффект Coanda, эффект Venturi, турbulent mixing, "
            "laminar flow, эффект Magnus (жидкость), гидrostatic pressure, "
            "эффект Pitot, эжекция, vortex shedding, "
            "эффект Knudsen, газовые diffusion, пневматический transport, "
            "эффект Taylor bubble, капельная dispersion"
        ),
        "suggested_ids": [
            "bernoulli_effect",
            "coanda_effect",
            "venturi_effect",
            "turbulent_mixing",
            "laminar_flow",
            "magnus_fluid_effect",
            "hydrostatic_pressure",
            "pitot_effect",
            "fluid_ejector",
            "vortex_shedding",
            "knudsen_effect",
            "gas_diffusion",
            "pneumatic_transport",
            "taylor_bubble",
            "droplet_dispersion",
        ],
        "target_count": 15,
    },
    {
        "key": "material_phase",
        "title": "Материаловедческие и фазовые эффекты",
        "category_hint": "физический",
        "topics": (
            "мемори-сплавы, амorphization, recrystallization, "
            "эффект Hall-Petch, grain boundary sliding, "
            "эффект Zener pinning, martensitic transformation, "
            "эффект Guinier-Preston zones, spinodal decomposition, "
            "эффект Kirkendall, diffusion bonding, sintering, "
            "эффект Mott, work hardening"
        ),
        "suggested_ids": [
            "shape_memory_alloy",
            "amorphization",
            "recrystallization",
            "hall_petch_effect",
            "grain_boundary_sliding",
            "zener_pinning",
            "martensitic_transformation",
            "guinier_preston_zones",
            "spinodal_decomposition",
            "kirkendall_effect",
            "diffusion_bonding",
            "sintering",
            "mott_effect",
            "work_hardening",
        ],
        "target_count": 14,
    },
    {
        "key": "radiation_nuclear",
        "title": "Радиационные и ядерные эффекты",
        "category_hint": "физический",
        "topics": (
            "радиolysis, радиation grafting, эффект Mössbauer, "
            "радиoluminescence, neutron activation, "
            "эффект Compton, photo-stimulated desorption, "
            "радиation crosslinking, радиation sterilization, "
            "эффект Cherenkov, радиation induced conductivity"
        ),
        "suggested_ids": [
            "radiolysis",
            "radiation_grafting",
            "mossbauer_effect",
            "radioluminescence",
            "neutron_activation",
            "compton_effect",
            "photo_stimulated_desorption",
            "radiation_crosslinking",
            "radiation_sterilization",
            "cherenkov_radiation",
            "radiation_induced_conductivity",
        ],
        "target_count": 11,
    },
    {
        "key": "geometric",
        "title": "Геометрические эффекты и преобразования",
        "category_hint": "геометрический",
        "topics": (
            "рычag, блок, клин, винт, зубчатая передача, "
            "дифференциальный механизм, параллелogram linkage, "
            "four-bar linkage, cam mechanism, ratchet, "
            "expansion joint, bellows geometry, "
            "фокусирующая геометрия, траектория cycloid, "
            "эффект Archimedes screw, compliant mechanism"
        ),
        "suggested_ids": [
            "lever",
            "pulley_block",
            "wedge",
            "screw_mechanism",
            "gear_transmission",
            "differential_mechanism",
            "parallelogram_linkage",
            "four_bar_linkage",
            "cam_mechanism",
            "ratchet_mechanism",
            "expansion_joint",
            "bellows_geometry",
            "focusing_geometry",
            "cycloid_trajectory",
            "archimedes_screw",
            "compliant_mechanism",
        ],
        "target_count": 16,
    },
    {
        "key": "biological_medical",
        "title": "Биофизические и медицинские эффекты",
        "category_hint": "физический",
        "topics": (
            "эффект osmosis, dialysis, hemolysis, "
            "эффект Tyndall (кolloid), bioadhesion, "
            "электroporation, electrophoresis gel, "
            "эффект piezo in bone, photodynamic therapy, "
            "magnetic hyperthermia, osmotic pump, "
            "эффект Fick diffusion in tissue"
        ),
        "suggested_ids": [
            "osmosis",
            "dialysis",
            "hemolysis",
            "tyndall_effect",
            "bioadhesion",
            "electroporation",
            "gel_electrophoresis",
            "piezoelectric_bone_healing",
            "photodynamic_therapy",
            "magnetic_hyperthermia",
            "osmotic_pump",
            "fick_diffusion_tissue",
        ],
        "target_count": 12,
    },
    {
        "key": "misc_advanced",
        "title": "Дополнительные эффекты (квантовые, нелинейные, специальные)",
        "category_hint": "физический",
        "topics": (
            "эффект Josephson, SQUID, эффект Meissner-Ochsenfeld, "
            "эффект Casimir, non-Newtonian fluid shear thinning, "
            "эффект Weissenberg, electro-rheological fluid, "
            "magnetorheological fluid, photo-induced conductivity, "
            "эффект Mpemba, triboelectric effect, "
            "эффект Leidenfrost (доп.), thermoacoustic engine, "
            "эффект Ranque-Hilsch vortex tube, shape morphing"
        ),
        "suggested_ids": [
            "josephson_effect",
            "squid_sensor",
            "casimir_effect",
            "shear_thinning",
            "weissenberg_effect",
            "electrorheological_fluid",
            "magnetorheological_fluid",
            "photo_induced_conductivity",
            "mpemba_effect",
            "triboelectric_effect",
            "thermoacoustic_engine",
            "vortex_tube",
            "shape_morphing",
            "nonlinear_optics",
            "plasma_formation",
        ],
        "target_count": 15,
    },
    {
        "key": "gap_fill",
        "title": "Дополнение корпуса до целевого объёма",
        "category_hint": "физический",
        "topics": (
            "любые классические эффекты из указателя физических эффектов ТРИЗ, "
            "которые ещё не представлены в корпусе: термомагнитные, "
            "электрохимические, фотоelastic, magneto-optical, "
            "эффекты тонких плёнок, MEMS-эффекты, "
            "эффект electro-wetting, thermophoresis, "
            "эффект Soret, barocaloric effect"
        ),
        "suggested_ids": [],
        "target_count": 20,
    },
]


def build_suggested_map(ids: list[str], topics: str) -> dict[str, str]:
    """Строит словарь id → ожидаемое русское название из списка id и строки topics."""
    if not ids:
        return {}
    parts = [p.strip() for p in re.split(r",\s*", topics.strip()) if p.strip()]
    if len(parts) != len(ids):
        logger.warning(
            "topics/id mismatch: %d ids, %d topic parts — fallback к slug",
            len(ids),
            len(parts),
        )
        return {sid: sid.replace("_", " ") for sid in ids}
    return dict(zip(ids, parts))


def finalize_generation_batch(raw: dict) -> GenerationBatch:
    """Приводит suggested_ids к dict[str, str] (id → ожидаемое название)."""
    batch = dict(raw)
    sids = batch.get("suggested_ids") or []
    if isinstance(sids, list):
        batch["suggested_ids"] = build_suggested_map(sids, batch["topics"])
    elif isinstance(sids, dict):
        batch["suggested_ids"] = dict(sids)
    else:
        batch["suggested_ids"] = {}
    return batch  # type: ignore[return-value]


GENERATION_BATCHES = [finalize_generation_batch(b) for b in _RAW_GENERATION_BATCHES]


def normalize_effect_name(name: str) -> str:
    """Нормализация названия для сопоставления: lower, ё→е, только буквы/цифры."""
    normalized = name.strip().lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]", "", normalized)


def normalize_effect_id(raw_id: str) -> str:
    """Приводит id к slug: латиница, цифры, подчёркивания."""
    slug = raw_id.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug


def sanitize_effect_functions(effect: PhysicalEffect) -> PhysicalEffect:
    """Оставляет только функции из EFFECT_FUNCTIONS; невалидные — в лог."""
    valid: list[str] = []
    seen: set[str] = set()
    for fn in effect.functions:
        fn_stripped = fn.strip()
        if fn_stripped in EFFECT_FUNCTIONS_SET:
            if fn_stripped not in seen:
                valid.append(fn_stripped)
                seen.add(fn_stripped)
        else:
            logger.warning(
                "Эффект %s: функция %r не входит в EFFECT_FUNCTIONS — отброшена",
                effect.id,
                fn_stripped,
            )
    return effect.model_copy(update={"functions": valid, "id": normalize_effect_id(effect.id)})


def merge_effects(
    existing: list[PhysicalEffect],
    new_batch: list[PhysicalEffect],
) -> list[PhysicalEffect]:
    """Объединяет списки с дедупликацией по id и нормализованному name."""
    by_id: dict[str, PhysicalEffect] = {e.id: e for e in existing}
    names: dict[str, str] = {
        normalize_effect_name(e.name): e.id for e in existing if normalize_effect_name(e.name)
    }
    for effect in new_batch:
        normalized = sanitize_effect_functions(effect)
        if normalized.id in by_id:
            logger.info("Пропуск дубликата id=%s", normalized.id)
            continue
        norm_name = normalize_effect_name(normalized.name)
        if norm_name and norm_name in names:
            logger.info(
                "Пропуск дубликата name=%r (id=%s, existing id=%s)",
                normalized.name,
                normalized.id,
                names[norm_name],
            )
            continue
        by_id[normalized.id] = normalized
        if norm_name:
            names[norm_name] = normalized.id
    return sorted(by_id.values(), key=lambda e: e.id)


def canonicalize_batch_effects(
    batch: GenerationBatch,
    effects: list[PhysicalEffect],
    *,
    missing_ids: list[str],
) -> list[PhysicalEffect]:
    """Канонизирует id по name для missing suggested_ids; прочие — provenance extra."""
    suggested_map = batch["suggested_ids"]
    missing_set = set(missing_ids)

    name_to_id: dict[str, str] = {}
    ambiguous_names: set[str] = set()
    for sid in missing_ids:
        expected = suggested_map.get(sid, "")
        norm = normalize_effect_name(expected)
        if not norm:
            continue
        if norm in name_to_id:
            ambiguous_names.add(norm)
        else:
            name_to_id[norm] = sid
    for norm in ambiguous_names:
        name_to_id.pop(norm, None)

    result: list[PhysicalEffect] = []
    for effect in effects:
        sanitized = sanitize_effect_functions(effect)
        if sanitized.id in suggested_map:
            result.append(sanitized.model_copy(update={"provenance": "planned"}))
            continue

        norm_name = normalize_effect_name(sanitized.name)
        matched_id = name_to_id.get(norm_name)
        if matched_id and matched_id in missing_set:
            logger.info(
                "Канонизация id: %s → %s (name=%r)",
                sanitized.id,
                matched_id,
                sanitized.name,
            )
            result.append(
                sanitized.model_copy(update={"id": matched_id, "provenance": "planned"})
            )
            continue

        result.append(sanitized.model_copy(update={"provenance": "extra"}))
    return result


def batch_missing_ids(batch: GenerationBatch, existing_ids: set[str]) -> list[str]:
    """Возвращает suggested_ids батча, которых ещё нет в корпусе."""
    return [sid for sid in batch["suggested_ids"] if sid not in existing_ids]


def batch_coverage(batch: GenerationBatch, existing_ids: set[str]) -> float:
    """Доля покрытых suggested_ids батча (0.0–1.0)."""
    suggested = batch["suggested_ids"]
    if not suggested:
        return 1.0
    covered = sum(1 for sid in suggested if sid in existing_ids)
    return covered / len(suggested)


def batch_is_complete(
    batch: GenerationBatch,
    existing_ids: set[str],
    batch_count: int,
    *,
    attempt_count: int = 0,
    total_count: int = 0,
    min_total: int = 200,
    coverage_threshold: float = BATCH_COVERAGE_THRESHOLD,
    max_attempts: int = MAX_BATCH_GENERATION_ATTEMPTS,
) -> bool:
    """True, если батч закрыт: ≥coverage_threshold suggested_ids или ≥max_attempts попыток."""
    if batch["key"] == "gap_fill":
        return total_count >= min_total
    if batch["suggested_ids"]:
        if batch_coverage(batch, existing_ids) >= coverage_threshold:
            return True
        if attempt_count >= max_attempts:
            return True
        return False
    return batch_count >= batch["target_count"]


def build_batch_prompt(
    batch: GenerationBatch,
    *,
    missing_ids: list[str],
    existing_ids: set[str],
    count: int,
) -> str:
    """Формирует промпт для генерации одного батча эффектов."""
    functions_list = "\n".join(f"- {fn}" for fn in EFFECT_FUNCTIONS)
    avoid = ", ".join(sorted(existing_ids)[:80])
    if len(existing_ids) > 80:
        avoid += f", … (всего {len(existing_ids)} id)"

    id_instruction = ""
    if missing_ids:
        id_instruction = (
            f"\nОбязательно включи эффекты со следующими id (slug): {', '.join(missing_ids)}.\n"
        )
    elif batch["suggested_ids"]:
        id_instruction = (
            f"\nИспользуй id из списка: {', '.join(batch['suggested_ids'].keys())}.\n"
        )

    return f"""Ты — эксперт по указателю физических эффектов ТРИЗ (А.В. Быстрик и др.).

Сгенерируй ровно {count} записей физических/химических/геометрических эффектов для категории:
«{batch["title"]}».

Тематика: {batch["topics"]}

Основная категория записей: «{batch["category_hint"]}» (допускаются смежные, если уместно).

{id_instruction}
Требования к каждой записи:
- id: slug латиницей (snake_case), уникальный, без пробелов
- name: русское название в кавычках не нужно — просто «Магнитострикция»
- category: одно из «физический», «химический», «геометрический»
- description: 2–4 содержательных предложения о сути эффекта
- input_action: что подаём на вход (конкретно)
- output_action: что получаем на выходе (конкретно)
- functions: 1–4 значения СТРОГО из списка ниже (точное совпадение строк)
- limitations: границы применимости, типичные диапазоны величин, ограничения материалов
- examples: 1–3 реалистичных примера применения в технике/промышленности

Контролируемый словарь functions (использовать ТОЛЬКО эти строки):
{functions_list}

Не дублируй id из уже существующего корпуса: {avoid or "—"}.

Ответ — JSON по схеме EffectsBatch (поле effects)."""


def total_target_count() -> int:
    """Суммарный целевой объём по всем батчам."""
    return sum(b["target_count"] for b in GENERATION_BATCHES)
