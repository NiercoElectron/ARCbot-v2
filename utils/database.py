"""Acesso ao banco SQLite do bot.

Usa uma única conexão compartilhada e migrações versionadas: cada script de MIGRATIONS
é aplicado uma vez, em ordem, e `PRAGMA user_version` guarda o último aplicado.
Datas são guardadas como timestamps Unix (UTC) em colunas INTEGER.
"""

import logging
from pathlib import Path

import aiosqlite

log = logging.getLogger(__name__)

MIGRATIONS: tuple[str, ...] = (
    # 1 — esquema inicial
    '''
    CREATE TABLE guild_config (
        guild_id        INTEGER PRIMARY KEY,
        autorole_id     INTEGER,
        promote_role_id INTEGER,
        welcome_message TEXT,
        timezone        TEXT
    );

    CREATE TABLE warnings (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        mod_id     INTEGER NOT NULL,
        reason     TEXT    NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE INDEX idx_warnings_guild_user ON warnings (guild_id, user_id);

    -- time/date ficam no fuso do servidor; next_run_at é o próximo disparo em UTC
    -- (NULL quando um agendamento único já terminou).
    CREATE TABLE schedules (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id    INTEGER NOT NULL,
        channel_id  INTEGER NOT NULL,
        author_id   INTEGER NOT NULL,
        time        TEXT    NOT NULL,
        date        TEXT,
        daily       INTEGER NOT NULL,
        message     TEXT    NOT NULL,
        next_run_at INTEGER,
        status      TEXT    NOT NULL DEFAULT 'pending'
    );
    CREATE INDEX idx_schedules_guild ON schedules (guild_id);
    CREATE INDEX idx_schedules_next_run ON schedules (next_run_at);
    ''',
)

GUILD_CONFIG_FIELDS = ('autorole_id', 'promote_role_id', 'welcome_message', 'timezone')

# Status de um agendamento: pending (ativo), sent (único já enviado),
# missed (bot estava offline no horário) ou failed (erro ao enviar).
SCHEDULE_STATUSES = ('pending', 'sent', 'missed', 'failed')


class Database:
    """Wrapper assíncrono sobre o SQLite com as consultas usadas pelo bot."""

    def __init__(self, path: str | Path):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute('PRAGMA journal_mode = WAL')
        await self._migrate()

    async def close(self):
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError('Banco de dados não conectado.')
        return self._conn

    async def _migrate(self):
        cursor = await self.conn.execute('PRAGMA user_version')
        (version,) = await cursor.fetchone()
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            await self.conn.executescript(f'BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;')
            log.info('Migração %d aplicada', number)

    # ── guild_config ──────────────────────────────────────────────────────────

    async def get_guild_config(self, guild_id: int) -> dict:
        """Retorna a configuração do servidor (campos ausentes vêm como None)."""
        cursor = await self.conn.execute(
            f'SELECT {", ".join(GUILD_CONFIG_FIELDS)} FROM guild_config WHERE guild_id = ?',
            (guild_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else dict.fromkeys(GUILD_CONFIG_FIELDS)

    async def set_guild_config(self, guild_id: int, **fields):
        """Atualiza campos da configuração. Aceita apenas os nomes de GUILD_CONFIG_FIELDS."""
        unknown = set(fields) - set(GUILD_CONFIG_FIELDS)
        if unknown:
            raise ValueError(f'Campos de configuração desconhecidos: {sorted(unknown)}')
        if not fields:
            return
        columns = ', '.join(fields)
        placeholders = ', '.join('?' for _ in fields)
        updates = ', '.join(f'{column} = excluded.{column}' for column in fields)
        await self.conn.execute(
            f'INSERT INTO guild_config (guild_id, {columns}) VALUES (?, {placeholders}) '
            f'ON CONFLICT (guild_id) DO UPDATE SET {updates}',
            (guild_id, *fields.values()),
        )
        await self.conn.commit()

    # ── warnings ──────────────────────────────────────────────────────────────

    async def add_warning(self, guild_id: int, user_id: int, mod_id: int, reason: str, created_at: int) -> int:
        """Registra um aviso e retorna o total de avisos do usuário no servidor."""
        await self.conn.execute(
            'INSERT INTO warnings (guild_id, user_id, mod_id, reason, created_at) VALUES (?, ?, ?, ?, ?)',
            (guild_id, user_id, mod_id, reason, created_at),
        )
        await self.conn.commit()
        cursor = await self.conn.execute(
            'SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        )
        (total,) = await cursor.fetchone()
        return total

    async def get_warnings(self, guild_id: int, user_id: int) -> list[dict]:
        cursor = await self.conn.execute(
            'SELECT id, mod_id, reason, created_at FROM warnings '
            'WHERE guild_id = ? AND user_id = ? ORDER BY id',
            (guild_id, user_id),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def clear_warnings(self, guild_id: int, user_id: int) -> int:
        """Remove todos os avisos do usuário e retorna quantos foram removidos."""
        cursor = await self.conn.execute(
            'DELETE FROM warnings WHERE guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        )
        await self.conn.commit()
        return cursor.rowcount

    # ── schedules ─────────────────────────────────────────────────────────────

    async def add_schedule(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        time: str,
        date: str | None,
        message: str,
        next_run_at: int,
    ) -> int:
        """Cria um agendamento (diário quando `date` é None) e retorna o ID."""
        cursor = await self.conn.execute(
            'INSERT INTO schedules (guild_id, channel_id, author_id, time, date, daily, message, next_run_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (guild_id, channel_id, author_id, time, date, int(date is None), message, next_run_at),
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def count_active_schedules(self, guild_id: int) -> int:
        cursor = await self.conn.execute(
            'SELECT COUNT(*) FROM schedules WHERE guild_id = ? AND next_run_at IS NOT NULL',
            (guild_id,),
        )
        (total,) = await cursor.fetchone()
        return total

    async def list_schedules(self, guild_id: int) -> list[dict]:
        """Todos os agendamentos do servidor: ativos primeiro (por próximo disparo), depois os encerrados."""
        cursor = await self.conn.execute(
            'SELECT * FROM schedules WHERE guild_id = ? '
            'ORDER BY next_run_at IS NULL, next_run_at, id DESC',
            (guild_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def delete_schedule(self, schedule_id: int, guild_id: int) -> bool:
        """Remove um agendamento do servidor. Retorna True se ele existia."""
        cursor = await self.conn.execute(
            'DELETE FROM schedules WHERE id = ? AND guild_id = ?',
            (schedule_id, guild_id),
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def get_due_schedules(self, now_ts: int) -> list[dict]:
        """Agendamentos ativos cujo próximo disparo já chegou."""
        cursor = await self.conn.execute(
            'SELECT * FROM schedules WHERE next_run_at IS NOT NULL AND next_run_at <= ? ORDER BY next_run_at',
            (now_ts,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def update_schedule_run(self, schedule_id: int, next_run_at: int | None, status: str):
        """Define o próximo disparo (None encerra o agendamento) e o status."""
        if status not in SCHEDULE_STATUSES:
            raise ValueError(f'Status inválido: {status}')
        await self.conn.execute(
            'UPDATE schedules SET next_run_at = ?, status = ? WHERE id = ?',
            (next_run_at, status, schedule_id),
        )
        await self.conn.commit()
