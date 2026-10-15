"""Funções utilitárias para manipular texto enviado ao Discord."""

# Limite de caracteres de uma mensagem do Discord.
DISCORD_MAX_LENGTH = 2000


def split_message(text: str, limit: int = DISCORD_MAX_LENGTH) -> list[str]:
    """Divide o texto em pedaços de até `limit` caracteres, preferindo quebras de linha e espaços."""
    chunks = []
    while len(text) > limit:
        # O separador pode estar exatamente na posição `limit`: ele é descartado no corte.
        cut = text.rfind('\n', 0, limit + 1)
        if cut <= 0:
            cut = text.rfind(' ', 0, limit + 1)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:]
        # Descarta o separador usado no corte.
        if text[:1] in ('\n', ' '):
            text = text[1:]
    if text:
        chunks.append(text)
    return chunks


def truncate(text: str, limit: int) -> str:
    """Corta o texto em `limit` caracteres, terminando com reticências se necessário."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + '…'


def one_line(text: str) -> str:
    """Junta todas as linhas do texto em uma só."""
    return ' '.join(text.split())


def render_template(template: str, **values: str) -> str:
    """Substitui {chave} pelos valores informados (sem str.format, para não interpretar outras chaves)."""
    for key, value in values.items():
        template = template.replace('{' + key + '}', value)
    return template


def render_welcome(template: str, member) -> str:
    """Preenche a mensagem de boas-vindas com {member}, {mention} e {server}."""
    return render_template(template, member=member.display_name, mention=member.mention, server=member.guild.name)
