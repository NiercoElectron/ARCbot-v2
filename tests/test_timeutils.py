import datetime as dt
from zoneinfo import ZoneInfo

from utils.timeutils import (
    at_local_time,
    compute_next_run,
    format_duration,
    get_timezone,
    next_daily_run,
    parse_date,
    parse_duration,
    parse_time,
)

SAO_PAULO = ZoneInfo('America/Sao_Paulo')  # UTC-3, sem horário de verão
UTC = dt.timezone.utc


def test_parse_duration_simple_and_combined():
    assert parse_duration('10s') == dt.timedelta(seconds=10)
    assert parse_duration('5m') == dt.timedelta(minutes=5)
    assert parse_duration('2H') == dt.timedelta(hours=2)
    assert parse_duration('1h30m') == dt.timedelta(hours=1, minutes=30)
    assert parse_duration('1d 12h') == dt.timedelta(days=1, hours=12)


def test_parse_duration_invalid():
    for value in ('', '10', 'm', '10x', '-5m', '0m', '1.5h', 'abc'):
        assert parse_duration(value) is None, value
    assert parse_duration('99999999999999d') is None  # estouro de timedelta


def test_format_duration():
    assert format_duration(dt.timedelta(days=1, hours=2, minutes=30)) == '1d 2h 30m'
    assert format_duration(dt.timedelta(seconds=45)) == '45s'


def test_parse_time_normalizes():
    assert parse_time('9:00') == '09:00'
    assert parse_time('09:05') == '09:05'
    assert parse_time('23h59') == '23:59'
    assert parse_time(' 7:30 ') == '07:30'


def test_parse_time_invalid():
    for value in ('24:00', '12:60', '9', '9:5', 'nove'):
        assert parse_time(value) is None, value


def test_parse_date():
    assert parse_date('25/12/2026') == dt.date(2026, 12, 25)
    assert parse_date('31/02/2026') is None
    assert parse_date('2026-12-25') is None


def test_get_timezone():
    assert get_timezone('America/Sao_Paulo') is not None
    assert get_timezone('Marte/Base') is None
    assert get_timezone('') is None
    assert get_timezone(None) is None


def test_at_local_time_converts_to_utc():
    assert at_local_time(dt.date(2026, 10, 14), '09:00', SAO_PAULO) == dt.datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def test_next_daily_run_today_and_tomorrow():
    before = dt.datetime(2026, 10, 14, 11, 0, tzinfo=UTC)  # 08:00 em São Paulo
    assert next_daily_run('09:00', SAO_PAULO, before) == dt.datetime(2026, 10, 14, 12, 0, tzinfo=UTC)

    exactly = dt.datetime(2026, 10, 14, 12, 0, tzinfo=UTC)  # o horário em si já não conta
    assert next_daily_run('09:00', SAO_PAULO, exactly) == dt.datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def test_next_daily_run_crosses_utc_midnight():
    # 22:30 em São Paulo = 01:30 UTC do dia seguinte
    now = dt.datetime(2026, 10, 14, 20, 0, tzinfo=UTC)  # 17:00 local
    assert next_daily_run('22:30', SAO_PAULO, now) == dt.datetime(2026, 10, 15, 1, 30, tzinfo=UTC)


def test_compute_next_run_once():
    schedule = {'daily': 0, 'date': '2026-12-25', 'time': '09:00'}
    now = dt.datetime(2026, 10, 14, tzinfo=UTC)
    assert compute_next_run(schedule, SAO_PAULO, now) == dt.datetime(2026, 12, 25, 12, 0, tzinfo=UTC)
