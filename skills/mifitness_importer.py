"""
MiFitnessImporter — parse Mi Fitness / Zepp Life / Mi Home export ZIPs and
load body composition data into the local SQLite database.

Supported export formats
─────────────────────────
• Zepp Life (formerly Mi Fit)
    Profile → My Account → Zepp Account → Privacy → Export data
    ZIP contains: BODY_WEIGHT/BODY_WEIGHT_<ts>.json

• Mi Health / account.xiaomi.com
    account.xiaomi.com → Privacy → Manage data → Export
    ZIP contains: health_body.json or similar flat files

• Mi Fitness (newer Xiaomi app)
    Profile → Settings → Account → Export health data
    Similar flat JSON structure

Field names vary across app versions; this parser tries all known aliases.
Weight is detected as grams (>500) or kg automatically.
"""

import json
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── Field aliases ─────────────────────────────────────────────────────────────
# Maps our canonical field name → list of known aliases in exported JSON
_ALIASES: dict[str, list[str]] = {
    'weight_kg':             ['weight', 'weightKg', 'weight_kg', 'bodyWeight'],
    'bmi':                   ['bmi', 'BMI', 'bodyMassIndex'],
    'body_fat_pct':          ['bodyFatRate', 'body_fat_rate', 'fatRate', 'bodyFat',
                              'fatPercent', 'fat_rate', 'bodyFatRatio'],
    'muscle_mass_kg':        ['muscleMass', 'muscle_mass', 'musclesMass', 'muscleMassKg'],
    'bone_mass_kg':          ['boneMass', 'bone_mass', 'boneMassKg'],
    'water_pct':             ['moisture', 'bodyWater', 'water', 'waterPercent',
                              'body_water_rate', 'waterRate'],
    'protein_pct':           ['protein', 'proteinRate', 'protein_rate', 'proteinPercent',
                              'proteinRatio'],
    'bmr':                   ['bmr', 'BMR', 'basalMetabolicRate', 'basal_metabolic_rate'],
    'visceral_fat':          ['visceralFat', 'visceral_fat', 'visceralFatGrade',
                              'visceral_fat_grade', 'visceralFatIndex'],
    'metabolic_age':         ['metabolicAge', 'metabolic_age'],
    'lean_mass_kg':          ['lbm', 'leanBodyMass', 'lean_body_mass', 'leanMass',
                              'lean_mass', 'leanBodyMassKg'],
    'subcutaneous_fat_pct':  ['subcutaneousFat', 'subcutaneous_fat',
                              'subcutaneousFatRate', 'subcutaneousFatRatio'],
    'skeletal_muscle_pct':   ['skeletalMuscle', 'skeletal_muscle', 'skeletalMuscleMass',
                              'skeletal_muscle_rate', 'skeletalMuscleRate'],
    'fat_mass_kg':           ['fatMass', 'fat_mass', 'fatMassKg', 'fatControlWeight'],
    'impedance':             ['impedance', 'bodyResistance', 'resistance'],
}

# Build reverse lookup: alias → canonical
_ALIAS_MAP: dict[str, str] = {}
for _canon, _aliases in _ALIASES.items():
    for _a in _aliases:
        _ALIAS_MAP[_a] = _canon
        _ALIAS_MAP[_a.lower()] = _canon

# Files inside the ZIP that contain body composition data
_BODY_WEIGHT_PATTERNS = [
    r'BODY_WEIGHT.*\.json',
    r'body_weight.*\.json',
    r'health_body.*\.json',
    r'weight.*\.json',
    r'scale.*\.json',
    r'body.*composition.*\.json',
]


