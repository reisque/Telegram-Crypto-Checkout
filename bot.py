"""
telegram-checkout.py — Full script updated with:
- TXID uniqueness using used_txids.txt (reject repeats)
- Value verification with ±3% tolerance (accepts >=97% of expected; overpayments accepted)
- Solana full-value extraction (getTransaction jsonParsed)
- Automatic single-use invite link to private group (-1001234567891)
- Automatic removal after 7 days (weekly) or 30 days (monthly)
- Persisted scheduling across restarts (SQLite)
- Keeps all original functionality and logging

NOTES:
- Ensure the bot is admin in the group -1001234567891 with permissions to create invite links and remove members.
- Keep your BOT_TOKEN private. The token here is taken from your original file but consider using environment variable in production.
"""

import os
import logging
import asyncio
import time
import sqlite3
from decimal import Decimal, ROUND_DOWN
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------- CONFIG ----------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))  # set your admin chat id
DB_PATH = os.getenv("CHECKOUT_DB", "checkout_orders.db")
USED_TXIDS_FILE = os.getenv("USED_TXIDS_FILE", "used_txids.txt")
PRIVATE_GROUP_CHAT_ID = int(os.getenv("PRIVATE_GROUP_CHAT_ID", "0"))  # group where invite links will be generated

# Endereços fixos por moeda
ADDRESSES = {
    "BTC": os.getenv("ADDR_BTC", "bc1q52mnhf72v05nsgnwch5n2pru26s9mxjntnzq7a"),
    "LTC": os.getenv("ADDR_LTC", "Lc6uDm4633qiocrknGhEMeeA4mK4vvuNuB"),
    "ETH": os.getenv("ADDR_ETH", "0xA808ebB2cE78C4537D9C408Dd965ea2db6B78F51"),
    "SOL": os.getenv("ADDR_SOL", "BfyFuKaKfGfAJwWvKEhNSwqya1Fmp7xJxXuhXhLntNX6"),
}

# Planos: chave -> (titulo, descricao, valor_usd)
PLANS = {
    "weekly": {"title": "1 Week", "desc": "1 week of access to the VIP group.", "usd": Decimal("5")},
    "monthly": {"title": "1 Month", "desc": "1 month of access to the VIP group.", "usd": Decimal("15")},
}

# Mapeamento para CoinGecko ids
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "LTC": "litecoin",
    "ETH": "ethereum",
    "SOL": "solana",
}

# Timeout e cache simples (segundos)
COINGECKO_TIMEOUT = int(os.getenv("COINGECKO_TIMEOUT", "10"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))  # cache por 60s para evitar chamadas seguidas
_coingecko_cache = {"timestamp": 0, "data": {}}

# Monitor settings
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))       # segundos entre checagens
MONITOR_TIMEOUT = int(os.getenv("MONITOR_TIMEOUT", str(60 * 60)))  # tempo máximo (1h) antes de desistir

# Tolerance
TOLERANCE_LOWER_RATIO = Decimal("0.97")  # accept >= 97% of expected

