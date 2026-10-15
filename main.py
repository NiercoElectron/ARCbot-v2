"""Ponto de entrada do ARCbot v2.

Configura o logging, cria o bot, carrega os cogs, sincroniza os slash commands e conecta ao Discord.
"""

import asyncio
import logging
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands

import config
from utils.database import Database
from utils.error_handler import handle_interaction_error

log = logging.getLogger('arcbot')

EXTENSIONS = [
    'cogs.general',
    'cogs.ai',
    'cogs.moderation',
    'cogs.settings',
    'cogs.schedules',
    'cogs.events',
]
# Comandos /dev só existem quando há um servidor de desenvolvimento configurado.
if config.DEV_GUILD_ID:
    EXTENSIONS.append('cogs.dev')


class ARCBot(commands.Bot):
    """Bot com banco de dados compartilhado e sincronização de slash commands."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # ler o histórico do canal como contexto da IA
        intents.members = True  # boas-vindas e autorole

        super().__init__(
            # O bot só usa slash commands; o prefixo por menção é exigido pela classe, mas não há comandos de texto.
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
            # Nunca pinga @everyone/@here/cargos, a menos que uma mensagem libere explicitamente.
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True, replied_user=True),
        )
        self.db = Database(config.DB_PATH)

    async def setup_hook(self):
        await self.db.connect()
        self.tree.error(handle_interaction_error)
        for ext in EXTENSIONS:
            await self.load_extension(ext)
            log.info('Extensão carregada: %s', ext)
        if config.SYNC_COMMANDS_ON_STARTUP:
            await self.sync_commands()

    async def sync_commands(self) -> str:
        """Envia os slash commands ao Discord e retorna um resumo do que foi sincronizado."""
        synced = await self.tree.sync()
        summary = f'{len(synced)} comandos globais'
        if config.DEV_GUILD_ID:
            dev_synced = await self.tree.sync(guild=discord.Object(id=config.DEV_GUILD_ID))
            summary += f', {len(dev_synced)} no servidor de desenvolvimento'
        log.info('Comandos sincronizados: %s', summary)
        return summary

    async def close(self):
        await super().close()
        await self.db.close()


def setup_logging():
    level = getattr(logging, config.LOG_LEVEL, logging.INFO)
    file_handler = RotatingFileHandler(config.LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
    discord.utils.setup_logging(handler=file_handler, level=level)
    discord.utils.setup_logging(level=level)  # também no console


async def main():
    setup_logging()
    if not config.DISCORD_TOKEN:
        raise SystemExit('DISCORD_TOKEN não definido. Copie .env.example para .env e preencha.')
    bot = ARCBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info('Bot interrompido pelo usuário')
