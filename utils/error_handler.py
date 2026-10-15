"""Tratamento centralizado de erros de slash commands e modais."""

import logging
import uuid

import discord
from discord import app_commands

from utils.errors import UserFacingError, respond
from utils.permissions import permission_label

log = logging.getLogger(__name__)


def _format_permissions(perms: list[str]) -> str:
    return ', '.join(f'**{permission_label(p)}**' for p in perms)


async def handle_interaction_error(interaction: discord.Interaction, error: Exception):
    """Converte o erro em uma mensagem para o usuário; erros inesperados são logados com um código."""
    # Exceções levantadas dentro do comando chegam embrulhadas em CommandInvokeError.
    original = getattr(error, 'original', error)

    if isinstance(original, UserFacingError):
        message = str(original)
    elif isinstance(error, app_commands.CommandOnCooldown):
        message = f'Calma lá! Tente de novo em **{error.retry_after:.0f}s**.'
    elif isinstance(error, app_commands.MissingPermissions):
        message = f'Você precisa da permissão {_format_permissions(error.missing_permissions)}.'
    elif isinstance(error, app_commands.BotMissingPermissions):
        message = f'Eu preciso da permissão {_format_permissions(error.missing_permissions)} para isso.'
    elif isinstance(error, app_commands.NoPrivateMessage):
        message = 'Esse comando só funciona em servidores.'
    elif isinstance(error, app_commands.CheckFailure):
        message = 'Você não pode usar esse comando.'
    elif isinstance(original, discord.Forbidden):
        message = (
            'O Discord negou a ação. Confira se tenho as permissões necessárias '
            'e se meu cargo está acima do cargo do alvo.'
        )
    else:
        error_id = uuid.uuid4().hex[:8]
        command = interaction.command.qualified_name if interaction.command else '?'
        log.error('Erro em /%s [%s]', command, error_id, exc_info=original)
        message = f'Algo deu errado. Se continuar, avise a equipe com o código `{error_id}`.'

    try:
        await respond(interaction, message)
    except discord.HTTPException:
        log.warning('Não foi possível enviar a mensagem de erro', exc_info=True)


class BaseModal(discord.ui.Modal):
    """Modal cujos erros passam pelo mesmo tratamento dos comandos."""

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await handle_interaction_error(interaction, error)