# ----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------
# Banco SQLite simples & init
# ----------------------
def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        first_name TEXT,
        plan_key TEXT,
        currency TEXT,
        amount_usd TEXT,
        amount_crypto TEXT,
        address TEXT,
        txid TEXT,
        status TEXT,
        created_at TEXT,
        confirmed_at TEXT
    )
    """)
    # table to persist group invite and removal scheduling
    cur.execute("""
    CREATE TABLE IF NOT EXISTS access_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        user_id INTEGER,
        username TEXT,
        group_id INTEGER,
        invite_link TEXT,
        invite_created_at TEXT,
        expire_at TEXT,
        remove_at TEXT,
        status TEXT
    )
    """)
    conn.commit()
    conn.close()

# ----------------------
# used_txids file control
# ----------------------
def load_used_txids():
    if not os.path.exists(USED_TXIDS_FILE):
        return set()
    with open(USED_TXIDS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def save_used_txid(txid: str):
    with open(USED_TXIDS_FILE, "a") as f:
        f.write(txid + "\n")

# ----------------------
# DB helpers
# ----------------------
def create_order(user_id, username, first_name, plan_key, currency, amount_usd, amount_crypto, address, txid, status="pending"):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO orders (user_id, username, first_name, plan_key, currency, amount_usd, amount_crypto, address, txid, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (user_id, username, first_name, plan_key, currency, str(amount_usd), str(amount_crypto), address, txid, status, now)
    )
    order_id = cur.lastrowid
    conn.commit()
    conn.close()
    return order_id

def update_order_confirmed(txid, amount_crypto=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    if amount_crypto is not None:
        cur.execute("UPDATE orders SET status=?, confirmed_at=?, amount_crypto=? WHERE txid=?", ("confirmed", now, str(amount_crypto), txid))
    else:
        cur.execute("UPDATE orders SET status=?, confirmed_at=? WHERE txid=?", ("confirmed", now, txid))
    conn.commit()
    conn.close()

def get_order_by_tx(txid):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, username, first_name, plan_key, currency, amount_usd, amount_crypto, address, txid, status, created_at, confirmed_at FROM orders WHERE txid=?", (txid,))
    row = cur.fetchone()
    conn.close()
    return row

# --------------------
# Helpers (cotação, format)
# --------------------
def plans_keyboard():
    kb = [
        [InlineKeyboardButton(PLANS["weekly"]["title"], callback_data="plan:weekly")],
        [InlineKeyboardButton(PLANS["monthly"]["title"], callback_data="plan:monthly")],
    ]
    return InlineKeyboardMarkup(kb)

def currency_keyboard(plan_key: str):
    kb = [
        [
            InlineKeyboardButton("BTC", callback_data=f"pay:{plan_key}:BTC"),
            InlineKeyboardButton("LTC", callback_data=f"pay:{plan_key}:LTC"),
        ],
        [
            InlineKeyboardButton("ETH", callback_data=f"pay:{plan_key}:ETH"),
            InlineKeyboardButton("SOL", callback_data=f"pay:{plan_key}:SOL"),
        ],
        [InlineKeyboardButton("◀ Back", callback_data="back:plans")],
    ]
    return InlineKeyboardMarkup(kb)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = (
        f"Hi {user.first_name or 'user'}! 👋\n\n"
        "Choose the plan:"
    )
    await update.message.reply_text(msg, reply_markup=plans_keyboard())

async def plans_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = "Our plans:\n\n"
    for k, v in PLANS.items():
        txt += f"• {v['title']}: {v['desc']} — ${v['usd']}\n"
    txt += "\nChoose the plan:"
    await update.message.reply_text(txt, reply_markup=plans_keyboard())

def _format_amount_for_currency(amount_decimal: Decimal, currency: str) -> str:
    if currency in ("BTC", "LTC"):
        quant = Decimal("0.00000001")
    else:
        quant = Decimal("0.000001")
    return str(amount_decimal.quantize(quant, rounding=ROUND_DOWN))

def fetch_prices_usd(ids: list):
    now = int(time.time())
    if _coingecko_cache["data"] and now - _coingecko_cache["timestamp"] < CACHE_TTL:
        return _coingecko_cache["data"]

    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(ids), "vs_currencies": "usd"}
    try:
        resp = requests.get(url, params=params, timeout=COINGECKO_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        _coingecko_cache["timestamp"] = now
        _coingecko_cache["data"] = data
        return data
    except Exception as e:
        logger.exception("Erro ao buscar preços na CoinGecko: %s", e)
        raise

# --------------------
# Verificação de tx
# --------------------
def check_tx_blockcypher(currency: str, txid: str) -> dict:
    """
    Returns dict with confirmations and raw JSON from BlockCypher.
    """
    chain = currency.lower()
    url = f"https://api.blockcypher.com/v1/{chain}/main/txs/{txid}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    confirmations = data.get("confirmations", 0)
    return {"confirmations": confirmations, "raw": data}

def check_tx_solana(txid: str):
    """
    Busca status e detalhes completos de uma transação Solana.
    Retorna número de confirmações e valor recebido pelo endereço configurado (in SOL).
    """
    rpc_url = "https://api.mainnet-beta.solana.com"

    # Primeiro, obter status e confirmações
    payload_status = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignatureStatuses",
        "params": [[txid], {"searchTransactionHistory": True}]
    }
    resp_status = requests.post(rpc_url, json=payload_status, timeout=15)
    resp_status.raise_for_status()
    data_status = resp_status.json()
    val = data_status.get("result", {}).get("value", [None])[0]
    if val is None:
        return {"confirmations": 0, "received": Decimal("0"), "raw": data_status}

    confirmations = val.get("confirmations", 0) or 0
    status = val.get("confirmationStatus")

    # Depois, obter detalhes completos da transação
    payload_tx = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [txid, {"encoding": "jsonParsed"}]
    }
    resp_tx = requests.post(rpc_url, json=payload_tx, timeout=15)
    resp_tx.raise_for_status()
    data_tx = resp_tx.json()

    # Calcular valor recebido pelo endereço configurado
    received = Decimal("0")
    try:
        # meta.preBalances and meta.postBalances are arrays aligned with transaction message accountKeys
        pre_balances = data_tx["result"]["meta"]["preBalances"]
        post_balances = data_tx["result"]["meta"]["postBalances"]
        account_keys = data_tx["result"]["transaction"]["message"]["accountKeys"]
        for idx, addr_info in enumerate(account_keys):
            addr = addr_info.get("pubkey")
            if addr == ADDRESSES["SOL"]:
                diff = Decimal(post_balances[idx]) - Decimal(pre_balances[idx])
                if diff > 0:
                    received += diff / Decimal(1_000_000_000)  # lamports → SOL
    except Exception as e:
        logger.warning(f"Erro ao calcular valor recebido em Solana: {e}")

    # Definir confirmações mínimas como 1 se finalizada
    if status in ("confirmed", "finalized"):
        confirmations = max(1, confirmations or 1)

    return {"confirmations": confirmations, "received": received, "raw": data_tx}

# --------------------
# Monitor + notificacoes ao admin
# --------------------
async def send_admin_log_on_received(app, admin_chat_id, user_display, plan_key, currency, amount_usd, amount_crypto, txid):
    if not admin_chat_id:
        logger.warning("ADMIN_CHAT_ID não configurado; pulando log de recebido")
        return
    text = (
        f"🆕 *New order received*\n"
        f"User: {user_display}\n"
        f"Plan: {PLANS[plan_key]['title']} ({plan_key})\n"
        f"Coin: {currency}\n"
        f"Amount (USD): ${amount_usd}\n"
        f"TXID: `{txid}`\n"
        f"Status: *received*\n"
    )
    try:
        await app.bot.send_message(chat_id=admin_chat_id, text=text, parse_mode="Markdown")
    except Exception:
        logger.exception("Error sending received order log to admin")

async def send_admin_log_on_confirmed(app, admin_chat_id, user_display, plan_key, currency, amount_usd, amount_crypto, txid):
    if not admin_chat_id:
        logger.warning("ADMIN_CHAT_ID não configurado; pulando log de confirmado")
        return

    try:
        coin_id = COINGECKO_IDS.get(currency)
        prices = await asyncio.get_event_loop().run_in_executor(None, fetch_prices_usd, [coin_id])
        price_usd = Decimal(str(prices[coin_id]["usd"]))
        paid_usd = (Decimal(amount_crypto) * price_usd).quantize(Decimal("0.01"))
    except Exception as e:
        logger.exception("Erro ao converter valor pago em USD: %s", e)
        paid_usd = Decimal("0.00")

    text = (
        f"✅ *Payment confirmed*\n"
        f"User: {user_display}\n"
        f"Plan: {PLANS[plan_key]['title']} ({plan_key})\n"
        f"Coin: {currency}\n"
        f"Amount requested (USD): ${amount_usd}\n"
        f"Amount paid (USD): ${paid_usd}\n"
        f"TXID: `{txid}`\n"
        f"Status: *confirmed*\n"
    )
    try:
        await app.bot.send_message(chat_id=admin_chat_id, text=text, parse_mode="Markdown")
    except Exception:
        logger.exception("Error sending confirmed payment log to admin")

# --------------------
# Group invite + scheduling functions
# --------------------
async def grant_group_access_and_send(app, order_id: int, user_id: int, username: str, plan_key: str, group_id: int):
    """
    Create a single-use invite link to the private group, save it in DB and send to the user.
    Schedule automatic removal according to plan (7 days weekly, 30 days monthly).
    """
    # determine duration
    if plan_key == "weekly":
        duration_days = 7
    elif plan_key == "monthly":
        duration_days = 30
    else:
        duration_days = 7

    # expire link after 48 hours as safety (optional)
    expire_date_dt = datetime.utcnow() + timedelta(days=2)
    expire_timestamp = int(expire_date_dt.timestamp())

    try:
        invite = await app.bot.create_chat_invite_link(
            chat_id=group_id,
            expire_date=expire_timestamp,
            member_limit=1,
            name=f"Access for order {order_id}"
        )
        invite_url = invite.invite_link
    except Exception as e:
        logger.exception("Erro criando invite link: %s", e)
        # notify admin
        try:
            await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Error creating invite link for order {order_id}: {e}")
        except Exception:
            pass
        return None

    created_at = datetime.utcnow().isoformat()
    remove_at_dt = datetime.utcnow() + timedelta(days=duration_days)
    remove_at = remove_at_dt.isoformat()

    # save in DB
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO access_links (order_id, user_id, username, group_id, invite_link, invite_created_at, expire_at, remove_at, status) VALUES (?,?,?,?,?,?,?,?,?)",
        (order_id, user_id, username, group_id, invite_url, created_at, str(expire_timestamp), remove_at, "active")
    )
    conn.commit()
    conn.close()

    # send link to user (English text as requested)
    text = (
        f"Your payment was confirmed!\n\n"
        f"Here is the invite link to the VIP group (single-use, expires in 48h):\n{invite_url}\n\n"
        f"Note: Your access will be valid for {duration_days} days."
    )
    try:
        await app.bot.send_message(chat_id=user_id, text=text)
    except Exception:
        logger.exception("Error sending invite to user %s", user_id)
        # optionally notify admin
        try:
            await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Could not DM invite to user {user_id} for order {order_id}.")
        except Exception:
            pass

    # schedule removal
    delay_seconds = (remove_at_dt - datetime.utcnow()).total_seconds()
    if delay_seconds < 1:
        delay_seconds = 1
    # schedule background task via app
    app.create_task(schedule_removal_task(app, user_id, group_id, delay_seconds, order_id))
    return invite_url

async def schedule_removal_task(app, target_user_id: int, group_id: int, delay_seconds: float, order_id: int):
    try:
        await asyncio.sleep(delay_seconds)
        # ban the user (kick) then unban so they can rejoin later if desired
        try:
            await app.bot.ban_chat_member(chat_id=group_id, user_id=target_user_id)
            await asyncio.sleep(1)
            await app.bot.unban_chat_member(chat_id=group_id, user_id=target_user_id)
        except Exception as e:
            logger.exception("Erro removendo usuário %s do grupo %s: %s", target_user_id, group_id, e)

        # update DB
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        cur.execute("UPDATE access_links SET status=?, remove_at=? WHERE order_id=?", ("removed", now, order_id))
        conn.commit()
        conn.close()

        # notify user (optional)
        try:
            await app.bot.send_message(chat_id=target_user_id, text="Your access to the group has expired and you have been removed. Thank you!")
        except Exception:
            pass
    except asyncio.CancelledError:
        logger.info("Removal task cancelled for user %s", target_user_id)

async def schedule_pending_removals(app):
    """
    Recreate scheduled removal tasks from DB on startup.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT order_id, user_id, group_id, remove_at FROM access_links WHERE status='active'")
    rows = cur.fetchall()
    conn.close()
    for order_id, user_id, group_id, remove_at in rows:
        try:
            remove_dt = datetime.fromisoformat(remove_at)
            delay = (remove_dt - datetime.utcnow()).total_seconds()
            if delay <= 0:
                delay = 1
            app.create_task(schedule_removal_task(app, user_id, group_id, delay, order_id))
            logger.info("Scheduled pending removal for order %s in %s seconds", order_id, int(delay))
        except Exception as e:
            logger.exception("Error scheduling pending removal for order %s: %s", order_id, e)

