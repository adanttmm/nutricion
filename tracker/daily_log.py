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
                date            TEXT NOT NULL,
                person          TEXT NOT NULL DEFAULT 'ATM',
                calories_target REAL,
                protein_target  REAL,
                carbs_target    REAL,
                fat_target      REAL,
                plan_name       TEXT,
                PRIMARY KEY (date, person)
            );

            CREATE TABLE IF NOT EXISTS daily_ingredients (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                person          TEXT NOT NULL,
                meal_type       TEXT NOT NULL,
                ingredient_name TEXT NOT NULL,
                quantity_g      REAL,
                logged_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, person, meal_type, ingredient_name)
            );

            CREATE TABLE IF NOT EXISTS body_metrics (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                person      TEXT NOT NULL DEFAULT 'ATM',
                weight_kg   REAL,
                notes       TEXT,
                logged_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS dish_ratings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe      TEXT NOT NULL,
                week        TEXT NOT NULL,
                person      TEXT NOT NULL,
                stars       INTEGER,
                tag         TEXT,
                logged_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(recipe, week, person)
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
        # Migrations: add columns to tables that pre-date the person/source dimensions
        for stmt in (
            "ALTER TABLE body_metrics ADD COLUMN person TEXT NOT NULL DEFAULT 'ATM'",
            "ALTER TABLE meals ADD COLUMN person TEXT NOT NULL DEFAULT 'ATM'",
            "ALTER TABLE meals ADD COLUMN source TEXT NOT NULL DEFAULT 'logged'",
        ):
            try:
                self.conn.execute(stmt)
                self.conn.commit()
            except Exception:
                pass  # column already exists
        self._migrate_daily_goals_person()

    def _migrate_daily_goals_person(self):
        """daily_goals originally had `date` as its sole primary key (single-person).
        Rebuild it with a (date, person) composite key, carrying old rows forward as 'ATM'."""
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(daily_goals)").fetchall()]
        if 'person' in cols:
            return
        self.conn.executescript("""
            ALTER TABLE daily_goals RENAME TO daily_goals_old;
            CREATE TABLE daily_goals (
                date            TEXT NOT NULL,
                person          TEXT NOT NULL DEFAULT 'ATM',
                calories_target REAL,
                protein_target  REAL,
                carbs_target    REAL,
                fat_target      REAL,
                plan_name       TEXT,
                PRIMARY KEY (date, person)
            );
            INSERT INTO daily_goals (date, person, calories_target, protein_target, carbs_target, fat_target, plan_name)
                SELECT date, 'ATM', calories_target, protein_target, carbs_target, fat_target, plan_name FROM daily_goals_old;
            DROP TABLE daily_goals_old;
        """)
        self.conn.commit()

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
        person: str = 'ATM',
        source: str = 'logged',
    ):
        if log_date is None:
            log_date = date.today()
        self.conn.execute(
            """INSERT INTO meals (date, meal_type, name, calories, protein_g, carbs_g, fat_g, notes, person, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (log_date.isoformat(), meal_type, name, calories, protein_g, carbs_g, fat_g, notes,
             person.upper(), source),
        )
        self.conn.commit()

    def replace_planned_meal(
        self,
        log_date: date,
        person: str,
        meal_type: str,
        name: str,
        calories: float = None,
        protein_g: float = None,
        carbs_g: float = None,
        fat_g: float = None,
    ):
        """Idempotent upsert for auto-populated menu nutrition: one 'planned' row
        per (date, person, meal_type) — safe to call every time the site/menu rebuilds."""
        person = person.upper()
        d = log_date.isoformat() if hasattr(log_date, 'isoformat') else log_date
        self.conn.execute(
            "DELETE FROM meals WHERE date = ? AND person = ? AND meal_type = ? AND source = 'planned'",
            (d, person, meal_type),
        )
        self.conn.execute(
            """INSERT INTO meals (date, meal_type, name, calories, protein_g, carbs_g, fat_g, person, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'planned')""",
            (d, meal_type, name, calories, protein_g, carbs_g, fat_g, person),
        )
        self.conn.commit()

    def replace_daily_ingredients(self, log_date: date, person: str, meal_type: str, ingredients: list):
        """Idempotent upsert of a meal's ingredient quantities for one (date, person, meal_type).
        `ingredients`: list of {"name": str, "quantity_g": float}."""
        person = person.upper()
        d = log_date.isoformat() if hasattr(log_date, 'isoformat') else log_date
        self.conn.execute(
            "DELETE FROM daily_ingredients WHERE date = ? AND person = ? AND meal_type = ?",
            (d, person, meal_type),
        )
        for ing in ingredients:
            if not ing.get('quantity_g'):
                continue
            self.conn.execute(
                """INSERT OR REPLACE INTO daily_ingredients (date, person, meal_type, ingredient_name, quantity_g)
                   VALUES (?, ?, ?, ?, ?)""",
                (d, person, meal_type, ing['name'], ing['quantity_g']),
            )
        self.conn.commit()

    def get_nutrition_by_day(self, start_date: date = None, end_date: date = None, person: str = None) -> list:
        """Planned (menu-derived) nutrition, one row per meal. Filterable by date range/person."""
        query = "SELECT date, person, meal_type, name, calories, protein_g, carbs_g, fat_g FROM meals WHERE source = 'planned'"
        params: list = []
        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat() if hasattr(start_date, 'isoformat') else start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat() if hasattr(end_date, 'isoformat') else end_date)
        if person:
            query += " AND person = ?"
            params.append(person.upper())
        query += " ORDER BY date, person, meal_type"
        rows = self.conn.execute(query, params).fetchall()
        return [
            {"date": r[0], "person": r[1], "meal_type": r[2], "name": r[3],
             "calories": r[4], "protein_g": r[5], "carbs_g": r[6], "fat_g": r[7]}
            for r in rows
        ]

    def get_ingredients_by_day(self, log_date: date = None, person: str = None) -> list:
        """Ingredient quantities per day, optionally filtered to a single date and/or person."""
        query = "SELECT date, person, meal_type, ingredient_name, quantity_g FROM daily_ingredients"
        conditions = []
        params: list = []
        if log_date:
            conditions.append("date = ?")
            params.append(log_date.isoformat() if hasattr(log_date, 'isoformat') else log_date)
        if person:
            conditions.append("person = ?")
            params.append(person.upper())
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY date, person, meal_type, ingredient_name"
        rows = self.conn.execute(query, params).fetchall()
        return [
            {"date": r[0], "person": r[1], "meal_type": r[2], "ingredient_name": r[3], "quantity_g": r[4]}
            for r in rows
        ]

    def set_daily_goal(
        self,
        calories: float,
        protein_g: float,
        carbs_g: float,
        fat_g: float,
        plan_name: str = "Plan actual",
        log_date: date = None,
        person: str = 'ATM',
    ):
        if log_date is None:
            log_date = date.today()
        self.conn.execute(
            """INSERT OR REPLACE INTO daily_goals
               (date, person, calories_target, protein_target, carbs_target, fat_target, plan_name)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (log_date.isoformat(), person.upper(), calories, protein_g, carbs_g, fat_g, plan_name),
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

    def get_daily_summary(self, summary_date: date = None, person: str = 'ATM') -> dict:
        if summary_date is None:
            summary_date = date.today()
        person = person.upper()

        meals = self.conn.execute(
            """SELECT meal_type, name, calories, protein_g, carbs_g, fat_g
               FROM meals WHERE date = ? AND person = ? AND source = 'logged' ORDER BY id""",
            (summary_date.isoformat(), person),
        ).fetchall()

        goal = self.conn.execute(
            """SELECT calories_target, protein_target, carbs_target, fat_target
               FROM daily_goals WHERE date = ? AND person = ?""",
            (summary_date.isoformat(), person),
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

    def get_weekly_data(self, week_start: date, person: str = 'ATM') -> list:
        from datetime import timedelta
        dates = [(week_start + timedelta(days=i)).isoformat() for i in range(7)]
        placeholders = ",".join("?" * 7)
        rows = self.conn.execute(
            f"""SELECT date, SUM(calories), SUM(protein_g), SUM(carbs_g), SUM(fat_g)
                FROM meals WHERE date IN ({placeholders}) AND person = ? AND source = 'logged'
                GROUP BY date ORDER BY date""",
            [*dates, person.upper()],
        ).fetchall()
        return [
            {"date": r[0], "calories": r[1], "protein_g": r[2], "carbs_g": r[3], "fat_g": r[4]}
            for r in rows
        ]

    def log_rating(self, recipe: str, week: str, person: str, stars: int = None, tag: str = None):
        """Upsert a dish rating (one per recipe/week/person)."""
        self.conn.execute(
            """INSERT INTO dish_ratings (recipe, week, person, stars, tag)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(recipe, week, person) DO UPDATE SET
                   stars=excluded.stars, tag=excluded.tag,
                   logged_at=CURRENT_TIMESTAMP""",
            (recipe, week, person.upper(), stars, tag or ""),
        )
        self.conn.commit()

    def get_ratings(self, person: str = None, min_stars: int = None) -> list:
        """Return all dish ratings, optionally filtered."""
        query = "SELECT recipe, week, person, stars, tag FROM dish_ratings"
        params = []
        conditions = []
        if person:
            conditions.append("person = ?")
            params.append(person.upper())
        if min_stars is not None:
            conditions.append("stars >= ?")
            params.append(min_stars)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY week DESC, recipe"
        rows = self.conn.execute(query, params).fetchall()
        return [{"recipe": r[0], "week": r[1], "person": r[2], "stars": r[3], "tag": r[4]}
                for r in rows]

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
        # Union manual peso logs + body_composition records (Xiaomi/scale imports).
        # body_metrics wins on duplicate dates (it's a manual override).
        rows = self.conn.execute(
            """
            SELECT date, weight_kg, notes FROM body_metrics
             WHERE person = ? AND weight_kg IS NOT NULL
            UNION
            SELECT date, weight_kg, NULL FROM body_composition
             WHERE person = ? AND weight_kg IS NOT NULL
               AND date NOT IN (SELECT date FROM body_metrics WHERE person = ? AND weight_kg IS NOT NULL)
            ORDER BY date DESC LIMIT ?
            """,
            (person.upper(), person.upper(), person.upper(), limit),
        ).fetchall()
        return [{"date": r[0], "weight_kg": r[1], "notes": r[2]} for r in rows]

    def close(self):
        self.conn.close()
