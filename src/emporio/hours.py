"""Store opening hours. Campo Grande is UTC-4, one hour behind Brasília."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import holidays

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
_HOLIDAYS = holidays.Brazil(subdiv="MS")


def store_now() -> datetime:
    return datetime.now(STORE_TZ).replace(tzinfo=None)


def hours_on(day: date) -> tuple[time, time] | None:
    return None if day in _HOLIDAYS else OPENING_HOURS.get(day.weekday())


def next_opening(now: datetime) -> datetime:
    for offset in range(1, 15):
        day = now.date() + timedelta(days=offset)
        hours = hours_on(day)
        if hours:
            return datetime.combine(day, hours[0])
    raise RuntimeError("no opening within two weeks")


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
        f"Agora é {stamp}. A loja está fechada. A equipe volta {weekday}, {opening:%d/%m} às {opening:%H:%M}."
    )