# --------------------
# Monitor (now returns order_id required for group invite)
# --------------------
async def monitor_tx_and_notify(app, chat_id: int, txid: str, currency: str, expected_amount: str, user_display: str, plan_key: str, amount_usd: Decimal, order_id: int, user_id: int, username: str):
    start_time = time.time()
    logger.info("Starting TX monitoring %s (%s) for chat %s", txid, currency, chat_id)

    while True:
        try:
            total_received = Decimal("0")
            raw = {}

            if currency in ("BTC", "LTC", "ETH"):
                res = await asyncio.get_event_loop().run_in_executor(None, check_tx_blockcypher, currency, txid)
                conf = int(res.get("confirmations", 0))
                raw = res.get("raw", {})
                outputs = raw.get("outputs", [])
                # depending on chain, BlockCypher returns value in satoshis for BTC/LTC, and in "value" for ETH (in wei? BlockCypher returns value in satoshis for BTC/LTC and "value" in Wei for Ethereum? In practice, BlockCypher provides 'outputs' with 'value' in smallest unit)
                total_received = Decimal("0")
                try:
                    for o in outputs:
                        addr_list = o.get("addresses", [])
                        if any(a == ADDRESSES[currency] for a in addr_list):
                            val = Decimal(str(o.get("value", 0)))
                            # convert to human unit
                            if currency in ("BTC", "LTC"):
                                total_received += val / Decimal("100000000")
                            else:
                                # ETH: BlockCypher returns value in "value" as wei - convert to ETH
                                total_received += val / Decimal("1000000000000000000")
                except Exception as e:
                    logger.exception("Error parsing outputs for %s: %s", txid, e)

            elif currency == "SOL":
                res = await asyncio.get_event_loop().run_in_executor(None, check_tx_solana, txid)
                conf = int(res.get("confirmations", 0))
                total_received = res.get("received", Decimal("0"))
                raw = res.get("raw", {})
            else:
                conf = 0
                total_received = Decimal("0")

            logger.info("TX %s (%s) confirmations=%s, received=%s", txid, currency, conf, total_received)

            # When >=1 confirmations, validate value
            if conf >= 1:
                expected = Decimal(expected_amount)
                min_acceptable = (expected * TOLERANCE_LOWER_RATIO).quantize(Decimal("0.00000001"))
                # decide acceptance
                if total_received < min_acceptable:
                    msg = (
                        f"⚠️ Payment detected but amount is too low.\n\n"
                        f"Expected: `{expected_amount} {currency}`\n"
                        f"Received: `{total_received} {currency}`\n\n"
                        "Please contact support to resolve this issue."
                    )
                    await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    logger.warning("Payment below tolerance for %s (expected=%s, got=%s)", txid, expected, total_received)
                    return

                # acceptable (>=97% or greater than expected)
                update_order_confirmed(txid, amount_crypto=str(total_received))
                msg = (
                    f"✅ Payment confirmed!\n\n"
                    f"TXID: `{txid}`\n"
                    f"Coin: {currency}\n"
                    f"Amount received: `{total_received} {currency}`\n\n"
                    "We've received at least 1 confirmation. Thank you! Your access will be granted."
                )
                await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

                # send admin log
                await send_admin_log_on_confirmed(app, ADMIN_CHAT_ID, user_display, plan_key, currency, amount_usd, str(total_received), txid)

                # grant group access & send invite
                try:
                    await grant_group_access_and_send(app, order_id=order_id, user_id=user_id, username=username, plan_key=plan_key, group_id=PRIVATE_GROUP_CHAT_ID)
                except Exception:
                    logger.exception("Error granting group access for order %s", order_id)

                return

        except Exception as e:
            logger.exception("Error checking tx %s: %s", txid, e)

        if time.time() - start_time > MONITOR_TIMEOUT:
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=(f"⚠️ Unable to confirm transaction `{txid}` in {MONITOR_TIMEOUT//60} minutes.\n"
                          "Please check that the TXID is correct and that the transaction has been propagated. Please contact us if necessary."),
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            return

        await asyncio.sleep(POLL_INTERVAL)

