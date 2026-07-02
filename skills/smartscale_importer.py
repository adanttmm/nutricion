"""
SmartScaleImporter — parse SmartScaleConnect JSON output and load into SQLite.

SmartScaleConnect (https://github.com/AlexxIT/SmartScaleConnect) exports a JSON
array of Weight structs with these fields (Date + Weight required, rest optional):
  Date, Weight, BMI, BodyFat, BodyWater, BoneMass, MetabolicAge, MuscleMass,
  PhysiqueRating, ProteinMass, VisceralFat, BasalMetabolism, HeartRate,
  SkeletalMuscleMass, User, Source

Notes on unit conversions:
  ProteinMass      → stored in kg by SSC; we derive protein_pct = kg/weight*100
  SkeletalMuscleMass → kg; we derive skeletal_muscle_pct = kg/weight*100
"""

import json
from datetime import datetime
from typing import Optional

# Direct field mappings: SmartScaleConnect key → our canonical column
_FIELD_MAP = {
    'Weight':          'weight_kg',
    'BMI':             'bmi',
    'BodyFat':         'body_fat_pct',
    'BodyWater':       'water_pct',
    'BoneMass':        'bone_mass_kg',
    'MetabolicAge':    'metabolic_age',
    'MuscleMass':      'muscle_mass_kg',
    'VisceralFat':     'visceral_fat',
    'BasalMetabolism': 'bmr',
}

_DISPLAY = [
    ('weight_kg',      '⚖️  Peso',           'kg'),
    ('bmi',            '📊 IMC',             ''),
    ('body_fat_pct',   '🫧 Grasa corporal',  '%'),
    ('fat_mass_kg',    '   Masa grasa',      'kg'),
    ('muscle_mass_kg', '💪 Músculo',         'kg'),
    ('lean_mass_kg',   '   Masa magra',      'kg'),
    ('bone_mass_kg',   '🦴 Masa ósea',       'kg'),
    ('water_pct',      '💧 Agua',            '%'),
    ('protein_pct',    '🥩 Proteína',        '%'),
    ('bmr',            '🔥 TMB',             'kcal'),
    ('visceral_fat',   '🫀 Grasa visceral',  ''),
    ('metabolic_age',  '🧬 Edad metabólica', 'años'),
]


class SmartScaleImporter:

    def __init__(self):
        from tracker.daily_log import DailyLog
        self.log = DailyLog()

    def close(self):
        self.log.close()

    # ── Public API ────────────────────────────────────────────────────────────

    def import_json_str(
        self,
        data: str,
        person: str = 'ATM',
        dry_run: bool = False,
    ) -> dict:
        """Parse a JSON string (array or single object) and upsert into SQLite."""
        raw_list = json.loads(data.strip() or '[]')
        if isinstance(raw_list, dict):
            raw_list = [raw_list]

        normalized = [r for item in raw_list if (r := self._normalize(item))]

        imported = skipped = 0
        errors: list[str] = []
        for rec in normalized:
            try:
                if not dry_run:
                    self.log.log_body_composition(rec, person=person, source='xiaomi_home')
                imported += 1
            except Exception as e:
                errors.append(f"{rec.get('date', '?')}: {e}")
                skipped += 1

        return {
            'total':      len(raw_list),
            'normalized': len(normalized),
            'imported':   imported,
            'skipped':    skipped,
            'errors':     errors,
            'records':    normalized if dry_run else [],
        }

    # ── Normalization ─────────────────────────────────────────────────────────

    def _normalize(self, raw: dict) -> Optional[dict]:
        # Date — SSC emits ISO 8601 with timezone
        date_raw = raw.get('Date') or raw.get('date') or raw.get('time')
        if not date_raw:
            return None
        try:
            date_str = datetime.fromisoformat(
                str(date_raw).replace('Z', '+00:00')
            ).strftime('%Y-%m-%d')
        except Exception:
            return None

        out: dict = {'date': date_str}

        # Direct mappings
        for ssc_key, canon in _FIELD_MAP.items():
            val = raw.get(ssc_key)
            if val is not None and val != 0:
                out[canon] = float(val)

        if 'weight_kg' not in out or out['weight_kg'] <= 0:
            return None

        w = out['weight_kg']

        # ProteinMass (kg) → protein_pct
        pm = raw.get('ProteinMass')
        if pm and float(pm) > 0:
            out['protein_pct'] = round(float(pm) / w * 100, 1)

        # SkeletalMuscleMass (kg) → skeletal_muscle_pct; fill muscle_mass_kg if absent
        smm = raw.get('SkeletalMuscleMass')
        if smm and float(smm) > 0:
            out['skeletal_muscle_pct'] = round(float(smm) / w * 100, 1)
            if 'muscle_mass_kg' not in out:
                out['muscle_mass_kg'] = float(smm)

        # Derived fat_mass_kg and lean_mass_kg
        if 'fat_mass_kg' not in out and 'body_fat_pct' in out:
            out['fat_mass_kg'] = round(w * out['body_fat_pct'] / 100, 2)
        if 'lean_mass_kg' not in out and 'fat_mass_kg' in out:
            out['lean_mass_kg'] = round(w - out['fat_mass_kg'], 2)

        return out

    # ── Pretty output ─────────────────────────────────────────────────────────

    @staticmethod
    def format_record(rec: dict) -> str:
        lines = [f"  📅 {rec['date']}"]
        for key, label, unit in _DISPLAY:
            val = rec.get(key)
            if val is None:
                continue
            fmt = f"{val:.1f}" if isinstance(val, float) else str(val)
            lines.append(f"     {label:<22} {fmt} {unit}".rstrip())
        return "\n".join(lines)
