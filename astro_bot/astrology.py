from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Tuple
from skyfield.api import load, N, W, wgs84
from skyfield.api import Loader
from skyfield.timelib import Time
from dateutil import tz
import os
import random


@dataclass
class PlanetPosition:
    name: str
    ecliptic_lon_deg: float


class AstrologyEngine:
    def __init__(self):
        # Cache ephemerides
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(data_dir, exist_ok=True)
        self.loader: Loader = load
        self.ts = self.loader.timescale()
        # Use built-in DE421 for compactness
        self.eph = self.loader("de421.bsp")

    def _tz_aware_time(self, birth_date: str, birth_time: str, timezone: str) -> Time:
        day, month, year = map(int, birth_date.split("."))
        hour, minute = map(int, birth_time.split(":"))
        tz_info = tz.gettz(timezone)
        dt = datetime(year, month, day, hour, minute, tzinfo=tz_info)
        return self.ts.from_datetime(dt)

    def planets_longitudes(self, t: Time) -> Dict[str, float]:
        planets = {
            "Sun": self.eph["sun"],
            "Moon": self.eph["moon"],
            "Mercury": self.eph["mercury"],
            "Venus": self.eph["venus"],
            "Mars": self.eph["mars"],
            "Jupiter": self.eph["jupiter barycenter"],
            "Saturn": self.eph["saturn barycenter"],
        }
        earth = self.eph["earth"]
        result: Dict[str, float] = {}
        for name, planet in planets.items():
            astrometric = earth.at(t).observe(planet)
            ecliptic_lon, lat, distance = astrometric.ecliptic_latlon()
            result[name] = float(ecliptic_lon.degrees % 360.0)
        return result

    def natal_chart(self, birth_date: str, birth_time: str, timezone: str) -> Dict[str, float]:
        t = self._tz_aware_time(birth_date, birth_time, timezone)
        return self.planets_longitudes(t)

    def transit_chart(self, timezone: str) -> Dict[str, float]:
        now = datetime.now(tz.gettz(timezone))
        t = self.ts.from_datetime(now)
        return self.planets_longitudes(t)

    def compute_aspects(self, natal: Dict[str, float], transit: Dict[str, float]) -> List[Tuple[str, str, str]]:
        aspects = []
        major_aspects = {
            "Conjunction": 0,
            "Sextile": 60,
            "Square": 90,
            "Trine": 120,
            "Opposition": 180,
        }
        orb = 6.0  # degrees
        for t_name, t_lon in transit.items():
            for n_name, n_lon in natal.items():
                delta = abs((t_lon - n_lon + 180) % 360 - 180)
                for a_name, a_lon in major_aspects.items():
                    if abs(delta - a_lon) <= orb:
                        aspects.append((t_name, n_name, a_name))
                        break
        return aspects

    def render_daily_message(self, user_name: str, aspects: List[Tuple[str, str, str]], quotes: List[str]) -> str:
        if aspects:
            lines = [f"Доброе утро, {user_name}!", ""]
            lines.append("Тема дня: гармония и принятие. Прислушайся к себе.")
            # Group some motifs by planets
            motifs = []
            used = set()
            for t_planet, n_planet, aspect in aspects[:5]:
                key = (t_planet, aspect)
                if key in used:
                    continue
                used.add(key)
                hint = self._aspect_hint(t_planet, aspect)
                motifs.append(f"{t_planet} {self._aspect_verb(aspect)} твоему {n_planet}. {hint}")
            if motifs:
                lines.append("Энергии дня:")
                for m in motifs:
                    lines.append(f"• {m}")
            lines.append("")
            lines.append("Действуй:")
            actions = self._actions_from_aspects(aspects)
            for a in actions[:2]:
                lines.append(f"• {a}")
            lines.append("")
            lines.append("Категорически:")
            cant = list(dict.fromkeys(self._avoid_from_aspects(aspects)))[:2]
            for c in cant:
                lines.append(f"• {c}")
            lines.append("")
            lines.append("Утренний ритуал (5 минут):")
            lines.append("Посмотри на небо и вспомни три своих мечты.")
            lines.append("")
            lines.append("Девиз дня:")
            quote = random.choice(quotes) if quotes else "Осознанность создаёт свободу."
            lines.append(quote)
            return "\n".join(lines)
        else:
            quote = random.choice(quotes) if quotes else "Осознанность создаёт свободу."
            return f"Доброе утро, {user_name}!\nСегодня спокойный день. Будь мягок к себе.\n\n{quote}"

    def _aspect_hint(self, planet: str, aspect: str) -> str:
        mapping = {
            ("Moon", "Square"): "Эмоции могут прыгать в разные стороны — дыши глубже.",
            ("Mars", "Trine"): "Легче сказать смелое ‘нет’.",
            ("Venus", "Sextile"): "Муза рядом: бери кисть, слова или музыку.",
            ("Saturn", "Opposition"): "Не перегружай себя обязанностями — структура, а не строгость.",
            ("Jupiter", "Trine"): "Оптимизм помогает увидеть возможности.",
        }
        return mapping.get((planet, aspect), "Заметь, где тело подсказывает направление.")

    def _aspect_verb(self, aspect: str) -> str:
        return {
            "Conjunction": "соединяется с",
            "Sextile": "делает секстиль к",
            "Square": "квадрат к",
            "Trine": "трин к",
            "Opposition": "в оппозиции к",
        }.get(aspect, "в аспекте к")

    def _actions_from_aspects(self, aspects: List[Tuple[str, str, str]]) -> List[str]:
        actions = [
            "Обрати внимание на свои истинные желания",
            "Проведи немного времени наедине с собой",
            "Запиши три шага к мечте",
            "Сделай одно доброе дело для себя",
        ]
        return actions

    def _avoid_from_aspects(self, aspects: List[Tuple[str, str, str]]) -> List[str]:
        avoid = [
            "Не игнорируй тревогу",
            "Не перегружай календарь",
            "Не сравнивай себя с другими",
        ]
        # Deduplicate
        return list(dict.fromkeys(avoid))


def load_quotes(quotes_dir: str) -> List[str]:
    result: List[str] = []
    for fname in ("secret.txt", "happy_pocket.txt"):
        path = os.path.join(quotes_dir, fname)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        result.append(line)
    # Fallback defaults if files empty
    if not result:
        result = [
            "Мы — магнит. Мы притягиваем то, чем являемся.",
            "Благодарность ускоряет поток изобилия.",
            "Я позволяю себе мечтать — и делаю один шаг сегодня.",
        ]
    return result