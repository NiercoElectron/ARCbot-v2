"""Comandos gerais: ping, informações de servidor/usuário, avatar e ajuda."""

import discord
from discord import app_commands
from discord.ext import commands

from utils.text import truncate

EMBED_FIELD_MAX = 1024


class General(commands.Cog):
    """Comandos informativos e utilitários públicos."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description='Mostra a latência do bot.')
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f'Pong! `{round(self.bot.latency * 1000)}ms`')

    @app_commands.command(description='Mostra informações sobre o servidor.')
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name='Dono', value=f'<@{guild.owner_id}>', inline=True)
        embed.add_field(name='ID', value=str(guild.id), inline=True)
        embed.add_field(name='Membros', value=str(guild.member_count), inline=True)
        embed.add_field(name='Cargos', value=str(len(guild.roles)), inline=True)
        embed.add_field(name='Canais de texto', value=str(len(guild.text_channels)), inline=True)
        embed.add_field(name='Canais de voz', value=str(len(guild.voice_channels)), inline=True)
        embed.add_field(
            name='Impulsos',
            value=f'{guild.premium_subscription_count} (nível {guild.premium_tier})',
            inline=True,
        )
        embed.add_field(name='Criado em', value=discord.utils.format_dt(guild.created_at, style='D'), inline=True)
        if guild.description:
            embed.add_field(name='Descrição', value=truncate(guild.description, EMBED_FIELD_MAX), inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(description='Mostra informações de um membro.')
    @app_commands.describe(membro='Membro a consultar (padrão: você)')
    @app_commands.guild_only()
    async def userinfo(self, interaction: discord.Interaction, membro: discord.Member | None = None):
        target = membro or interaction.user
        roles = [r.mention for r in reversed(target.roles) if not r.is_default()]

        embed = discord.Embed(
            title=str(target),
            color=target.color if target.color.value else discord.Color.blurple(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name='ID', value=str(target.id), inline=True)
        embed.add_field(name='Apelido', value=target.display_name, inline=True)
        embed.add_field(name='Bot', value='Sim' if target.bot else 'Não', inline=True)
        embed.add_field(name='Conta criada em', value=discord.utils.format_dt(target.created_at, style='D'), inline=True)
        embed.add_field(
            name='Entrou no servidor em',
            value=discord.utils.format_dt(target.joined_at, style='D') if target.joined_at else 'Desconhecido',
            inline=True,
        )
        embed.add_field(name=f'Cargos ({len(roles)})', value=self._join_roles(roles), inline=False)
        await interaction.response.send_message(embed=embed)

    @staticmethod
    def _join_roles(roles: list[str]) -> str:
        """Junta as menções de cargos respeitando o limite de um campo de embed."""
        if not roles:
            return '*(nenhum)*'
        shown = []
        length = 0
        for role in roles:
            if length + len(role) + 1 > EMBED_FIELD_MAX - 20:
                shown.append(f'… e mais {len(roles) - len(shown)}')
                break
            shown.append(role)
            length += len(role) + 1
        return ' '.join(shown)

    @app_commands.command(description='Mostra o avatar de um usuário em tamanho grande.')
    @app_commands.describe(usuario='Usuário (padrão: você)')
    async def avatar(self, interaction: discord.Interaction, usuario: discord.User | None = None):
        target = usuario or interaction.user
        embed = discord.Embed(title=f'Avatar de {target.display_name}', color=discord.Color.blurple())
        embed.set_image(url=target.display_avatar.with_size(1024).url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='help', description='Lista os comandos que você pode usar.')
    async def help_command(self, interaction: discord.Interaction):
        lines = []
        commands_list = self.bot.tree.get_commands(type=discord.AppCommandType.chat_input)
        for command in sorted(commands_list, key=lambda c: c.name):
            if not self._can_use(command, interaction):
                continue
            if isinstance(command, app_commands.Group):
                for sub in command.walk_commands():
                    if isinstance(sub, app_commands.Command):
                        lines.append(f'`/{sub.qualified_name}` — {sub.description}')
            else:
                lines.append(f'`/{command.name}` — {command.description}')

        embed = discord.Embed(
            title='Comandos disponíveis',
            description=truncate('\n'.join(lines), 4096),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text='Comandos de moderação e configuração aparecem só para quem tem as permissões necessárias.')
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @staticmethod
    def _can_use(command: app_commands.Command | app_commands.Group, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return not command.guild_only
        required = command.default_permissions
        perms = interaction.permissions
        return required is None or perms.administrator or required <= perms


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
