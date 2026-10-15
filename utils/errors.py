"""Erros com mensagem amigável e helper de resposta efêmera."""

import discord
from discord import app_commands


class UserFacingError(app_commands.AppCommandError):
    """Erro cuja mensagem pode ser mostrada diretamente para quem usou o comando."""


async def respond(interaction: discord.Interaction, content: str | None = None, **kwargs):
    """Responde à interação de forma efêmera, usando followup se ela já foi respondida/adiada."""
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=True, **kwargs)
    else:
        await interaction.response.send_message(content, ephemeral=True, **kwargs)
