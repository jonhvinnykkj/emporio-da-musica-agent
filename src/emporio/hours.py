"""Store opening hours. Campo Grande is UTC-4, one hour behind Brasília."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

STORE_TZ = ZoneInfo("America/Campo_Grande")
OPENING_HOURS = {weekday: (time(9), time(18)) for weekday in range(5)} | {5: (time(9), time(13))}
WEEKDAYS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)
# National holidays by (month, day). Good Friday moves with Easter and is computed below.
FIXED_HOLIDAYS = frozenset({(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)})


def store_now() -> datetime:
    return datetime.now(STORE_TZ).replace(tzinfo=None)


def easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous algorithm)."""
    century, rest = divmod(year, 100)
    leap_cycles, leap_rest = divmod(century, 4)
    moon_shift = (century + 8) // 25
    correction = (century - moon_shift + 1) // 3
    epact = (19 * (year % 19) + century - leap_cycles - correction + 15) % 30
    weeks, week_rest = divmod(rest, 4)
    weekday_offset = (32 + 2 * leap_rest + 2 * weeks - epact - week_rest) % 7
    shift = ((year % 19) + 11 * epact + 22 * weekday_offset) // 451
    month, day = divmod(epact + weekday_offset - 7 * shift + 114, 31)
    return date(year, month, day + 1)


def is_holiday(day: date) -> bool:
    return (day.month, day.day) in FIXED_HOLIDAYS or day == easter(day.year) - timedelta(days=2)


def hours_on(day: date) -> tuple[time, time] | None:
    return None if is_holiday(day) else OPENING_HOURS.get(day.weekday())


def next_opening(now: datetime) -> datetime:
    for offset in range(1, 15):
        day = now.date() + timedelta(days=offset)
        hours = hours_on(day)
        if hours:
            return datetime.combine(day, hours[0])
    raise RuntimeError("no opening within two weeks")


def skipped_holidays(now: datetime, opening: datetime) -> str:
    """Warn about working days lost to a holiday, which the model would otherwise read as open."""
    days = (now.date() + timedelta(days=offset) for offset in range((opening.date() - now.date()).days))
    closed = [day for day in days if is_holiday(day) and day.weekday() in OPENING_HOURS]
    return "".join(f" {WEEKDAYS[day.weekday()]}, {day:%d/%m} é feriado, a loja não abre." for day in closed)


def describe(now: datetime) -> str:
    """Line for the system prompt, so the agent knows the time and can state the return time."""
    stamp = f"{WEEKDAYS[now.weekday()]}, {now:%d/%m/%Y}, {now:%H:%M} (horário de Campo Grande)"
    today = hours_on(now.date())
    if today and today[0] <= now.time() < today[1]:
        return f"Agora é {stamp}. A loja está aberta até {today[1]:%H:%M}."
    if today and now.time() < today[0]:
        opening = datetime.combine(now.date(), today[0])
    else:
        opening = next_opening(now)
    weekday = WEEKDAYS[opening.weekday()]
    return (
        f"Agora é {stamp}. A loja está fechada.{skipped_holidays(now, opening)} "
        f"A equipe volta {weekday}, {opening:%d/%m} às {opening:%H:%M}."
    )
