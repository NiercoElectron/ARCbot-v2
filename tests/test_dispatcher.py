import datetime as dt
from types import SimpleNamespace

import pytest

from cogs.schedules import Schedules
from utils.database import Database

NOW = dt.datetime(2026, 10, 14, 12, 0, tzinfo=dt.timezone.utc)  # 09:00 em São Paulo


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content, **kwargs):
        self.sent.append(content)


@pytest.fixture
async def setup(tmp_path):
    db = Database(tmp_path / 'dispatch.db')
    await db.connect()
    channel = FakeChannel()
    bot = SimpleNamespace(db=db, get_channel=lambda channel_id: channel if channel_id == 5 else None)
    cog = Schedules(bot)
    yield db, channel, cog
    await db.close()


async def _add(db, *, date, next_run_at, channel_id=5):
    return await db.add_schedule(
        guild_id=1, channel_id=channel_id, author_id=9, time='09:00', date=date, message='oi',
        next_run_at=int(next_run_at.timestamp()),
    )


async def _get(db, schedule_id):
    return next(s for s in await db.list_schedules(1) if s['id'] == schedule_id)


async def test_daily_schedule_is_sent_and_moved_to_tomorrow(setup):
    db, channel, cog = setup
    schedule_id = await _add(db, date=None, next_run_at=NOW)

    await cog._fire(await _get(db, schedule_id), NOW + dt.timedelta(seconds=20))

    assert channel.sent == ['oi']
    schedule = await _get(db, schedule_id)
    assert schedule['next_run_at'] == int((NOW + dt.timedelta(days=1)).timestamp())
    assert schedule['status'] == 'pending'


async def test_once_schedule_is_sent_and_finished(setup):
    db, channel, cog = setup
    schedule_id = await _add(db, date='2026-10-14', next_run_at=NOW)

    await cog._fire(await _get(db, schedule_id), NOW + dt.timedelta(minutes=5))  # dentro da tolerância

    assert channel.sent == ['oi']
    schedule = await _get(db, schedule_id)
    assert schedule['next_run_at'] is None
    assert schedule['status'] == 'sent'


async def test_overdue_schedules_are_skipped(setup):
    db, channel, cog = setup
    once_id = await _add(db, date='2026-10-14', next_run_at=NOW)
    daily_id = await _add(db, date=None, next_run_at=NOW)
    late = NOW + dt.timedelta(hours=3)  # bot ficou offline

    await cog._fire(await _get(db, once_id), late)
    await cog._fire(await _get(db, daily_id), late)

    assert channel.sent == []
    assert (await _get(db, once_id))['status'] == 'missed'
    daily = await _get(db, daily_id)
    assert daily['next_run_at'] == int((NOW + dt.timedelta(days=1)).timestamp())


async def test_missing_channel_marks_once_schedule_as_failed(setup, monkeypatch):
    db, channel, cog = setup
    schedule_id = await _add(db, date='2026-10-14', next_run_at=NOW, channel_id=404)

    async def fake_send(schedule):
        return False
    monkeypatch.setattr(cog, '_send', fake_send)

    await cog._fire(await _get(db, schedule_id), NOW)

    assert (await _get(db, schedule_id))['status'] == 'failed'
