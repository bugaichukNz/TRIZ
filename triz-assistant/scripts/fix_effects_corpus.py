#!/usr/bin/env python3
"""Точечные исправления корпуса физэффектов data/triz_corpus/effects.json."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.llm.effects_corpus import EFFECT_FUNCTIONS, EFFECT_FUNCTIONS_SET  # noqa: E402
from backend.llm.models import EffectsCorpus, PhysicalEffect  # noqa: E402

DEFAULT_INPUT = PROJECT_ROOT / "data" / "triz_corpus" / "effects.json"
FIXED_VERSION = "1.0.1"

DELETE_IDS: frozenset[str] = frozenset(
    {
        "magnus_fluid_effect",
        "alexandrov_effect",
        "kelvin_effect",
        "casimir_effect",
    }
)

FUNCTIONS_REPLACEMENTS: dict[str, list[str]] = {
    "compton_effect": ["обнаружение дефектов"],
    "mossbauer_effect": ["обнаружение дефектов"],
    "neutron_activation": ["обнаружение дефектов"],
    "ph_effect": ["изменение вязкости"],
    "mott_effect": ["изменение проводимости"],
    "tyndall_effect": ["изменение прозрачности"],
}

NAME_RENAMES: dict[str, str] = {
    "disjoining_pressure": "Расклинивающее давление (Дерягина)",
    "stern_layer": "Слой Штерна",
}

REWRITES: dict[str, dict[str, Any]] = {
    "egd_effect": {
        "description": (
            "Электрогидродинамика (ЭГД) — движение жидкости или газа под действием "
            "электрического поля за счёт сил, действующих на заряженные или поляризованные "
            "частицы среды. Позволяет управлять потоками и перемещать вещество без "
            "механических движущих частей."
        ),
        "input_action": "электрическое поле в жидкости или газе",
        "output_action": "движение жидкости/газа, перенос вещества",
        "functions": ["управление потоком жидкости/газа", "перемещение объекта"],
    },
    "maggi_righi_effect": {
        "name": "Магнитоупругий эффект (Виллари)",
        "description": (
            "Магнитоупругий эффект (эффект Виллари) — изменение намагниченности "
            "ферромагнитного материала при механическом напряжении или деформации. "
            "Изменение намагниченности при растяжении или сжатии — обратное изменению размеров "
            "в магнитном поле. Применяется в датчиках силы и неразрушающем контроле."
        ),
        "input_action": "механическое напряжение или деформация ферромагнитного материала",
        "output_action": "изменение намагниченности",
        "functions": ["измерение силы", "обнаружение дефектов"],
    },
}


def _apply_fixes(effects: list[PhysicalEffect]) -> tuple[list[PhysicalEffect], list[str]]:
    """Применяет исправления; возвращает новый список и журнал действий."""
    log: list[str] = []
    by_id = {e.id: e for e in effects}

    for eid in sorted(DELETE_IDS):
        if eid in by_id:
            del by_id[eid]
            log.append(f"удалён: {eid}")
        # идемпотентно: отсутствующий id — пропуск без сообщения

    for eid, fns in FUNCTIONS_REPLACEMENTS.items():
        if eid not in by_id:
            continue
        effect = by_id[eid]
        if effect.functions != fns:
            by_id[eid] = effect.model_copy(update={"functions": list(fns)})
            log.append(f"functions[{eid}]: {fns}")

    for eid, new_name in NAME_RENAMES.items():
        if eid not in by_id:
            continue
        effect = by_id[eid]
        if effect.name != new_name:
            by_id[eid] = effect.model_copy(update={"name": new_name})
            log.append(f"name[{eid}]: «{new_name}»")

    for eid, fields in REWRITES.items():
        if eid not in by_id:
            continue
        effect = by_id[eid]
        updates = {k: v for k, v in fields.items() if getattr(effect, k) != v}
        if updates:
            by_id[eid] = effect.model_copy(update=updates)
            log.append(f"переписан: {eid} ({', '.join(sorted(updates))})")

    return sorted(by_id.values(), key=lambda e: e.id), log


def _report_extra_provenance(effects: list[PhysicalEffect]) -> None:
    extras = [e for e in effects if e.provenance == "extra"]
    print(f"\n=== Записи provenance=extra ({len(extras)}) — для ручной проверки ===")
    if not extras:
        print("  (нет)")
        return
    for effect in sorted(extras, key=lambda e: e.id):
        print(f"  • {effect.id}: {effect.name}")


def _report_function_dictionary(effects: list[PhysicalEffect]) -> None:
    used: set[str] = set()
    for effect in effects:
        used.update(effect.functions)

    unknown = sorted(used - EFFECT_FUNCTIONS_SET)
    uncovered = sorted(EFFECT_FUNCTIONS_SET - used)

    print("\n=== Валидация словаря функций (EFFECT_FUNCTIONS) ===")
    print(f"Уникальных functions в корпусе: {len(used)}")
    print(f"Размер словаря EFFECT_FUNCTIONS: {len(EFFECT_FUNCTIONS)}")

    print(f"\n(a) В корпусе, но отсутствуют в словаре ({len(unknown)}):")
    if unknown:
        for fn in unknown:
            print(f"  ! {fn}")
    else:
        print("  (нет расхождений)")

    print(f"\n(b) В словаре, но не покрыты ни одним эффектом ({len(uncovered)}):")
    if uncovered:
        for fn in uncovered:
            print(f"  ○ {fn}")
    else:
        print("  (полное покрытие)")


def fix_corpus(path: Path, *, dry_run: bool = False) -> int:
    if not path.is_file():
        print(f"ОШИБКА: файл не найден: {path}")
        return 1

    raw = json.loads(path.read_text(encoding="utf-8"))
    try:
        corpus = EffectsCorpus.model_validate(raw)
    except Exception as exc:
        print(f"ОШИБКА схемы EffectsCorpus: {exc}")
        return 1

    before_count = len(corpus.effects)
    fixed_effects, change_log = _apply_fixes(corpus.effects)
    after_count = len(fixed_effects)

    print(f"Файл: {path}")
    print(f"Версия до: {corpus.version}")
    print(f"Записей до/после: {before_count} -> {after_count} (удалено {before_count - after_count})")

    if change_log:
        print(f"\nПрименённые изменения ({len(change_log)}):")
        for line in change_log:
            print(f"  • {line}")
    else:
        print("\nИзменений не требуется (корпус уже исправлен).")

    _report_extra_provenance(fixed_effects)
    _report_function_dictionary(fixed_effects)

    new_corpus = EffectsCorpus(effects=fixed_effects, version=FIXED_VERSION)
    new_payload = new_corpus.model_dump()
    old_payload = corpus.model_dump()

    if new_payload == old_payload and corpus.version == FIXED_VERSION:
        print(f"\nOK Корпус актуален (version={FIXED_VERSION}), запись не требуется.")
        return 0

    if dry_run:
        print("\n[dry-run] Файл не записан.")
        return 0

    backup_path = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup_path)
    print(f"\nБэкап: {backup_path}")

    path.write_text(
        json.dumps(new_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Записано: {path} (version={FIXED_VERSION})")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Точечные исправления корпуса физэффектов TRIZ",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Путь к effects.json (по умолчанию {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать отчёт без записи файла",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sys.exit(fix_corpus(args.input, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
