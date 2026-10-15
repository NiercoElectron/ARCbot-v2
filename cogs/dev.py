"""Comandos /dev, restritos ao dono do bot e registrados só no servidor de desenvolvimento."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.errors import UserFacingError

log = logging.getLogger(__name__)


@app_commands.default_permissions(administrator=True)
class Dev(commands.GroupCog, group_name='dev', group_description='Ferramentas do dono do bot.'):
    """Recarregar módulos e sincronizar comandos sem reiniciar o bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Recarregar módulos afeta todos os servidores, então só o dono do bot pode.
        if not await self.bot.is_owner(interaction.user):
            raise UserFacingError('Apenas o dono do bot pode usar esse comando.')
        return True

    @app_commands.command(name='reload', description='Recarrega um módulo (cog) sem reiniciar o bot.')
    @app_commands.describe(modulo='Módulo a recarregar')
    async def reload(self, interaction: discord.Interaction, modulo: str):
        try:
            await self.bot.reload_extension(modulo)
        except commands.ExtensionError as error:
            log.exception('Falha ao recarregar %s', modulo)
            raise UserFacingError(f'Falha ao recarregar `{modulo}`: {error}') from None
        await interaction.response.send_message(
            f'✅ `{modulo}` recarregado. Se mudou nomes/opções de comandos, rode `/dev sync`.',
            ephemeral=True,
        )

    @reload.autocomplete('modulo')
    async def reload_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=name, value=name)
            for name in sorted(self.bot.extensions)
            if current.lower() in name.lower()
        ][:25]

    @app_commands.command(name='sync', description='Sincroniza os slash commands com o Discord.')
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        summary = await self.bot.sync_commands()
        await interaction.followup.send(f'✅ Sincronizado: {summary}.', ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Dev(bot), guild=discord.Object(id=config.DEV_GUILD_ID))
