"""Regras de agendamento que dependem do banco (fuso do servidor e reagendamento)."""

import datetime as dt

import discord

import config
from utils.database import Database
from utils.timeutils import compute_next_run, get_timezone


async def guild_timezone(db: Database, guild_id: int) -> dt.tzinfo:
    """Fuso configurado no servidor, ou o padrão do bot."""
    cfg = await db.get_guild_config(guild_id)
    return get_timezone(cfg['timezone']) or get_timezone(config.DEFAULT_TIMEZONE) or dt.timezone.utc


async def reschedule_guild(db: Database, guild_id: int, tz: dt.tzinfo) -> int:
    """Recalcula o próximo disparo dos agendamentos ativos (ex.: após trocar o fuso). Retorna quantos mudaram."""
    now = discord.utils.utcnow()
    count = 0
    for schedule in await db.list_schedules(guild_id):
        if schedule['next_run_at'] is None:
            continue
        next_run = compute_next_run(schedule, tz, now)
        await db.update_schedule_run(schedule['id'], int(next_run.timestamp()), schedule['status'])
        count += 1
    return count
