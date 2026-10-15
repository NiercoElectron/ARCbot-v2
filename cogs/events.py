"""Listeners de eventos: entrada do bot em servidores, boas-vindas e autorole."""

import logging

import discord
from discord.ext import commands

from utils.permissions import missing_permissions, permission_label
from utils.text import render_welcome

log = logging.getLogger(__name__)


class Events(commands.Cog):
    """Automações disparadas por eventos do Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        log.info('Conectado como %s (%s) em %d servidores', self.bot.user, self.bot.user.id, len(self.bot.guilds))

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Avisa o dono do servidor se faltar alguma permissão necessária."""
        log.info('Entrei no servidor %s (%s)', guild.name, guild.id)
        missing = missing_permissions(guild.me.guild_permissions)
        if not missing:
            return

        message = (
            f'Olá! Acabei de entrar em **{guild.name}**, mas estou sem algumas permissões necessárias:\n\n'
            + '\n'.join(f'• {permission_label(p)}' for p in missing)
            + '\n\nAjuste as permissões do meu cargo. Use `/config status` para conferir depois.'
        )
        owner = guild.owner
        if owner is None:
            try:
                owner = await guild.fetch_member(guild.owner_id)
            except discord.HTTPException:
                owner = None
        if owner is not None:
            try:
                await owner.send(message)
                return
            except discord.HTTPException:
                pass

        # Sem DM: tenta o canal de sistema e depois o primeiro canal onde o bot pode falar.
        candidates = [guild.system_channel, *guild.text_channels]
        for channel in candidates:
            if channel is not None and channel.permissions_for(guild.me).send_messages:
                try:
                    await channel.send(message)
                    return
                except discord.HTTPException:
                    continue

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        log.info('Saí do servidor %s (%s)', guild.name, guild.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        cfg = await self.bot.db.get_guild_config(member.guild.id)

        if cfg['welcome_message']:
            try:
                await member.send(render_welcome(cfg['welcome_message'], member))
            except discord.HTTPException:
                log.debug('Não foi possível enviar boas-vindas por DM para %s', member.id)

        # Membros que ainda não aceitaram as regras (triagem) recebem o cargo em on_member_update.
        if not member.pending:
            await self._apply_autorole(member, cfg)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.pending and not after.pending and not after.bot:
            cfg = await self.bot.db.get_guild_config(after.guild.id)
            await self._apply_autorole(after, cfg)

    async def _apply_autorole(self, member: discord.Member, cfg: dict):
        if not cfg['autorole_id']:
            return
        guild = member.guild
        role = guild.get_role(cfg['autorole_id'])
        if role is None:
            log.warning('Autorole %s não existe mais no servidor %s', cfg['autorole_id'], guild.id)
            return
        if not guild.me.guild_permissions.manage_roles or not role.is_assignable():
            log.warning('Sem permissão para atribuir o autorole %s no servidor %s', role.id, guild.id)
            return
        try:
            await member.add_roles(role, reason='Autorole')
        except discord.HTTPException:
            log.warning('Falha ao atribuir autorole a %s no servidor %s', member.id, guild.id, exc_info=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
