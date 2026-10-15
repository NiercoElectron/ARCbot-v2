# 🤖 ARC Bot v2

> Bot Discord multi-servidor com IA, moderação completa e agendamento de mensagens — agora com **slash commands**.

---

## ✨ Funcionalidades

Todos os comandos usam `/`. Comandos de moderação e configuração só aparecem para quem tem a permissão correspondente no Discord (e o bot confere de novo na execução).

### 🧠 Inteligência Artificial

Assistente com personalidade própria (modelo configurável, padrão **gpt-5-mini**). Lê as últimas mensagens do canal (até 24h) como contexto. Cooldown de 30 s por usuário.

| Comando | Descrição |
|---------|-----------|
| `/sec pergunta` | Pergunta qualquer coisa ao secretário |

### 🎉 Gerais

| Comando | Descrição |
|---------|-----------|
| `/ping` | Latência do bot |
| `/serverinfo` | Informações do servidor |
| `/userinfo [membro]` | Informações de um membro |
| `/avatar [usuario]` | Avatar em tamanho grande |
| `/help` | Lista os comandos que **você** pode usar |

### 🛡️ Moderação

| Comando | Permissão | Descrição |
|---------|-----------|-----------|
| `/promote membro` · `/demote membro` | Gerenciar cargos | Dá/remove o cargo de promoção |
| `/ban usuario [motivo] [apagar_mensagens]` | Banir membros | Bane (aceita ID de quem não está no servidor) |
| `/unban usuario [motivo]` | Banir membros | Remove o banimento |
| `/softban membro [motivo]` | Banir membros | Bane e desbane apagando 7 dias de mensagens |
| `/kick membro [motivo]` | Expulsar membros | Expulsa do servidor |
| `/mute membro duracao [motivo]` | Castigar membros | Timeout: `10m`, `2h`, `1d`, `1h30m` (máx. 28d) |
| `/unmute membro` | Castigar membros | Remove o timeout |
| `/warn membro motivo` | Castigar membros | Registra aviso e notifica por DM |
| `/warnings usuario` | Castigar membros | Lista avisos (funciona para quem já saiu) |
| `/clearwarns usuario` | Castigar membros | Remove todos os avisos |
| `/purge quantidade [membro]` | Gerenciar mensagens | Apaga até 200 mensagens (opcionalmente só de um membro) |

### ⚙️ Configuração *(Gerenciar servidor)*

| Comando | Descrição |
|---------|-----------|
| `/config autorole [cargo]` | Cargo dado a novos membros (vazio = desativar) |
| `/config promoterole [cargo]` | Cargo usado por `/promote` e `/demote` |
| `/config welcome` | Abre um formulário para editar a DM de boas-vindas (`{member}`, `{mention}`, `{server}`) |
| `/config timezone fuso` | Fuso horário dos agendamentos (com sugestões) |
| `/config show` | Configuração atual |
| `/config status` | Latência e permissões do bot |

### 📅 Agendamentos *(Gerenciar servidor)*

| Comando | Descrição |
|---------|-----------|
| `/schedule add canal horario` | Mensagem **diária** (a mensagem é digitada num formulário) |
| `/schedule add canal horario data` | Mensagem **única** em `dd/mm/aaaa` |
| `/schedule list` | Lista agendamentos com o próximo envio |
| `/schedule remove agendamento` | Remove (com autocompletar) |

Horários seguem o fuso do servidor. Se o bot estiver offline no horário, o envio é tolerado com até 15 min de atraso; depois disso é marcado como perdido (os diários seguem para o dia seguinte).

### 🔧 Desenvolvimento *(apenas o dono do bot, no servidor `DEV_GUILD_ID`)*

| Comando | Descrição |
|---------|-----------|
| `/dev reload modulo` | Recarrega um cog sem reiniciar |
| `/dev sync` | Sincroniza os slash commands |

### 👋 Automações

- **Boas-vindas** por DM ao entrar no servidor
- **Autorole** ao entrar (ou depois de aceitar as regras, se o servidor usa triagem de membros)
- **Aviso de permissões** ao dono quando o bot entra num servidor sem as permissões necessárias

---

## 🗂️ Estrutura

