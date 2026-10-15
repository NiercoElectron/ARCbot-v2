"""Conversão e validação de durações, horários, datas e fusos."""

import datetime as dt
import functools
import re
import zoneinfo

_DURATION_RE = re.compile(r'(?:\d+[smhd])+')
_DURATION_PART_RE = re.compile(r'(\d+)([smhd])')
_UNIT_SECONDS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
# Aceita 9:00, 09:00 e 9h00.
_TIME_RE = re.compile(r'([01]?\d|2[0-3])[:h]([0-5]\d)')


def parse_duration(value: str) -> dt.timedelta | None:
    """Converte '10m', '2h', '1h30m' ou '1d 12h' em timedelta. Retorna None se inválido ou zero."""
    text = value.lower().replace(' ', '')
    if not _DURATION_RE.fullmatch(text):
        return None
    seconds = sum(int(amount) * _UNIT_SECONDS[unit] for amount, unit in _DURATION_PART_RE.findall(text))
    if seconds <= 0:
        return None
    try:
        return dt.timedelta(seconds=seconds)
    except OverflowError:
        return None


def format_duration(delta: dt.timedelta) -> str:
    """Formata um timedelta como '1d 2h 30m'."""
    total = int(delta.total_seconds())
    parts = []
    for unit, size in (('d', 86400), ('h', 3600), ('m', 60), ('s', 1)):
        amount, total = divmod(total, size)
        if amount:
            parts.append(f'{amount}{unit}')
    return ' '.join(parts) or '0s'


def parse_time(value: str) -> str | None:
    """Valida um horário e o normaliza para HH:MM (ex.: '9:00' → '09:00')."""
    match = _TIME_RE.fullmatch(value.strip().lower())
    if not match:
        return None
    return f'{int(match.group(1)):02d}:{match.group(2)}'


def parse_date(value: str) -> dt.date | None:
    """Converte 'dd/mm/aaaa' em date. Retorna None se inválido."""
    try:
        return dt.datetime.strptime(value.strip(), '%d/%m/%Y').date()
    except ValueError:
        return None


def get_timezone(name: str | None) -> zoneinfo.ZoneInfo | None:
    """Retorna o fuso pelo nome IANA (ex.: 'America/Sao_Paulo') ou None se não existir."""
    if not name:
        return None
    try:
        return zoneinfo.ZoneInfo(name)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return None


@functools.cache
def all_timezones() -> tuple[str, ...]:
    """Lista ordenada de todos os fusos IANA disponíveis."""
    return tuple(sorted(zoneinfo.available_timezones()))


def at_local_time(day: dt.date, time_str: str, tz: dt.tzinfo) -> dt.datetime:
    """Converte uma data + 'HH:MM' no fuso `tz` para um datetime em UTC."""
    hour, minute = map(int, time_str.split(':'))
    local = dt.datetime.combine(day, dt.time(hour, minute), tzinfo=tz)
    return local.astimezone(dt.timezone.utc)


def next_daily_run(time_str: str, tz: dt.tzinfo, now: dt.datetime) -> dt.datetime:
    """Próxima ocorrência estritamente futura de 'HH:MM' no fuso `tz`, em UTC."""
    today = now.astimezone(tz).date()
    candidate = at_local_time(today, time_str, tz)
    if candidate <= now:
        candidate = at_local_time(today + dt.timedelta(days=1), time_str, tz)
    return candidate


def compute_next_run(schedule: dict, tz: dt.tzinfo, now: dt.datetime) -> dt.datetime:
    """Próximo disparo de um agendamento (linha da tabela `schedules`), em UTC."""
    if schedule['daily']:
        return next_daily_run(schedule['time'], tz, now)
    return at_local_time(dt.date.fromisoformat(schedule['date']), schedule['time'], tz)
