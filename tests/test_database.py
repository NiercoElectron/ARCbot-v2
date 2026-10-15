import pytest

from utils.database import MIGRATIONS, Database


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / 'test.db')
    await database.connect()
    yield database
    await database.close()


async def test_migrations_run_once(tmp_path):
    path = tmp_path / 'migrate.db'
    for _ in range(2):  # reconectar não pode reaplicar as migrações
        database = Database(path)
        await database.connect()
        cursor = await database.conn.execute('PRAGMA user_version')
        (version,) = await cursor.fetchone()
        assert version == len(MIGRATIONS)
        await database.close()


async def test_guild_config_defaults_and_partial_updates(db):
    assert await db.get_guild_config(1) == {
        'autorole_id': None, 'promote_role_id': None, 'welcome_message': None, 'timezone': None,
    }
    await db.set_guild_config(1, autorole_id=10)
    await db.set_guild_config(1, welcome_message='Oi {member}', timezone='America/Sao_Paulo')
    cfg = await db.get_guild_config(1)
    assert cfg['autorole_id'] == 10  # não foi apagado pela segunda atualização
    assert cfg['welcome_message'] == 'Oi {member}'
    assert cfg['timezone'] == 'America/Sao_Paulo'

    await db.set_guild_config(1, autorole_id=None)
    assert (await db.get_guild_config(1))['autorole_id'] is None


async def test_guild_config_rejects_unknown_fields(db):
    with pytest.raises(ValueError):
        await db.set_guild_config(1, prefix='!')


async def test_warnings_are_scoped_per_guild(db):
    assert await db.add_warning(1, 100, 900, 'spam', 1_700_000_000) == 1
    assert await db.add_warning(1, 100, 900, 'flood', 1_700_000_100) == 2
    assert await db.add_warning(2, 100, 900, 'outro servidor', 1_700_000_200) == 1

    warns = await db.get_warnings(1, 100)
    assert [w['reason'] for w in warns] == ['spam', 'flood']

    assert await db.clear_warnings(1, 100) == 2
    assert await db.get_warnings(1, 100) == []
    assert len(await db.get_warnings(2, 100)) == 1


async def test_schedule_lifecycle(db):
    daily_id = await db.add_schedule(
        guild_id=1, channel_id=5, author_id=9, time='09:00', date=None, message='bom dia', next_run_at=1000,
    )
    once_id = await db.add_schedule(
        guild_id=1, channel_id=5, author_id=9, time='10:00', date='2026-12-25', message='feliz natal',
        next_run_at=5000,
    )
    assert await db.count_active_schedules(1) == 2

    due = await db.get_due_schedules(2000)
    assert [s['id'] for s in due] == [daily_id]
    assert due[0]['daily'] == 1

    await db.update_schedule_run(once_id, None, 'sent')
    assert await db.count_active_schedules(1) == 1
    assert await db.get_due_schedules(10_000) == [await _schedule(db, daily_id)]

    listed = await db.list_schedules(1)
    assert [s['id'] for s in listed] == [daily_id, once_id]  # ativos antes dos encerrados

    assert await db.delete_schedule(daily_id, guild_id=2) is False  # outro servidor não pode remover
    assert await db.delete_schedule(daily_id, guild_id=1) is True


async def test_update_schedule_rejects_unknown_status(db):
    with pytest.raises(ValueError):
        await db.update_schedule_run(1, None, 'whatever')


async def _schedule(db, schedule_id):
    return next(s for s in await db.list_schedules(1) if s['id'] == schedule_id)