# --------------------
# Handlers
# --------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    logger.info("Callback data: %s", data)

    if data.startswith("plan:"):
        _, plan_key = data.split(":", 1)
        plan = PLANS.get(plan_key)
        if not plan:
            await query.edit_message_text("Invalid plan. Please try again.", reply_markup=plans_keyboard())
            return
        text = (
            f"You choose: *{plan['title']}*\n"
            f"{plan['desc']}\n\n"
            "Now select the currency for payment:"
        )
        await query.edit_message_text(text, reply_markup=currency_keyboard(plan_key), parse_mode="Markdown")

    elif data.startswith("pay:"):
        try:
            _, plan_key, currency = data.split(":")
        except ValueError:
            await query.edit_message_text("Invalid. Try /start.")
            return

        addr = ADDRESSES.get(currency)
        if not addr:
            await query.edit_message_text("Currency not configured. Contact your administrator.")
            return

        plan = PLANS.get(plan_key)
        if not plan:
            await query.edit_message_text("Invalid plan. Try /start.")
            return

        coin_id = COINGECKO_IDS.get(currency)
        if not coin_id:
            await query.edit_message_text("Internal error: Currency not mapped.")
            return

        loading_msg = await query.edit_message_text("Checking quote... please wait a moment ⏳")

        try:
            prices = await asyncio.get_event_loop().run_in_executor(None, fetch_prices_usd, [coin_id])
            price_usd = Decimal(str(prices[coin_id]["usd"]))
            target_usd = plan["usd"]
            amount_crypto = (target_usd / price_usd).quantize(Decimal("0.0000000001"))
            amount_str = _format_amount_for_currency(amount_crypto, currency)

            txt = (
                f"== *{currency}* ==\n\n"
                f"Plan: *{plan['title']}* — ${plan['usd']}\n\n"
                f"Send exactly: `{amount_str} {currency}`\n"
                f"Addy:\n`{addr}`\n\n"
                "After payment, submit the TXID/hash here for validation."
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Back to coins", callback_data=f"plan:{plan_key}")],
                [InlineKeyboardButton("◀ Back to home", callback_data="back:plans")]
            ])
            context.user_data['pending_payment'] = {
                "plan_key": plan_key,
                "currency": currency,
                "address": addr,
                "amount_str": amount_str,
                "amount_usd": str(plan['usd'])
            }
            await query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            await query.edit_message_text(
                "Unable to get a quote right now. Please try again in a few seconds or contact the administrator."
            )
            return

    elif data == "back:plans":
        await query.edit_message_text("Choose the plan:", reply_markup=plans_keyboard())

    else:
        await query.edit_message_text("Unknown operation. Use /start to restart.")

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    pending = context.user_data.get('pending_payment')
    if not pending:
        await update.message.reply_text("If you want to pay, choose a plan with /start and follow the instructions.")
        return

    if not (text.isalnum() and len(text) >= 8):
        await update.message.reply_text(
            "Invalid TXID/hash — Make sure you copy the full TXID without spaces. "
            "If you are unsure, send /start and generate a new payment instruction."
        )
        return

    txid = text

    # === check for repeated txid ===
    used_txids = load_used_txids()
    if txid in used_txids:
        await update.message.reply_text(
            "⚠️ This TXID has already been used. Please send a different transaction."
        )
        return
    # ==================================

    currency = pending["currency"]
    amount_str = pending["amount_str"]
    amount_usd = Decimal(pending.get("amount_usd", "0"))

    # Validate tx exists on chain quickly
    try:
        if currency in ("BTC", "LTC", "ETH"):
            await asyncio.get_event_loop().run_in_executor(None, check_tx_blockcypher, currency, txid)
        elif currency == "SOL":
            await asyncio.get_event_loop().run_in_executor(None, check_tx_solana, txid)
        else:
            raise Exception("Currency not supported")
    except Exception as e:
        logger.exception("TX validation failed: %s", e)
        await update.message.reply_text(
            "This transaction could not be located on the blockchain. Please check the TXID and try again."
        )
        return

    username = user.username if user.username else None
    first_name = user.first_name or ""
    user_display = f"@{username}" if username else f"{first_name} (id:{user.id})"

    # create order in DB with status 'received'
    order_id = create_order(user.id, username, first_name, pending['plan_key'], currency, amount_usd, amount_str, pending['address'], txid, status="received")

    # save TXID as used immediately to prevent reuse
    save_used_txid(txid)

    await send_admin_log_on_received(context.application, ADMIN_CHAT_ID, user_display, pending['plan_key'], currency, amount_usd, amount_str, txid)

    await update.message.reply_text(
        f"I received the TXID `{txid}` and created the order #{order_id}. I will monitor it until 1 confirmation and notify you here.",
        parse_mode="Markdown"
    )

    # start monitoring task — pass order_id and user info for later invite grant
    asyncio.create_task(monitor_tx_and_notify(context.application, chat_id, txid, currency, amount_str, user_display, pending['plan_key'], amount_usd, order_id, user.id, username))

    context.user_data.pop('pending_payment', None)

# --------------------
# Entry point
# --------------------
def main():
    init_db()
    if not BOT_TOKEN:
        logger.error("Defina a variável de ambiente BOT_TOKEN.")
        return

    if not PRIVATE_GROUP_CHAT_ID:
        logger.error("Defina a variável de ambiente PRIVATE_GROUP_CHAT_ID.")
        return

    if not ADMIN_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID não definido -- logs para admin serão ignorados. Defina ADMIN_CHAT_ID=")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # schedule pending removals when app loop runs
    # app.create_task will schedule coroutine once the event loop is running
    app.create_task(schedule_pending_removals(app))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("plans", plans_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("Bot iniciado. Rodando polling...")
    app.run_polling(allowed_updates=["callback_query", "message"])

if __name__ == "__main__":
    main()