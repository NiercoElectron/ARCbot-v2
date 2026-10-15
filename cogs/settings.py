"""Comandos /config: autorole, boas-vindas, cargo de promoção, fuso horário e status."""

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.error_handler import BaseModal
from utils.errors import UserFacingError
from utils.permissions import (
    REQUIRED_PERMISSIONS,
    ensure_role_manageable,
    missing_permissions,
    permission_label,
    require_permissions,
)
from utils.scheduling import guild_timezone, reschedule_guild
from utils.text import render_welcome, truncate
from utils.timeutils import all_timezones, get_timezone

class WelcomeModal(BaseModal, title='Mensagem de boas-vindas'):
    message = discord.ui.TextInput(
        label='Mensagem ({member}, {mention}, {server})',
        style=discord.TextStyle.paragraph,
        placeholder='Ex.: Olá {mention}, bem-vindo(a) ao {server}! Deixe vazio para desativar.',
        required=False,
        max_length=1500,
    )

    def __init__(self, bot: commands.Bot, current: str | None):
        super().__init__()
        self.bot = bot
        self.message.default = current

    async def on_submit(self, interaction: discord.Interaction):
        text = self.message.value.strip()
        await self.bot.db.set_guild_config(interaction.guild.id, welcome_message=text or None)
        if not text:
            await interaction.response.send_message('Mensagem de boas-vindas **desativada**.', ephemeral=True)
            return
        preview = render_welcome(text, interaction.user)
        await interaction.response.send_message(
            f'Mensagem de boas-vindas salva! Novos membros receberão por DM:\n>>> {preview}',
            ephemeral=True,
        )


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class Settings(commands.GroupCog, group_name='config', group_description='Configurações do bot neste servidor.'):
    """Configuração por servidor. Exige a permissão Gerenciar servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        require_permissions(interaction, manage_guild=True)
        return True

    @app_commands.command(name='autorole', description='Define o cargo dado a novos membros (vazio = desativar).')
    @app_commands.describe(cargo='Cargo a atribuir; deixe vazio para desativar')
    async def autorole(self, interaction: discord.Interaction, cargo: discord.Role | None = None):
        if cargo is None:
            await self.bot.db.set_guild_config(interaction.guild.id, autorole_id=None)
            await interaction.response.send_message('Autorole **desativado**.', ephemeral=True)
            return
        ensure_role_manageable(interaction.user, cargo)
        await self.bot.db.set_guild_config(interaction.guild.id, autorole_id=cargo.id)
        await interaction.response.send_message(
            f'Autorole definido: novos membros receberão {cargo.mention}.', ephemeral=True
        )

    @app_commands.command(name='promoterole', description='Define o cargo usado por /promote e /demote (vazio = remover).')
    @app_commands.describe(cargo='Cargo de promoção; deixe vazio para remover')
    async def promoterole(self, interaction: discord.Interaction, cargo: discord.Role | None = None):
        if cargo is None:
            await self.bot.db.set_guild_config(interaction.guild.id, promote_role_id=None)
            await interaction.response.send_message('Cargo de promoção **removido**.', ephemeral=True)
            return
        ensure_role_manageable(interaction.user, cargo)
        await self.bot.db.set_guild_config(interaction.guild.id, promote_role_id=cargo.id)
        await interaction.response.send_message(f'Cargo de promoção definido: {cargo.mention}.', ephemeral=True)

    @app_commands.command(name='welcome', description='Edita a mensagem de boas-vindas enviada por DM a novos membros.')
    async def welcome(self, interaction: discord.Interaction):
        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        await interaction.response.send_modal(WelcomeModal(self.bot, cfg['welcome_message']))

    @app_commands.command(name='timezone', description='Define o fuso horário usado nos agendamentos.')
    @app_commands.describe(fuso='Fuso IANA, ex.: America/Sao_Paulo')
    async def timezone(self, interaction: discord.Interaction, fuso: str):
        tz = get_timezone(fuso)
        if tz is None:
            raise UserFacingError(f'Fuso `{fuso}` não encontrado. Escolha uma das opções sugeridas.')
        await self.bot.db.set_guild_config(interaction.guild.id, timezone=fuso)
        updated = await reschedule_guild(self.bot.db, interaction.guild.id, tz)
        note = f' {updated} agendamento(s) ativo(s) recalculado(s).' if updated else ''
        await interaction.response.send_message(f'Fuso horário definido: `{fuso}`.{note}', ephemeral=True)

    @timezone.autocomplete('fuso')
    async def timezone_autocomplete(self, interaction: discord.Interaction, current: str):
        query = current.lower().replace(' ', '_')
        matches = [name for name in all_timezones() if query in name.lower()]
        return [app_commands.Choice(name=name, value=name) for name in matches[:25]]

    @app_commands.command(name='show', description='Mostra a configuração atual do bot neste servidor.')
    async def show(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = await self.bot.db.get_guild_config(guild.id)
        autorole = guild.get_role(cfg['autorole_id']) if cfg['autorole_id'] else None
        promote_role = guild.get_role(cfg['promote_role_id']) if cfg['promote_role_id'] else None
        tz = await guild_timezone(self.bot.db, guild.id)
        active_schedules = await self.bot.db.count_active_schedules(guild.id)

        embed = discord.Embed(title=f'⚙️ Configuração — {guild.name}', color=discord.Color.blurple())
        embed.add_field(name='Autorole', value=autorole.mention if autorole else '*(desativado)*', inline=True)
        embed.add_field(
            name='Cargo de promoção',
            value=promote_role.mention if promote_role else '*(não definido)*',
            inline=True,
        )
        tz_note = '' if cfg['timezone'] else ' *(padrão)*'
        embed.add_field(name='Fuso horário', value=f'`{tz}`{tz_note}', inline=True)
        welcome = cfg['welcome_message']
        embed.add_field(
            name='Boas-vindas (DM)',
            value=truncate(welcome, 1000) if welcome else '*(desativada)*',
            inline=False,
        )
        embed.add_field(name='Agendamentos ativos', value=str(active_schedules), inline=True)
        embed.set_footer(text=f'Variáveis da boas-vindas: {{member}}, {{mention}}, {{server}}')
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='status', description='Mostra latência e as permissões do bot neste servidor.')
    async def status(self, interaction: discord.Interaction):
        guild = interaction.guild
        missing = missing_permissions(guild.me.guild_permissions)
        ok = [perm for perm in REQUIRED_PERMISSIONS if perm not in missing]

        embed = discord.Embed(
            title=f'📊 Status — {guild.name}',
            color=discord.Color.red() if missing else discord.Color.green(),
        )
        embed.add_field(name='Latência', value=f'`{round(self.bot.latency * 1000)}ms`', inline=True)
        embed.add_field(name='Servidores', value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name='IA (/sec)', value='Ativa' if 'AI' in self.bot.cogs else 'Desativada', inline=True)
        embed.add_field(
            name='✅ Permissões OK',
            value='\n'.join(permission_label(p) for p in ok) or '*(nenhuma)*',
            inline=False,
        )
        if missing:
            embed.add_field(
                name='❌ Permissões faltando',
                value='\n'.join(permission_label(p) for p in missing),
                inline=False,
            )
        embed.set_footer(text=f'Modelo de IA: {config.OPENAI_MODEL}')
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
