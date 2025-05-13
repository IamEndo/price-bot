import requests
import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Backup manual circulating supply (will be updated manually)
MANUAL_CIRC_SUPPLY = 8_000_000_000_000  # Default value (update as needed)


def get_cg_supply():
    """Fetch circulating supply from CoinGecko markets endpoint."""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "ids": "nexa"}
    try:
        res = requests.get(url, params=params, timeout=5)
        res.raise_for_status()
        data = res.json()
        if data and isinstance(data, list) and "circulating_supply" in data[0]:
            return int(data[0]["circulating_supply"])
        logging.warning("CoinGecko returned unexpected format: %r", data)
    except Exception as e:
        logging.warning("CoinGecko supply error: %s", e)
    return None


def get_circ_supply():
    """Fetch circulating supply (Explorer → CoinGecko → manual)."""
    # 1) Try Nexa Explorer
    try:
        r = requests.get("https://explorer.nexa.org/api/coinsupply", timeout=5)
        r.raise_for_status()
        logging.info("Raw coinsupply response: %r", r.text)

        # JSON-number?
        try:
            data = r.json()
            return int(data)
        except ValueError:
            logging.debug("Not JSON-number, falling back to text parse")

        # Plain-text digits
        return int(r.text.strip())

    except Exception as e:
        logging.error("Explorer supply error: %s", e)

    # 2) Try CoinGecko
    cg_supply = get_cg_supply()
    if cg_supply is not None:
        logging.info("Using CoinGecko supply: %d", cg_supply)
        return cg_supply

    # 3) Fallback to manual
    logging.warning("Falling back to manual supply: %d", MANUAL_CIRC_SUPPLY)
    return MANUAL_CIRC_SUPPLY


def get_mexc_price():
    """Fetches the latest Nexa price from MEXC API."""
    url = "https://api.mexc.com/api/v3/ticker/price?symbol=NEXAUSDT"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "price" in data:
            return float(data["price"])
        logging.warning("Unexpected MEXC API response format: %r", data)
    except Exception as e:
        logging.error(f"MEXC API Error: {e}")
    return None


def get_cg_price():
    """Fetches the latest Nexa price from CoinGecko."""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "ids": "nexa"}
    try:
        res = requests.get(url, params=params, timeout=5)
        res.raise_for_status()
        data = res.json()
        if data and isinstance(data, list) and "current_price" in data[0]:
            return float(data[0]["current_price"])
        logging.warning("CoinGecko price returned unexpected format: %r", data)
    except Exception as e:
        logging.error("CoinGecko price error: %s", e)
    return None


def escape_markdown_v2(text: str) -> str:
    """Escapes Telegram MarkdownV2 special characters."""
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text


def get_nexa_price():
    """Gets the price (MEXC → CoinGecko) and calculates market cap."""
    # 1) Try MEXC
    nexa_price = get_mexc_price()
    source = "MEXC"
    # 2) Fallback to CoinGecko
    if nexa_price is None:
        logging.info("Falling back to CoinGecko for price")
        nexa_price = get_cg_price()
        source = "CoinGecko"

    if nexa_price is None:
        return "\U0001F6A8 Error: Unable to fetch price from MEXC or CoinGecko."

    circ_supply = get_circ_supply()
    market_cap = nexa_price * circ_supply
    circ_supply_trillions = circ_supply / 1_000_000_000_000
    market_cap_millions = market_cap / 1_000_000

    # Price calculations
    price_per_million = nexa_price * 1_000_000
    price_per_billion = nexa_price * 1_000_000_000

    # Properly format values
    market_cap_text = (
        f"Market Cap: ${market_cap_millions:,.2f}M\n"
        f"Circ Supply: {circ_supply_trillions:.3f}T NEXA"
    )

    # Format response
    message = (
        f"NEXA/USDT Price ({source})\n\n"
        f"{nexa_price:.8f}$ per NEXA\n"
        f"{price_per_million:,.2f}$ per 1M NEXA\n"
        f"{price_per_billion:,.0f}$ per 1B NEXA\n\n"
        f"{market_cap_text}"
    )

    return escape_markdown_v2(message)


async def price(update: Update, context: CallbackContext) -> None:
    """Send Nexa price details when /price or /p is called."""
    message = get_nexa_price()
    await update.message.reply_text(message, parse_mode='MarkdownV2')


def main():
    """Start the Telegram bot."""
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler(["price", "p"], price))
    application.run_polling()


if __name__ == "__main__":
    main()