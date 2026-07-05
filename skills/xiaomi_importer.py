"""
xiaomi_importer.py — Import body composition data from a Xiaomi account ZIP export.

How to get the ZIP:
  1. Open Mi Fitness app → Me (bottom-right) → Settings → Privacy → Export data
     OR open health.mi.com in a browser → Account → Data export
  2. Download the ZIP file (e.g. mifitness_export_*.zip)
  3. Run: python main.py importar-xiaomi-zip --archivo mifitness_export.zip --persona ATM

Supported formats inside the ZIP:
  - BODY_WEIGHT.json / body_weight.json
  - BODY_RECORD.json / body_record.json
  - BODY_FAT.json   / body_fat.json
  - health_data_body.json
  - *.csv files with weight/bmi/fat columns
  - Nested ZIPs (exports-within-exports)
"""

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Field name mappings ────────────────────────────────────────────────────────
# Maps normalised field names → list of raw keys to try (case-insensitive)
_FIELD_MAP = {
    "timestamp":           ["time", "timestamp", "create_time", "createTime", "date", "Date", "datetime", "recordTime"],
    "weight_kg":           ["weight", "Weight", "bodyWeight", "body_weight", "weightKg", "weight_kg"],
    "bmi":                 ["bmi", "BMI", "bmiVal"],
    "body_fat_pct":        ["fat", "bodyFat", "body_fat", "fatRate", "bodyFatPercent", "fatPercent", "fat_percent"],
    "fat_mass_kg":         ["fatWeight", "fat_weight", "fatMass", "fat_mass"],
    "muscle_mass_kg":      ["muscle", "muscleMass", "muscle_mass", "muscleWeight"],
    "bone_mass_kg":        ["bone", "boneMass", "bone_mass", "boneWeight"],
    "water_pct":           ["water", "bodyWater", "body_water", "waterPercent", "waterRate"],
    "protein_pct":         ["protein", "proteinRate", "proteinPercent"],
    "bmr":                 ["bmr", "BMR", "basalMetabolism", "basicMetabolism", "metabolismRate"],
    "visceral_fat":        ["visceralFat", "visceral_fat", "visceralFatLevel"],
    "metabolic_age":       ["bodyAge", "metabolicAge", "metabolic_age"],
    "lean_mass_kg":        ["leanMass", "lean_mass", "leanBodyMass"],
    "subcutaneous_fat_pct":["subcutaneousFat", "subcutaneous_fat"],
    "skeletal_muscle_pct": ["skeletalMuscle", "skeletal_muscle"],
    "impedance":           ["impedance", "resistance"],
}

# Weight unit detection thresholds (raw value → kg)
# Xiaomi stores weight in different units depending on app/version:
#   - grams (e.g. 75500 → 75.5 kg)  divide by 1000
#   - 0.01 kg units (e.g. 7550 → 75.5 kg) divide by 100
#   - kg directly (e.g. 75.5)
def _to_kg(val) -> Optional[float]:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v > 500:       # likely grams (a person > 500 kg would be extreme)
        return round(v / 1000, 2)
    if v > 300:       # likely 0.01 kg units; 300 in raw = 3 kg (plausible for bone mass)
        return round(v / 100, 2)
    return round(v, 2)


