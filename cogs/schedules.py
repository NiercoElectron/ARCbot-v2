"""Mensagens agendadas: comandos /schedule e o loop que dispara os envios."""

import datetime as dt
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.error_handler import BaseModal
from utils.errors import UserFacingError
from utils.permissions import require_permissions
from utils.scheduling import guild_timezone
from utils.text import one_line, truncate
from utils.timeutils import at_local_time, next_daily_run, parse_date, parse_time

log = logging.getLogger(__name__)

MAX_ACTIVE_SCHEDULES = 25
# Atraso máximo tolerado: se o bot estava offline por mais que isso, o envio é considerado perdido.
GRACE_PERIOD = dt.timedelta(minutes=15)
# Mensagens agendadas são escritas por admins e podem anunciar com @everyone e cargos.
SCHEDULE_MENTIONS = discord.AllowedMentions(everyone=True, roles=True, users=True)

STATUS_LABELS = {
    'sent': '✅ Enviado',
    'missed': '⚠️ Perdido (bot offline no horário)',
    'failed': '❌ Falhou ao enviar',
}


class ScheduleMessageModal(BaseModal, title='Mensagem agendada'):
    message = discord.ui.TextInput(label='Mensagem', style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, bot: commands.Bot, channel: discord.abc.GuildChannel, time_str: str,
                 day: dt.date | None, tz: dt.tzinfo):
        super().__init__()
        self.bot = bot
        self.channel = channel
        self.time_str = time_str
        self.day = day
        self.tz = tz

    async def on_submit(self, interaction: discord.Interaction):
        now = discord.utils.utcnow()
        if self.day is None:
            run_at = next_daily_run(self.time_str, self.tz, now)
        else:
            run_at = at_local_time(self.day, self.time_str, self.tz)
            if run_at <= now:
                raise UserFacingError('Esse horário já passou. Rode `/schedule add` de novo.')
        if await self.bot.db.count_active_schedules(interaction.guild.id) >= MAX_ACTIVE_SCHEDULES:
            raise UserFacingError(f'Limite de {MAX_ACTIVE_SCHEDULES} agendamentos ativos atingido.')

        schedule_id = await self.bot.db.add_schedule(
            guild_id=interaction.guild.id,
            channel_id=self.channel.id,
            author_id=interaction.user.id,
            time=self.time_str,
            date=self.day.isoformat() if self.day else None,
            message=self.message.value,
            next_run_at=int(run_at.timestamp()),
        )
        recurrence = 'todo dia' if self.day is None else f'em {self.day:%d/%m/%Y}'
        await interaction.response.send_message(
            f'✅ Agendamento **#{schedule_id}** criado: {self.channel.mention} às `{self.time_str}` {recurrence}.\n'
            f'Próximo envio: {discord.utils.format_dt(run_at, "F")} ({discord.utils.format_dt(run_at, "R")})',
            ephemeral=True,
        )


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class Schedules(commands.GroupCog, group_name='schedule', group_description='Mensagens agendadas.'):
    """Agendamentos por servidor. Exige a permissão Gerenciar servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.dispatcher.start()

    async def cog_unload(self):
        self.dispatcher.cancel()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        require_permissions(interaction, manage_guild=True)
        return True

    # ── comandos ──────────────────────────────────────────────────────────────

    @app_commands.command(name='add', description='Agenda uma mensagem diária ou para uma data específica.')
    @app_commands.describe(
        canal='Canal onde a mensagem será enviada',
        horario='Horário no fuso do servidor, ex.: 09:00',
        data='dd/mm/aaaa para um envio único; deixe vazio para enviar todo dia',
    )
    async def add(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        horario: str,
        data: str | None = None,
    ):
        time_str = parse_time(horario)
        if time_str is None:
            raise UserFacingError('Horário inválido. Use o formato HH:MM (ex.: `09:00`).')

        tz = await guild_timezone(self.bot.db, interaction.guild.id)
        day = None
        if data:
            day = parse_date(data)
            if day is None:
                raise UserFacingError('Data inválida. Use o formato dd/mm/aaaa (ex.: `25/12/2026`).')
            if at_local_time(day, time_str, tz) <= discord.utils.utcnow():
                raise UserFacingError(f'Essa data/horário já passou (fuso do servidor: `{tz}`).')

        perms = canal.permissions_for(interaction.guild.me)
        if not (perms.view_channel and perms.send_messages):
            raise UserFacingError(f'Não tenho permissão para enviar mensagens em {canal.mention}.')
        if await self.bot.db.count_active_schedules(interaction.guild.id) >= MAX_ACTIVE_SCHEDULES:
            raise UserFacingError(f'Limite de {MAX_ACTIVE_SCHEDULES} agendamentos ativos atingido.')

        await interaction.response.send_modal(ScheduleMessageModal(self.bot, canal, time_str, day, tz))

    @app_commands.command(name='list', description='Lista os agendamentos do servidor.')
    async def list_schedules(self, interaction: discord.Interaction):
        schedules = await self.bot.db.list_schedules(interaction.guild.id)
        if not schedules:
            await interaction.response.send_message(
                'Nenhum agendamento. Use `/schedule add` para criar um.', ephemeral=True
            )
            return

        tz = await guild_timezone(self.bot.db, interaction.guild.id)
        embed = discord.Embed(title='Agendamentos do servidor', color=discord.Color.blurple())
        for s in schedules[:25]:
            if s['next_run_at'] is not None:
                recurrence = '🔁 Diário' if s['daily'] else f'📅 {dt.date.fromisoformat(s["date"]):%d/%m/%Y}'
                when = f'Próximo: <t:{s["next_run_at"]}:f> (<t:{s["next_run_at"]}:R>)'
            else:
                recurrence = f'📅 {dt.date.fromisoformat(s["date"]):%d/%m/%Y}'
                when = STATUS_LABELS.get(s['status'], s['status'])
            embed.add_field(
                name=f'#{s["id"]} · {s["time"]} · {recurrence}',
                value=f'<#{s["channel_id"]}> · {when}\n> {truncate(one_line(s["message"]), 150)}',
                inline=False,
            )
        footer = f'Fuso: {tz}'
        if len(schedules) > 25:
            footer += f' · mostrando 25 de {len(schedules)}'
        embed.set_footer(text=footer)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='remove', description='Remove um agendamento.')
    @app_commands.describe(agendamento='Agendamento a remover')
    async def remove(self, interaction: discord.Interaction, agendamento: int):
        if not await self.bot.db.delete_schedule(agendamento, interaction.guild.id):
            raise UserFacingError(f'Agendamento `#{agendamento}` não encontrado neste servidor.')
        await interaction.response.send_message(f'Agendamento **#{agendamento}** removido.', ephemeral=True)

    @remove.autocomplete('agendamento')
    async def schedule_autocomplete(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None or not interaction.permissions.manage_guild:
            return []
        query = current.lower().lstrip('#')
        choices = []
        for s in await self.bot.db.list_schedules(interaction.guild.id):
            label = truncate(f'#{s["id"]} · {s["time"]} · {one_line(s["message"])}', 100)
            if query in label.lower():
                choices.append(app_commands.Choice(name=label, value=s['id']))
        return choices[:25]

    # ── envio ─────────────────────────────────────────────────────────────────

    @tasks.loop(seconds=30)
    async def dispatcher(self):
        now = discord.utils.utcnow()
        try:
            due = await self.bot.db.get_due_schedules(int(now.timestamp()))
        except Exception:
            log.exception('Erro ao buscar agendamentos')
            return
        for schedule in due:
            try:
                await self._fire(schedule, now)
            except Exception:
                log.exception('Erro ao processar o agendamento #%s', schedule['id'])

    @dispatcher.before_loop
    async def before_dispatcher(self):
        await self.bot.wait_until_ready()

    async def _fire(self, schedule: dict, now: dt.datetime):
        lateness = now - dt.datetime.fromtimestamp(schedule['next_run_at'], dt.timezone.utc)
        on_time = lateness <= GRACE_PERIOD
        sent = on_time and await self._send(schedule)
        if not on_time:
            log.warning('Agendamento #%s perdido (atraso de %s)', schedule['id'], lateness)

        if schedule['daily']:
            tz = await guild_timezone(self.bot.db, schedule['guild_id'])
            next_run = next_daily_run(schedule['time'], tz, now)
            await self.bot.db.update_schedule_run(schedule['id'], int(next_run.timestamp()), 'pending')
        else:
            status = 'sent' if sent else ('failed' if on_time else 'missed')
            await self.bot.db.update_schedule_run(schedule['id'], None, status)

    async def _send(self, schedule: dict) -> bool:
        channel = self.bot.get_channel(schedule['channel_id'])
        try:
            if channel is None:
                channel = await self.bot.fetch_channel(schedule['channel_id'])
            await channel.send(schedule['message'], allowed_mentions=SCHEDULE_MENTIONS)
            return True
        except discord.HTTPException:
            log.warning('Falha ao enviar o agendamento #%s no canal %s', schedule['id'], schedule['channel_id'],
                        exc_info=True)
            return False


async def setup(bot: commands.Bot):
    await bot.add_cog(Schedules(bot))