class MiFitnessImporter:

    def __init__(self):
        from tracker.daily_log import DailyLog
        self.log = DailyLog()

    def close(self):
        self.log.close()

    # ── Public API ────────────────────────────────────────────────────────────

    def import_zip(
        self,
        zip_path: str | Path,
        person: str = 'ATM',
        dry_run: bool = False,
    ) -> dict:
        """
        Parse a Mi Fitness / Zepp Life export ZIP and upsert records into SQLite.

        Returns a summary dict with keys: total, imported, skipped, errors.
        """
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise FileNotFoundError(zip_path)

        with zipfile.ZipFile(zip_path) as zf:
            body_files = self._find_body_files(zf)
            if not body_files:
                raise ValueError(
                    "No se encontraron archivos de composición corporal en el ZIP.\n"
                    "Archivos en el ZIP:\n" +
                    "\n".join(f"  {n}" for n in zf.namelist()[:30])
                )

            records: list[dict] = []
            for name in body_files:
                raw = json.loads(zf.read(name).decode('utf-8'))
                records.extend(self._parse_file(raw, name))

        total   = len(records)
        imported = 0
        skipped  = 0
        errors   = []

        for rec in records:
            try:
                if dry_run:
                    imported += 1
                    continue
                self.log.log_body_composition(rec, person=person, source='mifitness')
                imported += 1
            except Exception as e:
                errors.append(f"{rec.get('date', '?')}: {e}")
                skipped += 1

        return {
            'total':    total,
            'imported': imported,
            'skipped':  skipped,
            'errors':   errors,
            'records':  records if dry_run else [],
        }

    def import_json(
        self,
        json_path: str | Path,
        person: str = 'ATM',
        dry_run: bool = False,
    ) -> dict:
        """Import from a bare JSON file (not zipped)."""
        json_path = Path(json_path)
        raw = json.loads(json_path.read_text(encoding='utf-8'))
        records = self._parse_file(raw, json_path.name)
        imported = skipped = 0
        errors: list[str] = []
        for rec in records:
            try:
                if not dry_run:
                    self.log.log_body_composition(rec, person=person, source='mifitness')
                imported += 1
            except Exception as e:
                errors.append(f"{rec.get('date', '?')}: {e}")
                skipped += 1
        return {'total': len(records), 'imported': imported, 'skipped': skipped,
                'errors': errors, 'records': records if dry_run else []}

    # ── File discovery ────────────────────────────────────────────────────────

    @staticmethod
    def _find_body_files(zf: zipfile.ZipFile) -> list[str]:
        matched = []
        for name in zf.namelist():
            basename = name.split('/')[-1]
            for pat in _BODY_WEIGHT_PATTERNS:
                if re.search(pat, basename, re.IGNORECASE):
                    matched.append(name)
                    break
        return matched

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_file(self, raw: object, filename: str) -> list[dict]:
        """Parse a JSON value (list or dict) from one file into normalized records."""
        # Unwrap common wrapper keys
        if isinstance(raw, dict):
            for key in ('data', 'records', 'items', 'list', 'body', 'results'):
                if isinstance(raw.get(key), list):
                    raw = raw[key]
                    break
            else:
                # Single record dict
                raw = [raw]
        if not isinstance(raw, list):
            return []

        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            rec = self._normalize(item)
            if rec is None:
                continue
            out.append(rec)
        return out

    def _normalize(self, item: dict) -> Optional[dict]:
        """Normalize one raw dict into our canonical schema. Returns None if unusable."""
        # ── Date ──────────────────────────────────────────────────────────────
        date_str = self._extract_date(item)
        if date_str is None:
            return None

        # ── Fields ────────────────────────────────────────────────────────────
        out: dict = {'date': date_str}
        for raw_key, raw_val in item.items():
            canon = _ALIAS_MAP.get(raw_key) or _ALIAS_MAP.get(raw_key.lower())
            if canon and raw_val is not None and raw_val != '':
                try:
                    out[canon] = float(raw_val)
                except (TypeError, ValueError):
                    pass

        # ── Weight unit fix ───────────────────────────────────────────────────
        if 'weight_kg' in out:
            w = out['weight_kg']
            if w > 500:          # stored in grams
                out['weight_kg'] = round(w / 1000, 2)
            elif w > 200:        # stored in 100g units (unlikely but seen in some apps)
                out['weight_kg'] = round(w / 100, 2)

        # Require at least weight
        if 'weight_kg' not in out or out['weight_kg'] <= 0:
            return None

        # ── Derive fat_mass_kg if missing ─────────────────────────────────────
        if 'fat_mass_kg' not in out and 'body_fat_pct' in out:
            out['fat_mass_kg'] = round(out['weight_kg'] * out['body_fat_pct'] / 100, 2)

        # ── Derive lean_mass_kg if missing ────────────────────────────────────
        if 'lean_mass_kg' not in out and 'fat_mass_kg' in out:
            out['lean_mass_kg'] = round(out['weight_kg'] - out['fat_mass_kg'], 2)

        return out

    # ── Date extraction ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_date(item: dict) -> Optional[str]:
        for key in ('time', 'date', 'dateTime', 'date_time', 'startTime',
                    'start_time', 'timestamp', 'createTime', 'recordDate'):
            val = item.get(key)
            if val is None:
                continue
            val = str(val).strip()
            # ISO date string: "2024-01-15" or "2024-01-15 08:30:00" or "2024-01-15T08:30:00"
            m = re.match(r'(\d{4}-\d{2}-\d{2})', val)
            if m:
                return m.group(1)
            # Unix timestamp in seconds (10 digits)
            if re.match(r'^\d{10}$', val):
                return datetime.fromtimestamp(int(val)).strftime('%Y-%m-%d')
            # Unix timestamp in milliseconds (13 digits)
            if re.match(r'^\d{13}$', val):
                return datetime.fromtimestamp(int(val) / 1000).strftime('%Y-%m-%d')
            # Date-only compact: "20240115"
            m2 = re.match(r'^(\d{4})(\d{2})(\d{2})$', val)
            if m2:
                return f"{m2.group(1)}-{m2.group(2)}-{m2.group(3)}"
        return None

    # ── Pretty summary ────────────────────────────────────────────────────────

    @staticmethod
    def format_record(rec: dict) -> str:
        lines = [f"  📅 {rec['date']}"]
        pairs = [
            ('weight_kg',            '⚖️  Peso',            'kg'),
            ('bmi',                  '📊 BMI',              ''),
            ('body_fat_pct',         '🫧 Grasa corporal',   '%'),
            ('fat_mass_kg',          '   Masa grasa',       'kg'),
            ('muscle_mass_kg',       '💪 Músculo',          'kg'),
            ('bone_mass_kg',         '🦴 Masa ósea',        'kg'),
            ('water_pct',            '💧 Agua',             '%'),
            ('protein_pct',          '🥩 Proteína',         '%'),
            ('bmr',                  '🔥 TMB',              'kcal'),
            ('visceral_fat',         '🫀 Grasa visceral',   ''),
            ('metabolic_age',        '🧬 Edad metabólica',  'años'),
            ('lean_mass_kg',         '   Masa magra',       'kg'),
            ('subcutaneous_fat_pct', '   G. subcutánea',    '%'),
            ('skeletal_muscle_pct',  '   Músculo esq.',     '%'),
        ]
        for key, label, unit in pairs:
            if key in rec and rec[key] is not None:
                val = rec[key]
                fmt = f"{val:.1f}" if isinstance(val, float) else str(val)
                lines.append(f"     {label:<22} {fmt} {unit}".rstrip())
        return "\n".join(lines)
