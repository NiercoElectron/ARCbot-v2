"""Comandos de moderação: cargos, ban/kick, castigo, avisos e limpeza de mensagens."""

import datetime as dt
import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.errors import UserFacingError
from utils.permissions import ensure_can_moderate, ensure_role_manageable, moderator_command
from utils.text import truncate
from utils.timeutils import format_duration, parse_duration

log = logging.getLogger(__name__)

DEFAULT_REASON = 'Sem motivo informado'
# Limite de timeout imposto pelo Discord.
MAX_TIMEOUT = dt.timedelta(days=28)
# Ao filtrar /purge por membro, quantas mensagens recentes são examinadas no máximo.
PURGE_SCAN_LIMIT = 500

BAN_DELETE_CHOICES = [
    app_commands.Choice(name='Não apagar', value=0),
    app_commands.Choice(name='Última hora', value=3600),
    app_commands.Choice(name='Últimas 24 horas', value=86400),
    app_commands.Choice(name='Últimos 7 dias', value=604800),
]


def audit_reason(interaction: discord.Interaction, reason: str) -> str:
    """Motivo registrado no log de auditoria, identificando o moderador (máx. 512 caracteres)."""
    return truncate(f'{interaction.user} ({interaction.user.id}): {reason}', 512)


class Moderation(commands.Cog):
    """Comandos de moderação. Cada comando exige do membro e do bot a permissão correspondente."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── promote / demote ──────────────────────────────────────────────────────

    async def _promote_role(self, interaction: discord.Interaction) -> discord.Role:
        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        if not cfg['promote_role_id']:
            raise UserFacingError('Nenhum cargo de promoção configurado. Use `/config promoterole` primeiro.')
        role = interaction.guild.get_role(cfg['promote_role_id'])
        if role is None:
            raise UserFacingError('O cargo de promoção configurado não existe mais. Use `/config promoterole`.')
        ensure_role_manageable(interaction.user, role)
        return role

    @app_commands.command(description='Dá o cargo de promoção a um membro.')
    @app_commands.describe(membro='Membro a promover')
    @moderator_command(manage_roles=True)
    async def promote(self, interaction: discord.Interaction, membro: discord.Member):
        role = await self._promote_role(interaction)
        if role in membro.roles:
            raise UserFacingError(f'{membro.mention} já tem o cargo {role.mention}.')
        await membro.add_roles(role, reason=audit_reason(interaction, 'Promoção'))
        await interaction.response.send_message(f'⬆️ {membro.mention} recebeu o cargo **{role.name}**!')

    @app_commands.command(description='Remove o cargo de promoção de um membro.')
    @app_commands.describe(membro='Membro a rebaixar')
    @moderator_command(manage_roles=True)
    async def demote(self, interaction: discord.Interaction, membro: discord.Member):
        role = await self._promote_role(interaction)
        if role not in membro.roles:
            raise UserFacingError(f'{membro.mention} não tem o cargo {role.mention}.')
        await membro.remove_roles(role, reason=audit_reason(interaction, 'Rebaixamento'))
        await interaction.response.send_message(f'⬇️ {membro.mention} perdeu o cargo **{role.name}**.')

    # ── ban / unban / softban / kick ──────────────────────────────────────────

    @app_commands.command(description='Bane um usuário do servidor (funciona com ID de quem não está no servidor).')
    @app_commands.describe(
        usuario='Membro ou ID do usuário',
        motivo='Motivo do banimento',
        apagar_mensagens='Quanto do histórico recente de mensagens apagar',
    )
    @app_commands.choices(apagar_mensagens=BAN_DELETE_CHOICES)
    @moderator_command(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        usuario: discord.User,
        motivo: str = DEFAULT_REASON,
        apagar_mensagens: app_commands.Choice[int] | None = None,
    ):
        if isinstance(usuario, discord.Member):
            ensure_can_moderate(interaction.user, usuario)
        delete_seconds = apagar_mensagens.value if apagar_mensagens else 0
        await interaction.guild.ban(
            usuario,
            reason=audit_reason(interaction, motivo),
            delete_message_seconds=delete_seconds,
        )
        await interaction.response.send_message(f'🔨 {usuario.mention} foi **banido**. Motivo: {motivo}')

    @app_commands.command(description='Remove o banimento de um usuário.')
    @app_commands.describe(usuario='ID do usuário banido', motivo='Motivo do desbanimento')
    @moderator_command(ban_members=True)
    async def unban(self, interaction: discord.Interaction, usuario: discord.User, motivo: str = DEFAULT_REASON):
        try:
            await interaction.guild.unban(usuario, reason=audit_reason(interaction, motivo))
        except discord.NotFound:
            raise UserFacingError(f'{usuario.mention} não está banido neste servidor.') from None
        await interaction.response.send_message(f'{usuario.mention} foi **desbanido**. Motivo: {motivo}')

    @app_commands.command(description='Bane e desbane na hora, apagando as mensagens dos últimos 7 dias.')
    @app_commands.describe(membro='Membro a softbanir', motivo='Motivo')
    @moderator_command(ban_members=True)
    async def softban(self, interaction: discord.Interaction, membro: discord.Member, motivo: str = DEFAULT_REASON):
        ensure_can_moderate(interaction.user, membro)
        await interaction.guild.ban(
            membro,
            reason=audit_reason(interaction, f'Softban: {motivo}'),
            delete_message_seconds=604800,
        )
        try:
            await interaction.guild.unban(membro, reason=audit_reason(interaction, 'Softban (desbanimento automático)'))
        except discord.HTTPException:
            log.exception('Softban: falha ao desbanir %s no servidor %s', membro.id, interaction.guild.id)
            raise UserFacingError(
                f'{membro.mention} foi banido, mas não consegui desbanir. Use `/unban` com o ID `{membro.id}`.'
            ) from None
        await interaction.response.send_message(
            f'{membro.mention} foi **softbanido** (mensagens recentes apagadas). Motivo: {motivo}'
        )

    @app_commands.command(description='Expulsa um membro do servidor.')
    @app_commands.describe(membro='Membro a expulsar', motivo='Motivo')
    @moderator_command(kick_members=True)
    async def kick(self, interaction: discord.Interaction, membro: discord.Member, motivo: str = DEFAULT_REASON):
        ensure_can_moderate(interaction.user, membro)
        await membro.kick(reason=audit_reason(interaction, motivo))
        await interaction.response.send_message(f'👢 {membro.mention} foi **expulso**. Motivo: {motivo}')

    # ── mute / unmute (timeout) ───────────────────────────────────────────────

    @app_commands.command(description='Castiga (timeout) um membro por um tempo.')
    @app_commands.describe(
        membro='Membro a castigar',
        duracao='Ex.: 10m, 2h, 1d, 1h30m (máximo 28d)',
        motivo='Motivo',
    )
    @moderator_command(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        duracao: str,
        motivo: str = DEFAULT_REASON,
    ):
        ensure_can_moderate(interaction.user, membro)
        if membro.guild_permissions.administrator:
            raise UserFacingError('O Discord não permite castigar administradores.')
        delta = parse_duration(duracao)
        if delta is None:
            raise UserFacingError('Duração inválida. Use algo como `10m`, `2h`, `1d` ou `1h30m`.')
        if delta > MAX_TIMEOUT:
            raise UserFacingError('A duração máxima de um castigo é 28 dias.')

        until = discord.utils.utcnow() + delta
        await membro.timeout(until, reason=audit_reason(interaction, motivo))
        await interaction.response.send_message(
            f'🔇 {membro.mention} foi **castigado** por `{format_duration(delta)}` '
            f'(até {discord.utils.format_dt(until, "f")}). Motivo: {motivo}'
        )

    @app_commands.command(description='Remove o castigo (timeout) de um membro.')
    @app_commands.describe(membro='Membro a liberar')
    @moderator_command(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, membro: discord.Member):
        if not membro.is_timed_out():
            raise UserFacingError(f'{membro.mention} não está castigado.')
        ensure_can_moderate(interaction.user, membro)
        await membro.timeout(None, reason=audit_reason(interaction, 'Castigo removido'))
        await interaction.response.send_message(f'🔊 Castigo de {membro.mention} removido.')

    # ── warn / warnings / clearwarns ──────────────────────────────────────────

    @app_commands.command(description='Registra um aviso para um membro e o notifica por DM.')
    @app_commands.describe(membro='Membro a advertir', motivo='Motivo do aviso')
    @moderator_command(moderate_members=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        motivo: app_commands.Range[str, 1, 500],
    ):
        ensure_can_moderate(interaction.user, membro)
        created_at = int(discord.utils.utcnow().timestamp())
        total = await self.bot.db.add_warning(interaction.guild.id, membro.id, interaction.user.id, motivo, created_at)

        dm_note = ''
        try:
            await membro.send(
                f'Você recebeu um aviso em **{interaction.guild.name}**.\n'
                f'Motivo: **{motivo}**\n'
                f'Total de avisos: **{total}**'
            )
        except discord.HTTPException:
            dm_note = ' *(não consegui avisar por DM)*'

        await interaction.response.send_message(
            f'⚠️ {membro.mention} recebeu um aviso. Motivo: **{motivo}** (total: {total}){dm_note}'
        )

    @app_commands.command(name='warnings', description='Lista os avisos de um usuário.')
    @app_commands.describe(usuario='Membro ou ID (funciona para quem já saiu do servidor)')
    @moderator_command(moderate_members=True)
    async def show_warnings(self, interaction: discord.Interaction, usuario: discord.User):
        warns = await self.bot.db.get_warnings(interaction.guild.id, usuario.id)
        if not warns:
            await interaction.response.send_message(f'{usuario.mention} não possui avisos.', ephemeral=True)
            return

        lines = []
        length = 0
        for index, warn in enumerate(warns, 1):
            line = (
                f'**#{index}** — {warn["reason"]} '
                f'*(por <@{warn["mod_id"]}> em <t:{warn["created_at"]}:d>)*'
            )
            if length + len(line) > 3900:
                lines.append(f'… e mais {len(warns) - index + 1} aviso(s).')
                break
            lines.append(line)
            length += len(line) + 1

        embed = discord.Embed(
            title=f'Avisos de {usuario.display_name}',
            description='\n'.join(lines),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f'Total: {len(warns)} aviso(s)')
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(description='Remove todos os avisos de um usuário.')
    @app_commands.describe(usuario='Membro ou ID')
    @moderator_command(moderate_members=True)
    async def clearwarns(self, interaction: discord.Interaction, usuario: discord.User):
        removed = await self.bot.db.clear_warnings(interaction.guild.id, usuario.id)
        if removed == 0:
            raise UserFacingError(f'{usuario.mention} não possui avisos para remover.')
        await interaction.response.send_message(f'✅ {removed} aviso(s) de {usuario.mention} removido(s).')

    # ── purge ─────────────────────────────────────────────────────────────────

    @app_commands.command(description='Apaga mensagens recentes do canal.')
    @app_commands.describe(
        quantidade='Quantas mensagens apagar (1–200)',
        membro='Apagar apenas mensagens deste usuário',
    )
    @moderator_command(manage_messages=True)
    @app_commands.checks.bot_has_permissions(read_message_history=True)
    async def purge(
        self,
        interaction: discord.Interaction,
        quantidade: app_commands.Range[int, 1, 200],
        membro: discord.User | None = None,
    ):
        channel = interaction.channel
        if not hasattr(channel, 'purge'):
            raise UserFacingError('Não consigo apagar mensagens neste tipo de canal.')

        await interaction.response.defer(ephemeral=True, thinking=True)
        reason = audit_reason(interaction, '/purge')
        if membro is None:
            deleted = await channel.purge(limit=quantidade, reason=reason)
        else:
            # Apaga até `quantidade` mensagens DO membro, examinando no máximo PURGE_SCAN_LIMIT mensagens.
            remaining = quantidade

            def check(message: discord.Message) -> bool:
                nonlocal remaining
                if remaining > 0 and message.author.id == membro.id:
                    remaining -= 1
                    return True
                return False

            deleted = await channel.purge(limit=PURGE_SCAN_LIMIT, check=check, reason=reason)

        await interaction.followup.send(f'🗑️ {len(deleted)} mensagem(ns) apagada(s).', ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
