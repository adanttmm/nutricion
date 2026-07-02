"""
RatingsLoader — ingest weekly ratings exported from the browser and build menu context.

Flow:
  1. User rates dishes in the browser (stars + tag per person).
  2. User clicks "Exportar valoraciones" → downloads ratings_YYYY-MM-DD.json.
  3. User places the file in data/ratings/.
  4. actualizar_menu.sh calls `python main.py importar-ratings` (or semana-completa does it).
  5. RatingsLoader merges the file into data/ratings_history.json.
  6. MenuGeneratorSkill receives the context and avoids/repeats dishes accordingly.
  7. actualizar_site.sh commits data/ratings/ + data/ratings_history.json to GitHub.
"""

import json
import re
from datetime import date
from pathlib import Path

RATINGS_DIR = Path("data/ratings")
HISTORY_PATH = Path("data/ratings_history.json")
PERSONS = ["atm", "iob"]


class RatingsLoader:
    def __init__(self):
        RATINGS_DIR.mkdir(parents=True, exist_ok=True)
        self._history = self._load_history()

    # ── Public API ────────────────────────────────────────────────────────────

    def ingest_pending(self) -> int:
        """Scan data/ratings/ for unprocessed JSON files. Also imports weights.json. Returns count ingested."""
        ingested = set(self._history.get("ingested_files", []))
        new_count = 0
        for path in sorted(RATINGS_DIR.glob("ratings_*.json")):
            if path.name in ingested:
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  ⚠ No se pudo leer {path.name}: {e}")
                continue
            week_key = self._week_key_from_filename(path.name)
            n_dishes = self._merge_week(week_key, raw)
            self._write_to_db(week_key, raw)
            ingested.add(path.name)
            new_count += 1
            print(f"  ✅ Valoraciones ingresadas: {path.name} ({n_dishes} platos)")

        self._history["ingested_files"] = sorted(ingested)
        self._history["last_updated"] = date.today().isoformat()
        self._save_history()

        # Import weight measurements if present
        weights_path = RATINGS_DIR / "weights.json"
        if weights_path.exists():
            self._import_weights(weights_path)

        return new_count

    def backfill_db(self) -> int:
        """Write all ratings already in ratings_history.json into the DB. Safe to run multiple times."""
        from tracker.daily_log import DailyLog
        log = DailyLog()
        count = 0
        for title, data in self._history.get("dishes", {}).items():
            for week_entry in data.get("ratings", []):
                week = week_entry.get("week", "")
                for pk in PERSONS:
                    pr = week_entry.get(pk) or {}
                    stars = int(pr.get("stars") or 0) or None
                    tag = str(pr.get("tag") or "")
                    if stars or tag:
                        log.log_rating(title, week, pk, stars=stars, tag=tag)
                        count += 1
        log.close()
        return count

    def _import_weights(self, path: Path):
        """Import per-person weight entries from JSON into SQLite body_metrics."""
        try:
            from datetime import date as _date
            from tracker.daily_log import DailyLog
            data = json.loads(path.read_text(encoding="utf-8"))
            log = DailyLog()
            counts = {}
            for person, entries in data.items():
                if not isinstance(entries, list):
                    continue
                count = 0
                for entry in entries:
                    try:
                        d = _date.fromisoformat(entry["date"])
                        kg = float(entry["kg"])
                        log.log_weight(kg, person=person.upper(), log_date=d)
                        count += 1
                    except Exception:
                        pass
                counts[person.upper()] = count
            log.close()
            parts = ", ".join(f"{p}={n}" for p, n in counts.items())
            print(f"  ✅ Pesos importados: {parts}")
        except Exception as e:
            print(f"  ⚠ No se pudieron importar pesos: {e}")

    def build_menu_context(self) -> str:
        """Return a formatted block to inject into the menu generator prompt."""
        dishes = self._history.get("dishes", {})
        if not dishes:
            return ""

        avoid, favorites = [], []
        for title, data in dishes.items():
            avg = data.get("avg_stars", 0)
            all_tags = data.get("all_tags", [])
            last = data.get("last_rating", {})

            parts = []
            for pk in PERSONS:
                pr = last.get(pk, {})
                s = pr.get("stars", 0) or 0
                t = pr.get("tag", "") or ""
                if not s and not t:
                    continue
                label = f"{pk.upper()}: {s}★" if s else pk.upper()
                if t == "favorito":
                    label += " ❤️"
                elif t == "repetir":
                    label += " 🔄"
                elif t == "no":
                    label += " 🚫"
                parts.append(label)

            detail = f" ({', '.join(parts)})" if parts else ""
            times = data.get("times_served", 1)
            served = f" — servido {times}×" if times > 1 else ""

            if "no" in all_tags or avg <= 2:
                avoid.append(f"  • {title}{detail}{served}")
            elif "favorito" in all_tags or "repetir" in all_tags or avg >= 4:
                favorites.append(f"  • {title}{detail}{served}")

        if not avoid and not favorites:
            return ""

        lines = ["VALORACIONES DE SEMANAS ANTERIORES (considera estas preferencias al diseñar el menú):"]
        if avoid:
            lines.append("\nEVITAR — mal calificados o marcados 🚫 (no incluir a menos que sea indispensable):")
            lines.extend(avoid)
        if favorites:
            lines.append("\nFAVORITOS — bien calificados o marcados ❤️/🔄 (incluir si encaja en el plan nutricional):")
            lines.extend(favorites)

        return "\n".join(lines)

    def summary(self) -> dict:
        """Return a brief summary dict for CLI display."""
        dishes = self._history.get("dishes", {})
        avoid = sum(
            1 for d in dishes.values()
            if "no" in d.get("all_tags", []) or d.get("avg_stars", 0) <= 2
        )
        faves = sum(
            1 for d in dishes.values()
            if "favorito" in d.get("all_tags", [])
            or "repetir" in d.get("all_tags", [])
            or d.get("avg_stars", 0) >= 4
        )
        return {
            "total_dishes": len(dishes),
            "favorites": faves,
            "avoid": avoid,
            "weeks_ingested": len(self._history.get("ingested_files", [])),
            "last_updated": self._history.get("last_updated", "—"),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load_history(self) -> dict:
        if HISTORY_PATH.exists():
            try:
                return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"dishes": {}, "ingested_files": [], "last_updated": ""}

    def _save_history(self):
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text(
            json.dumps(self._history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_to_db(self, week_key: str, raw: dict):
        """Upsert ratings from a weekly JSON file into nutricion.db."""
        try:
            from tracker.daily_log import DailyLog
            log = DailyLog()
            for _slug, entry in raw.items():
                title = (entry.get("title") or "").strip()
                if not title:
                    continue
                for pk in PERSONS:
                    pr = entry.get(pk) or {}
                    stars = int(pr.get("stars") or 0) or None
                    tag = str(pr.get("tag") or "")
                    if stars or tag:
                        log.log_rating(title, week_key, pk, stars=stars, tag=tag)
            log.close()
        except Exception as e:
            print(f"  ⚠ No se pudieron guardar valoraciones en DB: {e}")

    @staticmethod
    def _week_key_from_filename(name: str) -> str:
        m = re.search(r"ratings_(.+)\.json", name)
        return m.group(1) if m else name

    def _merge_week(self, week_key: str, raw: dict) -> int:
        """Merge one week's raw ratings into history. Returns number of dishes processed."""
        dishes = self._history.setdefault("dishes", {})
        processed = 0
        for _slug, entry in raw.items():
            title = (entry.get("title") or "").strip()
            if not title:
                continue

            rec = dishes.setdefault(title, {
                "ratings": [],
                "avg_stars": 0,
                "all_tags": [],
                "last_rating": {},
                "times_served": 0,
            })

            week_entry: dict = {"week": week_key}
            for pk in PERSONS:
                pr = entry.get(pk) or {}
                s = int(pr.get("stars", 0) or 0)
                t = str(pr.get("tag", "") or "")
                if s or t:
                    week_entry[pk] = {"stars": s, "tag": t}
                    rec["last_rating"][pk] = {"stars": s, "tag": t}
                    if t and t not in rec["all_tags"]:
                        rec["all_tags"].append(t)

            if not any(r.get("week") == week_key for r in rec["ratings"]):
                rec["ratings"].append(week_entry)
                rec["times_served"] = len(rec["ratings"])

            # Recompute avg across all recorded ratings
            all_stars = [
                p_data["stars"]
                for r in rec["ratings"]
                for pk in PERSONS
                if isinstance(p_data := r.get(pk, {}), dict) and p_data.get("stars", 0)
            ]
            rec["avg_stars"] = round(sum(all_stars) / len(all_stars), 1) if all_stars else 0
            processed += 1

        return processed
