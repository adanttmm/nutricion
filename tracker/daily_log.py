import sqlite3
from pathlib import Path
from datetime import date


class DailyLog:
    DB_PATH = "data/tracking/nutricion.db"

    def __init__(self):
        Path(self.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.DB_PATH)
        self._init_db()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS meals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                meal_type   TEXT NOT NULL,
                name        TEXT NOT NULL,
                calories    REAL,
                protein_g   REAL,
                carbs_g     REAL,
                fat_g       REAL,
                notes       TEXT,
                logged_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS daily_goals (
                date            TEXT PRIMARY KEY,
                calories_target REAL,
                protein_target  REAL,
                carbs_target    REAL,
                fat_target      REAL,
                plan_name       TEXT
            );

            CREATE TABLE IF NOT EXISTS body_metrics (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                person      TEXT NOT NULL DEFAULT 'ATM',
                weight_kg   REAL,
                notes       TEXT,
                logged_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS body_composition (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                date                 TEXT NOT NULL,
                person               TEXT NOT NULL DEFAULT 'ATM',
                weight_kg            REAL,
                bmi                  REAL,
                body_fat_pct         REAL,
                fat_mass_kg          REAL,
                muscle_mass_kg       REAL,
                bone_mass_kg         REAL,
                water_pct            REAL,
                protein_pct          REAL,
                bmr                  REAL,
                visceral_fat         REAL,
                metabolic_age        REAL,
                lean_mass_kg         REAL,
                subcutaneous_fat_pct REAL,
                skeletal_muscle_pct  REAL,
                impedance            REAL,
                source               TEXT DEFAULT 'manual',
                logged_at            TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, person)
            );
        """)
        self.conn.commit()
        # Migration: add person column to existing body_metrics tables
        try:
            self.conn.execute("ALTER TABLE body_metrics ADD COLUMN person TEXT NOT NULL DEFAULT 'ATM'")
            self.conn.commit()
        except Exception:
            pass  # column already exists

    def log_meal(
        self,
        meal_type: str,
        name: str,
        calories: float = None,
        protein_g: float = None,
        carbs_g: float = None,
        fat_g: float = None,
        notes: str = None,
        log_date: date = None,
    ):
        if log_date is None:
            log_date = date.today()
        self.conn.execute(
            """INSERT INTO meals (date, meal_type, name, calories, protein_g, carbs_g, fat_g, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (log_date.isoformat(), meal_type, name, calories, protein_g, carbs_g, fat_g, notes),
        )
        self.conn.commit()

    def set_daily_goal(
        self,
        calories: float,
        protein_g: float,
        carbs_g: float,
        fat_g: float,
        plan_name: str = "Plan actual",
        log_date: date = None,
    ):
        if log_date is None:
            log_date = date.today()
        self.conn.execute(
            """INSERT OR REPLACE INTO daily_goals
               (date, calories_target, protein_target, carbs_target, fat_target, plan_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (log_date.isoformat(), calories, protein_g, carbs_g, fat_g, plan_name),
        )
        self.conn.commit()

    def log_weight(self, weight_kg: float, person: str = 'ATM', notes: str = None, log_date: date = None):
        if log_date is None:
            log_date = date.today()
        # Upsert: one entry per (date, person)
        self.conn.execute(
            "DELETE FROM body_metrics WHERE date = ? AND person = ?",
            (log_date.isoformat(), person.upper()),
        )
        self.conn.execute(
            "INSERT INTO body_metrics (date, person, weight_kg, notes) VALUES (?, ?, ?, ?)",
            (log_date.isoformat(), person.upper(), weight_kg, notes),
        )
        self.conn.commit()

    def get_daily_summary(self, summary_date: date = None) -> dict:
        if summary_date is None:
            summary_date = date.today()

        meals = self.conn.execute(
            """SELECT meal_type, name, calories, protein_g, carbs_g, fat_g
               FROM meals WHERE date = ? ORDER BY id""",
            (summary_date.isoformat(),),
        ).fetchall()

        goal = self.conn.execute(
            """SELECT calories_target, protein_target, carbs_target, fat_target
               FROM daily_goals WHERE date = ?""",
            (summary_date.isoformat(),),
        ).fetchone()

        totals = {
            "calories": sum(m[2] or 0 for m in meals),
            "protein_g": sum(m[3] or 0 for m in meals),
            "carbs_g": sum(m[4] or 0 for m in meals),
            "fat_g": sum(m[5] or 0 for m in meals),
        }

        return {
            "date": summary_date.isoformat(),
            "meals": [
                {"type": m[0], "name": m[1], "calories": m[2],
                 "protein_g": m[3], "carbs_g": m[4], "fat_g": m[5]}
                for m in meals
            ],
            "totals": totals,
            "goals": (
                {"calories": goal[0], "protein_g": goal[1], "carbs_g": goal[2], "fat_g": goal[3]}
                if goal else None
            ),
        }

    def get_weekly_data(self, week_start: date) -> list:
        from datetime import timedelta
        dates = [(week_start + timedelta(days=i)).isoformat() for i in range(7)]
        placeholders = ",".join("?" * 7)
        rows = self.conn.execute(
            f"""SELECT date, SUM(calories), SUM(protein_g), SUM(carbs_g), SUM(fat_g)
                FROM meals WHERE date IN ({placeholders})
                GROUP BY date ORDER BY date""",
            dates,
        ).fetchall()
        return [
            {"date": r[0], "calories": r[1], "protein_g": r[2], "carbs_g": r[3], "fat_g": r[4]}
            for r in rows
        ]

    def log_body_composition(self, data: dict, person: str = 'ATM', source: str = 'manual'):
        """Upsert a full body composition reading (one per day per person)."""
        person = person.upper()
        fields = [
            'weight_kg', 'bmi', 'body_fat_pct', 'fat_mass_kg', 'muscle_mass_kg',
            'bone_mass_kg', 'water_pct', 'protein_pct', 'bmr', 'visceral_fat',
            'metabolic_age', 'lean_mass_kg', 'subcutaneous_fat_pct',
            'skeletal_muscle_pct', 'impedance',
        ]
        cols   = ', '.join(fields)
        params = ', '.join('?' * len(fields))
        vals   = [data.get(f) for f in fields]
        self.conn.execute(
            f"DELETE FROM body_composition WHERE date = ? AND person = ?",
            (data['date'], person),
        )
        self.conn.execute(
            f"""INSERT INTO body_composition (date, person, {cols}, source)
                VALUES (?, ?, {params}, ?)""",
            [data['date'], person, *vals, source],
        )
        self.conn.commit()

    def get_body_composition_history(self, limit: int = 90, person: str = 'ATM') -> list:
        cols = (
            'date, weight_kg, bmi, body_fat_pct, fat_mass_kg, muscle_mass_kg, '
            'bone_mass_kg, water_pct, protein_pct, bmr, visceral_fat, metabolic_age, '
            'lean_mass_kg, subcutaneous_fat_pct, skeletal_muscle_pct, impedance, source'
        )
        rows = self.conn.execute(
            f"SELECT {cols} FROM body_composition WHERE person = ? "
            "ORDER BY date DESC LIMIT ?",
            (person.upper(), limit),
        ).fetchall()
        keys = [c.strip() for c in cols.split(',')]
        return [dict(zip(keys, r)) for r in rows]

    def get_weight_history(self, limit: int = 60, person: str = 'ATM') -> list:
        rows = self.conn.execute(
            "SELECT date, weight_kg, notes FROM body_metrics WHERE person = ? ORDER BY date DESC LIMIT ?",
            (person.upper(), limit),
        ).fetchall()
        return [{"date": r[0], "weight_kg": r[1], "notes": r[2]} for r in rows]

    def close(self):
        self.conn.close()
