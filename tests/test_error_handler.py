from types import SimpleNamespace

import discord
from discord import app_commands

from utils.error_handler import handle_interaction_error
from utils.errors import UserFacingError


class FakeResponse:
    def __init__(self):
        self.messages = []

    def is_done(self):
        return False

    async def send_message(self, content=None, **kwargs):
        self.messages.append((content, kwargs))


def make_interaction():
    return SimpleNamespace(response=FakeResponse(), command=SimpleNamespace(qualified_name='ban'))


def wrapped(error):
    return app_commands.CommandInvokeError(SimpleNamespace(name='ban'), error)


async def test_forbidden_inside_command_is_reported():
    interaction = make_interaction()
    forbidden = discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'Missing Permissions')

    await handle_interaction_error(interaction, wrapped(forbidden))

    content, kwargs = interaction.response.messages[0]
    assert 'negou a ação' in content
    assert kwargs['ephemeral'] is True


async def test_user_facing_error_message_is_shown_as_is():
    interaction = make_interaction()
    await handle_interaction_error(interaction, UserFacingError('Mensagem amigável.'))
    assert interaction.response.messages[0][0] == 'Mensagem amigável.'


async def test_missing_permissions_are_translated():
    interaction = make_interaction()
    await handle_interaction_error(interaction, app_commands.MissingPermissions(['ban_members']))
    assert 'Banir membros' in interaction.response.messages[0][0]


async def test_unexpected_error_gets_an_error_code(caplog):
    interaction = make_interaction()
    await handle_interaction_error(interaction, wrapped(ValueError('segredo interno')))

    content = interaction.response.messages[0][0]
    assert 'código' in content
    assert 'segredo interno' not in content  # detalhes ficam só no log
    assert 'segredo interno' in caplog.text