def _to_pct(val) -> Optional[float]:
    """Body fat, water, etc. Some apps store as 2450 = 24.5%. Others as 24.5."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v > 100:       # stored as integer × 100 (e.g. 2450 → 24.50)
        return round(v / 100, 2)
    return round(v, 2)


def _ts_to_date(val) -> Optional[str]:
    """Convert timestamp (seconds or ms) or ISO string to YYYY-MM-DD."""
    if not val:
        return None
    # ISO string
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(val).split(".")[0].split("Z")[0][:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    # Numeric timestamp
    try:
        ts = float(val)
        if ts > 1e11:   # milliseconds
            ts /= 1000
        if ts > 1e9:    # reasonable Unix time (after 2001)
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        pass
    return None


def _get(row: dict, keys: list):
    """Try keys case-insensitively on a dict."""
    lower = {k.lower(): v for k, v in row.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v not in (None, "", 0):
            return v
    return None


def _parse_record(row: dict) -> Optional[dict]:
    """Parse one raw record dict into a normalised body composition dict."""
    date_str = _ts_to_date(_get(row, _FIELD_MAP["timestamp"]))
    if not date_str:
        return None

    raw_weight = _get(row, _FIELD_MAP["weight_kg"])
    weight = _to_kg(raw_weight)
    if not weight:
        return None

    def pct(key):
        v = _get(row, _FIELD_MAP[key])
        return _to_pct(v)

    def mass(key):
        v = _get(row, _FIELD_MAP[key])
        return _to_kg(v)

    def num(key):
        v = _get(row, _FIELD_MAP[key])
        try:
            return round(float(v), 2) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    return {
        "date":                  date_str,
        "weight_kg":             weight,
        "bmi":                   num("bmi"),
        "body_fat_pct":          pct("body_fat_pct"),
        "fat_mass_kg":           mass("fat_mass_kg"),
        "muscle_mass_kg":        mass("muscle_mass_kg"),
        "bone_mass_kg":          mass("bone_mass_kg"),
        "water_pct":             pct("water_pct"),
        "protein_pct":           pct("protein_pct"),
        "bmr":                   num("bmr"),
        "visceral_fat":          num("visceral_fat"),
        "metabolic_age":         num("metabolic_age"),
        "lean_mass_kg":          mass("lean_mass_kg"),
        "subcutaneous_fat_pct":  pct("subcutaneous_fat_pct"),
        "skeletal_muscle_pct":   pct("skeletal_muscle_pct"),
        "impedance":             num("impedance"),
    }


# ── ZIP parsing ────────────────────────────────────────────────────────────────

_BODY_FILE_KEYWORDS = [
    "body_weight", "body_record", "body_fat", "body_composition",
    "weight", "bodyweight", "bodyrecord", "health_data_body",
    "scale", "yunmai", "smartscale",
]


def _is_body_file(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in _BODY_FILE_KEYWORDS) and (n.endswith(".json") or n.endswith(".csv"))


def _parse_json_file(data: bytes) -> list[dict]:
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
    except Exception:
        return []
    # Could be a list, or {"data": [...]} or {"records": [...]} or {"items": [...]}
    if isinstance(obj, list):
        rows = obj
    elif isinstance(obj, dict):
        rows = obj.get("data") or obj.get("records") or obj.get("items") or obj.get("list") or []
        if not rows:
            # Maybe the top-level dict IS a single record
            rows = [obj] if _get(obj, _FIELD_MAP["timestamp"]) else []
    else:
        return []
    return [r for r in rows if isinstance(r, dict)]


def _parse_csv_file(data: bytes) -> list[dict]:
    try:
        text = data.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        return [row for row in reader]
    except Exception:
        return []


def parse_zip(zip_path: str) -> list[dict]:
    """Open ZIP (and nested ZIPs) and return all parsed body composition records."""
    records = []
    _scan_zip(zip_path, records)
    return records


def _scan_zip(zip_path, records: list, depth: int = 0):
    if depth > 3:
        return
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            body_files = [n for n in names if _is_body_file(Path(n).name)]

            # If no obvious body files, scan everything
            candidates = body_files if body_files else [n for n in names if n.endswith((".json", ".csv"))]

            for name in candidates:
                raw = zf.read(name)
                if name.endswith(".json"):
                    rows = _parse_json_file(raw)
                else:
                    rows = _parse_csv_file(raw)

                parsed = [_parse_record(r) for r in rows]
                parsed = [p for p in parsed if p]
                if parsed:
                    print(f"  [{Path(name).name}] {len(parsed)} registros encontrados")
                    records.extend(parsed)

            # Recurse into nested ZIPs
            for name in names:
                if name.endswith(".zip") and depth < 3:
                    data = zf.read(name)
                    _scan_zip(io.BytesIO(data), records, depth + 1)

    except zipfile.BadZipFile:
        pass
    except Exception as e:
        print(f"  [warn] Error leyendo ZIP: {e}")


# ── DB import ─────────────────────────────────────────────────────────────────

def import_to_db(records: list[dict], person: str = "ATM") -> int:
    """Upsert body composition records into nutricion.db. Returns count saved."""
    from tracker.daily_log import DailyLog
    log = DailyLog()
    saved = 0
    for rec in records:
        try:
            log.log_body_composition(rec, person=person, source="xiaomi_zip")
            saved += 1
        except Exception as e:
            print(f"  [warn] No se pudo guardar {rec.get('date')}: {e}")
    log.close()
    return saved
