# Telegram Crypto Checkout Bot

Bot de checkout para Telegram com pagamentos em **BTC**, **LTC**, **ETH** e **SOL**, validação de TXID, controle anti-reuso de transações, geração automática de convite para grupo privado e remoção automática após o vencimento do plano.

> Projeto pronto para publicar no GitHub.

---

## Recursos

- Seleção de plano via bot Telegram.
- Cotação automática via CoinGecko.
- Pagamento em BTC, LTC, ETH e SOL.
- Verificação de transação por TXID/hash.
- Proteção contra reutilização de TXID.
- Tolerância de pagamento configurada em código: aceita a partir de 97% do valor esperado.
- Registro de pedidos em SQLite.
- Link de convite único para grupo privado.
- Expiração automática de acesso:
  - Plano semanal: 7 dias.
  - Plano mensal: 30 dias.
- Reagendamento de remoções pendentes após restart.
- Logs administrativos via Telegram.

---

## Stack

- Python 3.10+
- python-telegram-bot
- SQLite
- Requests
- CoinGecko API
- BlockCypher API
- Solana JSON-RPC

---

## Estrutura

```text
telegram-crypto-checkout-bot/
├── bot.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Pré-requisitos

1. Python 3.10 ou superior.
2. Bot criado no BotFather.
3. Bot adicionado como administrador no grupo privado.
4. Permissões necessárias no grupo:
   - Criar links de convite.
   - Remover membros.
5. Endereços das carteiras configurados nas variáveis de ambiente.

---

## Instalação

Clone o repositório:

```bash
git clone https://github.com/seu-usuario/telegram-crypto-checkout-bot.git
cd telegram-crypto-checkout-bot
```

Crie e ative um ambiente virtual:

```bash
python -m venv .venv
source .venv/bin/activate
```

No Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

---

## Configuração

Copie o arquivo de exemplo:

```bash
cp .env.example .env
```

Edite o `.env`:

```env
BOT_TOKEN=coloque_seu_token_aqui
ADMIN_CHAT_ID=123456789
PRIVATE_GROUP_CHAT_ID=-1001234567891

CHECKOUT_DB=checkout_orders.db
USED_TXIDS_FILE=used_txids.txt

ADDR_BTC=bc1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADDR_LTC=Lxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADDR_ETH=0x0000000000000000000000000000000000000000
ADDR_SOL=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

COINGECKO_TIMEOUT=10
CACHE_TTL=60
POLL_INTERVAL=20
MONITOR_TIMEOUT=3600
```

### Como obter o `PRIVATE_GROUP_CHAT_ID`

Em grupos privados, o ID normalmente começa com `-100`. Use um bot auxiliar, logs do próprio bot ou APIs do Telegram para identificar o ID correto.

---

## Execução

```bash
python bot.py
```

O bot iniciará em modo polling.

---

## Comandos disponíveis

| Comando | Descrição |
|---|---|
| `/start` | Abre o fluxo inicial de escolha do plano. |
| `/plans` | Lista os planos disponíveis. |

---

## Fluxo de pagamento

1. Usuário inicia o bot com `/start`.
2. Escolhe o plano.
3. Escolhe a moeda.
4. O bot calcula o valor aproximado em cripto.
5. Usuário envia o pagamento para o endereço informado.
6. Usuário envia o TXID/hash no chat.
7. O bot valida a transação.
8. Após pelo menos 1 confirmação, o bot libera o link de convite.
9. O usuário é removido automaticamente ao final do período contratado.

---

## Persistência

O projeto usa SQLite por padrão.

Arquivos gerados em runtime:

```text
checkout_orders.db
used_txids.txt
```

Esses arquivos estão no `.gitignore` e não devem ser enviados ao GitHub.

---

## Segurança

Nunca envie para o GitHub:

- Token do bot.
- Arquivo `.env`.
- Banco SQLite de produção.
- Lista real de TXIDs usados.
- Chaves privadas de carteiras.

Este projeto usa apenas endereços públicos de recebimento. Não coloque seed phrase, private key ou mnemonic no código.

---

## Deploy simples em VPS

Exemplo com `systemd`:

```ini
[Unit]
Description=Telegram Crypto Checkout Bot
After=network.target

[Service]
WorkingDirectory=/opt/telegram-crypto-checkout-bot
ExecStart=/opt/telegram-crypto-checkout-bot/.venv/bin/python bot.py
Restart=always
RestartSec=5
EnvironmentFile=/opt/telegram-crypto-checkout-bot/.env

[Install]
WantedBy=multi-user.target
```

Ative o serviço:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-crypto-checkout-bot
sudo systemctl start telegram-crypto-checkout-bot
sudo systemctl status telegram-crypto-checkout-bot
```

---

## Publicação no GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/seu-usuario/telegram-crypto-checkout-bot.git
git push -u origin main
```

---

## Observações técnicas

- BTC, LTC e ETH usam BlockCypher para consulta de transações.
- SOL usa Solana JSON-RPC.
- A cotação é cacheada por `CACHE_TTL` segundos para reduzir chamadas repetidas.
- A remoção automática é persistida no SQLite e reagendada no startup.
- O link de convite é single-use e expira em 48 horas.

---

## Licença

Defina a licença conforme sua necessidade antes de publicar. Sugestão comum para projetos open source: MIT.
