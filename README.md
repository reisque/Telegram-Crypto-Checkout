# Telegram Crypto Checkout Bot

Automated Telegram cryptocurrency checkout bot with blockchain transaction validation, VIP group access management, temporary subscriptions, and multi-currency support.

The bot validates on-chain payments automatically, confirms transactions after blockchain confirmations, generates single-use invite links for private Telegram groups, and removes expired members automatically.

---

# Features

## Supported Cryptocurrencies

* Bitcoin (BTC)
* Litecoin (LTC)
* Ethereum (ETH)
* Solana (SOL)

## Payment System

* Automatic blockchain transaction validation
* TXID/hash verification
* Real-time transaction monitoring
* Confirmation-based payment approval
* Underpayment tolerance support
* Overpayment support
* Anti-reuse TXID protection

## Telegram Automation

* Automatic private group invite generation
* Single-use invite links
* Automatic membership expiration
* Automatic member removal
* Admin notifications
* Persistent scheduled removals after restart

## Persistence

* SQLite database storage
* Persistent order history
* Persistent access scheduling
* Recovery after application restart

## Security

* Environment variables support
* No hardcoded secrets
* TXID reuse protection
* Invite expiration system
* Payment validation before access grant

---

# Tech Stack

* Python 3.10+
* python-telegram-bot
* SQLite
* CoinGecko API
* BlockCypher API
* Solana RPC API

---

# Project Structure

```text
telegram-crypto-checkout-bot/
│
├── bot.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── checkout_orders.db
└── used_txids.txt
```

---

# Installation

## 1. Clone the Repository

```bash
git clone https://github.com/your-username/telegram-crypto-checkout-bot.git

cd telegram-crypto-checkout-bot
```

---

## 2. Create a Virtual Environment

### Linux / macOS

```bash
python3 -m venv venv

source venv/bin/activate
```

### Windows

```powershell
python -m venv venv

venv\Scripts\activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Environment Configuration

Create a `.env` file based on `.env.example`.

Example:

```env
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
ADMIN_CHAT_ID=YOUR_ADMIN_CHAT_ID
PRIVATE_GROUP_CHAT_ID=-1001234567891

ADDR_BTC=YOUR_BTC_ADDRESS
ADDR_LTC=YOUR_LTC_ADDRESS
ADDR_ETH=YOUR_ETH_ADDRESS
ADDR_SOL=YOUR_SOL_ADDRESS
```

---

# Telegram Group Requirements

The bot must be an administrator in the private Telegram group with the following permissions:

* Invite users via links
* Ban/remove users
* Manage invite links

---

# Running the Bot

```bash
python bot.py
```

---

# Payment Flow

1. User starts the bot
2. User selects a subscription plan
3. User selects a cryptocurrency
4. Bot generates payment instructions
5. User sends the transaction hash (TXID)
6. Bot validates the transaction on-chain
7. Bot waits for confirmations
8. Payment is confirmed automatically
9. User receives a private group invite link
10. Access expires automatically after the subscription period

---

# Supported Plans

Example:

| Plan    | Duration | Price |
| ------- | -------- | ----- |
| Weekly  | 7 days   | $5    |
| Monthly | 30 days  | $15   |

---

# APIs Used

## CoinGecko

Used for cryptocurrency price conversion.

* [https://www.coingecko.com/](https://www.coingecko.com/)

## BlockCypher

Used for BTC, LTC, and ETH transaction validation.

* [https://www.blockcypher.com/](https://www.blockcypher.com/)

## Solana RPC

Used for Solana transaction validation.

* [https://docs.solana.com/developing/clients/jsonrpc-api](https://docs.solana.com/developing/clients/jsonrpc-api)

---

# Security Recommendations

## Recommended Improvements for Production

* Use PostgreSQL instead of SQLite
* Add rate limiting
* Add webhook support instead of polling
* Encrypt sensitive local data
* Use Docker deployment
* Add centralized logging
* Use environment-based secrets management

---

# Deployment

## Linux Server Example

```bash
sudo apt update

sudo apt install python3 python3-venv -y
```

Run with:

```bash
screen -S telegram-bot
python bot.py
```

Or preferably use:

* systemd
* Docker
* Supervisor
* PM2

---

# Example GitHub Description

```text
Automated Telegram crypto checkout bot with blockchain payment validation, VIP group access management, temporary subscriptions, and multi-currency support.
```

---

# Suggested GitHub Topics

```text
telegram-bot
crypto-payments
bitcoin
ethereum
solana
litecoin
python
web3
telegram-checkout
subscription-bot
payment-gateway
blockchain
telegram-premium-bot
```

---

# Important Translation Notes

Your original script still contains some Portuguese identifiers, comments, logs, and messages.

You should translate:

* Comments
* Logger messages
* Variable descriptions
* User-facing texts
* Error messages
* Function docstrings

Examples:

```python
# BEFORE
logger.info("Bot iniciado")

# AFTER
logger.info("Bot started")
```

```python
# BEFORE
"Erro criando invite link"

# AFTER
"Error creating invite link"
```

```python
# BEFORE
"Defina a variável BOT_TOKEN"

# AFTER
"Set the BOT_TOKEN environment variable"
```

---

# License

MIT License
