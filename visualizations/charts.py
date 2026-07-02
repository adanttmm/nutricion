import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from datetime import date, timedelta


class NutritionCharts:
    COLORS = {
        "on_target": "#27AE60",
        "over": "#E74C3C",
        "under": "#3498DB",
        "target_line": "#7F8C8D",
        "protein": "#3498DB",
        "carbs": "#2ECC71",
        "fat": "#F39C12",
    }
    OUTPUT_DIR = "outputs/charts"

    def __init__(self):
        Path(self.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        plt.rcParams.update({
            "font.family": "DejaVu Sans",
            "figure.facecolor": "#FAFAFA",
            "axes.facecolor": "#FFFFFF",
            "axes.spines.top": False,
            "axes.spines.right": False,
        })

    def weekly_calories_bar(self, weekly_data: list, targets: dict, week_start: date) -> Path:
        days_es = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        dates = [(week_start + timedelta(days=i)).isoformat() for i in range(7)]
        data_map = {d["date"]: d.get("calories") or 0 for d in weekly_data}
        actuals = [data_map.get(d, 0) for d in dates]
        target = targets.get("calories", 2200)

        fig, ax = plt.subplots(figsize=(12, 6))
        bar_colors = [
            self.COLORS["on_target"] if 0.9 * target <= a <= 1.1 * target
            else self.COLORS["over"] if a > 1.1 * target
            else self.COLORS["under"] if a > 0
            else "#ECEFF1"
            for a in actuals
        ]
        bars = ax.bar(range(7), actuals, color=bar_colors, alpha=0.85,
                      edgecolor="white", linewidth=1.5)
        ax.axhline(target, color=self.COLORS["target_line"], linewidth=2,
                   linestyle="--", label=f"Meta: {target} kcal", alpha=0.8)
        ax.axhline(target * 1.1, color=self.COLORS["over"], linewidth=1,
                   linestyle=":", alpha=0.4)
        ax.axhline(target * 0.9, color=self.COLORS["on_target"], linewidth=1,
                   linestyle=":", alpha=0.4)

        for bar, val in zip(bars, actuals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 25,
                        f"{int(val)}", ha="center", va="bottom", fontsize=10, fontweight="bold")

        ax.set_xticks(range(7))
        ax.set_xticklabels(days_es, fontsize=12)
        ax.set_ylabel("Calorías (kcal)", fontsize=12)
        ax.set_title(f"Calorías Semanales — {week_start.strftime('%d/%m/%Y')}",
                     fontsize=14, fontweight="bold", pad=15)
        ax.legend(fontsize=11)
        ax.set_ylim(0, max(max(actuals, default=0), target) * 1.25 + 200)
        ax.grid(axis="y", alpha=0.3)

        legend_patches = [
            mpatches.Patch(color=self.COLORS["on_target"], label="En meta (±10%)"),
            mpatches.Patch(color=self.COLORS["over"], label="Por encima"),
            mpatches.Patch(color=self.COLORS["under"], label="Por debajo"),
        ]
        ax.legend(handles=legend_patches + [
            plt.Line2D([0], [0], color=self.COLORS["target_line"], linewidth=2,
                       linestyle="--", label=f"Meta: {target} kcal")
        ], fontsize=10, loc="upper right")

        plt.tight_layout()
        path = Path(self.OUTPUT_DIR) / f"calorias_{week_start.strftime('%Y-%m-%d')}.png"
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        return path

    def macro_donut(self, totals: dict, targets: dict, chart_date: date) -> Path:
        protein_cal = (totals.get("protein_g") or 0) * 4
        carbs_cal = (totals.get("carbs_g") or 0) * 4
        fat_cal = (totals.get("fat_g") or 0) * 9
        total_cal = protein_cal + carbs_cal + fat_cal

        if total_cal == 0:
            return None

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
        fig.suptitle(f"Distribución de Macros — {chart_date.strftime('%d/%m/%Y')}",
                     fontsize=13, fontweight="bold")

        sizes = [protein_cal, carbs_cal, fat_cal]
        labels = [
            f"Proteína\n{totals.get('protein_g', 0):.0f}g",
            f"Carbohidratos\n{totals.get('carbs_g', 0):.0f}g",
            f"Grasas\n{totals.get('fat_g', 0):.0f}g",
        ]
        colors = [self.COLORS["protein"], self.COLORS["carbs"], self.COLORS["fat"]]

        wedges, texts, autotexts = ax1.pie(
            sizes, labels=labels, colors=colors, autopct="%1.0f%%",
            pctdistance=0.75,
            wedgeprops={"width": 0.5, "edgecolor": "white", "linewidth": 2},
            startangle=90,
        )
        for at in autotexts:
            at.set_fontsize(11)
            at.set_fontweight("bold")
        ax1.text(0, 0, f"{int(total_cal)}\nkcal", ha="center", va="center",
                 fontsize=14, fontweight="bold", color="#2C3E50")
        ax1.set_title("Real", fontsize=12)

        macro_labels = ["Proteína (g)", "Carbos (g)", "Grasas (g)"]
        actual_vals = [totals.get("protein_g") or 0, totals.get("carbs_g") or 0, totals.get("fat_g") or 0]
        target_vals = [targets.get("protein_g") or 0, targets.get("carbs_g") or 0, targets.get("fat_g") or 0]
        x = range(3)
        w = 0.35
        ax2.bar([i - w / 2 for i in x], actual_vals, w, label="Real", color=colors, alpha=0.85)
        ax2.bar([i + w / 2 for i in x], target_vals, w, label="Meta",
                color=colors, alpha=0.35, edgecolor=colors, linewidth=1.5)
        ax2.set_xticks(list(x))
        ax2.set_xticklabels(macro_labels, fontsize=10)
        ax2.set_ylabel("Gramos", fontsize=11)
        ax2.set_title("Real vs Meta", fontsize=12)
        ax2.legend(fontsize=11)
        ax2.grid(axis="y", alpha=0.3)

        plt.tight_layout()
        path = Path(self.OUTPUT_DIR) / f"macros_{chart_date.strftime('%Y-%m-%d')}.png"
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        return path

    def weight_trend(self, weight_history: list) -> Path:
        if len(weight_history) < 2:
            return None

        history = sorted(weight_history, key=lambda x: x["date"])
        dates = [d["date"] for d in history]
        weights = [d["weight_kg"] for d in history]

        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(dates, weights, marker="o", linewidth=2, markersize=7,
                color=self.COLORS["protein"], markerfacecolor="white", markeredgewidth=2)

        for i, (d, w) in enumerate(zip(dates, weights)):
            ax.annotate(f"{w:.1f}", (d, w), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=9)

        ax.set_xlabel("Fecha", fontsize=11)
        ax.set_ylabel("Peso (kg)", fontsize=11)
        ax.set_title("Progreso de Peso", fontsize=13, fontweight="bold", pad=15)
        ax.tick_params(axis="x", rotation=45)
        ax.grid(axis="y", alpha=0.3)

        min_w, max_w = min(weights), max(weights)
        margin = max(0.5, (max_w - min_w) * 0.2)
        ax.set_ylim(min_w - margin, max_w + margin)

        plt.tight_layout()
        path = Path(self.OUTPUT_DIR) / f"peso_{date.today().strftime('%Y-%m-%d')}.png"
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        return path
