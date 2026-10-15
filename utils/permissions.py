"""Permissões necessárias, checks de comandos e validação de hierarquia de cargos."""

import discord
from discord import app_commands

from utils.errors import UserFacingError

# Permissões que o bot precisa no servidor para todas as funcionalidades.
REQUIRED_PERMISSIONS = (
    'view_channel',
    'send_messages',
    'embed_links',
    'read_message_history',
    'manage_messages',
    'manage_roles',
    'kick_members',
    'ban_members',
    'moderate_members',
)

PERMISSION_LABELS = {
    'administrator': 'Administrador',
    'ban_members': 'Banir membros',
    'embed_links': 'Inserir links',
    'kick_members': 'Expulsar membros',
    'manage_guild': 'Gerenciar servidor',
    'manage_messages': 'Gerenciar mensagens',
    'manage_roles': 'Gerenciar cargos',
    'moderate_members': 'Castigar membros',
    'read_message_history': 'Ver histórico de mensagens',
    'send_messages': 'Enviar mensagens',
    'view_channel': 'Ver canais',
}


def permission_label(name: str) -> str:
    """Nome legível (como aparece no Discord) de uma permissão."""
    return PERMISSION_LABELS.get(name, name.replace('_', ' ').capitalize())


def missing_permissions(permissions: discord.Permissions, required=REQUIRED_PERMISSIONS) -> list[str]:
    """Retorna as permissões de `required` que faltam em `permissions`."""
    return [perm for perm in required if not getattr(permissions, perm, False)]


def moderator_command(**perms: bool):
    """Restringe um comando a servidores e a membros que tenham `perms`, e exige o mesmo do bot.

    O Discord esconde o comando de quem não tem as permissões (default_permissions), e os
    checks validam de novo na execução — mesmo que as permissões da integração sejam
    alteradas nas configurações do servidor.
    """
    def decorator(func):
        func = app_commands.guild_only()(func)
        func = app_commands.default_permissions(**perms)(func)
        func = app_commands.checks.has_permissions(**perms)(func)
        func = app_commands.checks.bot_has_permissions(**perms)(func)
        return func
    return decorator


def require_permissions(interaction: discord.Interaction, **perms: bool):
    """Versão para interaction_check de GroupCogs: levanta MissingPermissions se faltar algo."""
    missing = [perm for perm, value in perms.items() if getattr(interaction.permissions, perm) != value]
    if missing:
        raise app_commands.MissingPermissions(missing)


def ensure_can_moderate(actor: discord.Member, target: discord.Member):
    """Garante que `actor` e o bot podem aplicar uma ação de moderação em `target`."""
    guild = actor.guild
    if target.id == actor.id:
        raise UserFacingError('Você não pode fazer isso consigo mesmo.')
    if target.id == guild.me.id:
        raise UserFacingError('Não posso fazer isso comigo mesmo.')
    if target.id == guild.owner_id:
        raise UserFacingError('Não é possível fazer isso com o dono do servidor.')
    if actor.id != guild.owner_id and target.top_role >= actor.top_role:
        raise UserFacingError(f'{target.mention} tem um cargo igual ou superior ao seu.')
    if target.top_role >= guild.me.top_role:
        raise UserFacingError(
            f'Não consigo agir sobre {target.mention}: meu cargo mais alto precisa estar '
            'acima do cargo mais alto desse membro.'
        )


def ensure_role_manageable(actor: discord.Member, role: discord.Role):
    """Garante que `actor` e o bot podem atribuir/remover `role`."""
    guild = actor.guild
    if role.is_default() or role.managed:
        raise UserFacingError(f'O cargo {role.mention} é gerenciado pelo Discord ou por uma integração.')
    if not guild.me.guild_permissions.manage_roles:
        raise UserFacingError('Preciso da permissão **Gerenciar cargos** para isso.')
    if not role.is_assignable():
        raise UserFacingError(
            f'Não consigo gerenciar {role.mention}: ele está acima ou no mesmo nível do meu cargo mais alto.'
        )
    if actor.id != guild.owner_id and role >= actor.top_role:
        raise UserFacingError(
            f'Você não pode gerenciar {role.mention}: ele está acima ou no mesmo nível do seu cargo mais alto.'
        )