```
.
├── main.py              # Bot (setup_hook, sync de comandos, logging)
├── config.py            # Variáveis de ambiente, constantes e system prompt
├── cogs/
│   ├── ai.py            # /sec
│   ├── general.py       # /ping, /serverinfo, /userinfo, /avatar, /help
│   ├── moderation.py    # /ban, /kick, /mute, /warn, /purge, ...
│   ├── settings.py      # /config ...
│   ├── schedules.py     # /schedule ... + loop de envio
│   ├── events.py        # boas-vindas, autorole, entrada em servidores
│   └── dev.py           # /dev ... (só com DEV_GUILD_ID)
├── utils/
│   ├── database.py      # SQLite (conexão única + migrações versionadas)
│   ├── error_handler.py # Tratamento central de erros de comandos e formulários
│   ├── errors.py        # UserFacingError e resposta efêmera
│   ├── permissions.py   # Checks de permissão e hierarquia de cargos
│   ├── scheduling.py    # Fuso do servidor e reagendamento
│   ├── text.py          # Divisão de mensagens, templates
│   └── timeutils.py     # Durações, horários, datas e fusos
└── tests/               # pytest
```

---

## 🚀 Instalação

### Pré-requisitos

- Python 3.11+
- Aplicação no [Discord Developer Portal](https://discord.com/developers/applications) com os intents privilegiados **Server Members** e **Message Content** ativados (aba *Bot*)
- Chave da [OpenAI](https://platform.openai.com/) (opcional — sem ela o `/sec` fica desativado)

### Passo a passo

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # e preencha
python main.py
```

### Convite do bot

Gere a URL em *OAuth2 → URL Generator* com os escopos **bot** e **applications.commands** e as permissões: Ver canais, Enviar mensagens, Inserir links, Ver histórico de mensagens, Gerenciar mensagens, Gerenciar cargos, Expulsar membros, Banir membros e Castigar membros. O cargo do bot precisa ficar **acima** dos cargos que ele vai gerenciar.

### Variáveis de ambiente (`.env`)

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `DISCORD_TOKEN` | sim | Token do bot |
| `OPENAI_API_KEY` | não | Chave da OpenAI (habilita `/sec`) |
| `OPENAI_MODEL` | não | Modelo da IA (padrão `gpt-5-mini`) |
| `DEV_GUILD_ID` | não | Servidor que recebe os comandos `/dev` |
| `DEFAULT_TIMEZONE` | não | Fuso padrão (padrão `America/Sao_Paulo`) |
| `SYNC_COMMANDS_ON_STARTUP` | não | Sincroniza comandos ao iniciar (padrão `true`) |
| `DB_PATH` / `LOG_PATH` / `LOG_LEVEL` | não | Banco, log (rotativo, 5 MB × 3) e nível de log |

### Testes

```bash
pip install -r requirements-dev.txt
pytest
```

---

## 🔄 O que mudou em relação ao v1

- **Slash commands** no lugar do prefixo `|`, com autocompletar, formulários (modais) e respostas efêmeras para comandos administrativos.
- **Permissões por comando** (Banir membros, Castigar membros, Gerenciar servidor…) em vez de "só dono/admin"; checagem de hierarquia também para o cargo do bot.
- **Erros visíveis**: falhas de permissão do Discord não são mais engolidas em silêncio; erros inesperados vão para o log com um código mostrado ao usuário.
- **`/dev reload`** restrito ao dono do bot (no v1 qualquer admin de qualquer servidor recarregava o bot para todos).
- **Agendamentos** com fuso por servidor, horários normalizados (`9:00` funciona), tolerância a atrasos e status de envio.
- **IA** lê o histórico direto do canal: o bot não grava mais todas as mensagens de todos os servidores no banco. O contexto é marcado como não confiável no prompt e a resposta nunca pinga ninguém.
- **Banco** com conexão única, migrações versionadas e datas em timestamp UTC.
- `/purge @membro` apaga N mensagens **daquele membro**; `/softban` avisa se o desbanimento falhar; `/warnings` funciona para quem já saiu do servidor.

> O banco do v1 (`bot_data.db`) não é importado automaticamente.

---

## 📄 Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE).
