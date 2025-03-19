import telebot
import requests
import time
import threading
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Your Telegram Bot Token (from BotFather)
TELEGRAM_TOKEN = "7754247863:AAHEobys36u4K8_c5ZG_fkdXny229_fMy7g"

# Initialize the bot
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Dictionary to store user alerts
user_alerts = {}

# Define hard-coded alert chat ID - Change this to your Telegram chat ID
ADMIN_CHAT_ID = 500017774  # Replace with your actual chat ID

# Available timeframes mapping for Binance
TIMEFRAMES = {
    '5m': '5m',
    '15m': '15m',
    '30m': '30m',
    '1h': '1h',
    '2h': '2h',
    '4h': '4h',
    '8h': '8h',
    '12h': '12h',
    '1d': '1d',
    '3d': '3d',
    '1w': '1w'
}

# Cryptocurrency symbols we want to monitor
CRYPTO_SYMBOLS = ["BTC", "ETH", "LTC", "XRP", "DOGE", "MOVE", "BNB", "TON", "SOL"]

# Timeframes we want to monitor
ALERT_TIMEFRAMES = ["1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w"]

# Bollinger Band parameters
BB_PERIOD = 160
BB_STD_DEV = 2.7

def get_crypto_price(symbol):
    """Get the current price of a cryptocurrency from Binance."""
    try:
        # Binance uses trading pairs like BTCUSDT, ETHUSDT, etc.
        trading_pair = f"{symbol.upper()}USDT"
        
        # Fetch from Binance API
        response = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={trading_pair}")
        
        # Check if request was successful
        if response.status_code == 200:
            data = response.json()
            # Return the last trade price
            return float(data['price'])
        else:
            # If trading pair not found or other error
            print(f"Error: Status code {response.status_code} for {symbol}")
            return None
            
    except Exception as e:
        print(f"Error getting price from Binance: {e}")
        return None

def get_historical_data(symbol, timeframe='1h', limit=500):
    """Get historical OHLCV data from Binance."""
    try:
        trading_pair = f"{symbol.upper()}USDT"
        
        url = f"https://api.binance.com/api/v3/klines?symbol={trading_pair}&interval={timeframe}&limit={limit}"
        print(f"Requesting data from: {url}")  # Add this for debugging
        
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            if not data:  # Check if data is empty
                print(f"Empty data returned for {symbol} with timeframe {timeframe}")
                return None
                
            # Create DataFrame with proper column names
            columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                       'close_time', 'quote_asset_volume', 'number_of_trades', 
                       'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore']
            df = pd.DataFrame(data, columns=columns)
            
            # Convert types
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            
            print(f"Got {len(df)} data points for {symbol} with timeframe {timeframe}")
            return df
        else:
            print(f"Error getting historical data: Status code {response.status_code}")
            return None
    except Exception as e:
        print(f"Error getting historical data: {e}")
        return None

def calculate_bollinger_bands(symbol, period=160, std_dev=2.7, timeframe='1h'):
    """Calculate Bollinger Bands for a given symbol."""
    try:
        # Calculate how many data points we need
        needed_limit = max(500, period * 2)  # At least twice the period for better calculations
        
        # Get historical data
        df = get_historical_data(symbol, timeframe, limit=needed_limit)
        if df is None or len(df) < period:
            return None
        
        # Calculate Bollinger Bands
        df['sma'] = df['close'].rolling(window=period).mean()
        df['std'] = df['close'].rolling(window=period).std()
        df['upper_band'] = df['sma'] + (df['std'] * std_dev)
        df['lower_band'] = df['sma'] - (df['std'] * std_dev)
        
        # Get the latest values
        latest = df.iloc[-1]
        
        result = {
            'price': latest['close'],
            'upper_band': latest['upper_band'],
            'lower_band': latest['lower_band'],
            'sma': latest['sma'],
            'timestamp': latest['timestamp'],
            'timeframe': timeframe
        }
        
        return result
    except Exception as e:
        print(f"Error calculating Bollinger Bands: {e}")
        return None

# Start command
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    timeframes_text = ", ".join(TIMEFRAMES.keys())
    
    bot.reply_to(message, 
        'Welcome to the Crypto Price & Technical Alert Bot!\n\n'
        'Commands:\n'
        '/price <symbol> - Get current price (e.g., /price BTC)\n'
        f'/bb <symbol> [period] [std_dev] [timeframe] - Get Bollinger Bands (e.g., /bb BTC 160 2.7 1h)\n'
        '  Available timeframes: ' + timeframes_text + '\n'
        '/alert <symbol> <condition> <price> - Set price alert (e.g., /alert BTC > 50000)\n'
        f'/bbalert <symbol> <band> <period> <std_dev> <timeframe> - Set Bollinger Band alert\n'
        '  Example: /bbalert BTC upper 160 2.7 4h\n'
        '/alerts - View your active alerts\n'
        '/deletealert <alert_id> - Delete a specific alert\n'
        '/help - Show this help message'
    )

# Price command
@bot.message_handler(commands=['price'])
def handle_price(message):
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, 'Usage: /price <symbol> (e.g., /price BTC)')
        return
    
    symbol = parts[1].upper()
    price = get_crypto_price(symbol)
    
    if price:
        bot.reply_to(message, f"Current price of {symbol} on Binance: ${price:,.2f}")
    else:
        bot.reply_to(message, f"Could not retrieve price for {symbol}. Make sure the symbol is correct and supported by Binance.")

# Bollinger Bands command
@bot.message_handler(commands=['bb'])
def handle_bollinger_bands(message):
    parts = message.text.split()
    
    if len(parts) < 2 or len(parts) > 5:
        timeframes_text = ", ".join(TIMEFRAMES.keys())
        bot.reply_to(message, f'Usage: /bb <symbol> [period] [std_dev] [timeframe]\nExample: /bb BTC 160 2.7 1h\nAvailable timeframes: {timeframes_text}')
        return
    
    symbol = parts[1].upper()
    
    # Default values
    period = 160
    std_dev = 2.7
    timeframe = '1h'
    
    # Parse optional parameters
    if len(parts) >= 3:
        try:
            period = int(parts[2])
        except ValueError:
            bot.reply_to(message, 'Invalid period. Please enter a valid number.')
            return
    
    if len(parts) >= 4:
        try:
            std_dev = float(parts[3])
        except ValueError:
            bot.reply_to(message, 'Invalid standard deviation. Please enter a valid number.')
            return
    
    if len(parts) == 5:
        timeframe = parts[4]
        if timeframe not in TIMEFRAMES:
            timeframes_text = ", ".join(TIMEFRAMES.keys())
            bot.reply_to(message, f'Invalid timeframe. Available options: {timeframes_text}')
            return
    
    bb_data = calculate_bollinger_bands(symbol, period, std_dev, timeframe)
    
    if bb_data:
        response = (
            f"Bollinger Bands for {symbol} (Period: {period}, StdDev: {std_dev}, Timeframe: {timeframe}):\n\n"
            f"Current Price: ${bb_data['price']:,.2f}\n"
            f"Upper Band: ${bb_data['upper_band']:,.2f}\n"
            f"SMA: ${bb_data['sma']:,.2f}\n"
            f"Lower Band: ${bb_data['lower_band']:,.2f}\n\n"
            f"Time: {bb_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        bot.reply_to(message, response)
    else:
        bot.reply_to(message, f"Could not calculate Bollinger Bands for {symbol}. Please check if the symbol is supported and has enough historical data.")

# Alert command
@bot.message_handler(commands=['alert'])
def handle_alert(message):
    parts = message.text.split()
    if len(parts) != 4:
        bot.reply_to(message, 'Usage: /alert <symbol> <condition> <price> (e.g., /alert BTC > 50000)')
        return
    
    symbol = parts[1].upper()
    condition = parts[2]
    
    if condition not in ['>', '<', '>=', '<=']:
        bot.reply_to(message, 'Invalid condition. Use >, <, >=, or <=')
        return
    
    try:
        price = float(parts[3])
    except ValueError:
        bot.reply_to(message, 'Invalid price. Please enter a valid number.')
        return
    
    # Verify the symbol is available on Binance
    if get_crypto_price(symbol) is None:
        bot.reply_to(message, f"Symbol {symbol} not found on Binance. Please check if it's supported.")
        return
    
    user_id = message.from_user.id
    
    if user_id not in user_alerts:
        user_alerts[user_id] = []
    
    alert_id = len(user_alerts[user_id]) + 1
    
    user_alerts[user_id].append({
        'id': alert_id,
        'type': 'price',
        'symbol': symbol,
        'condition': condition,
        'price': price,
        'triggered': False
    })
    
    bot.reply_to(message, f"Alert #{alert_id} set: {symbol} {condition} ${price:,.2f}")

# Bollinger Band Alert command
@bot.message_handler(commands=['bbalert'])
def handle_bb_alert(message):
    parts = message.text.split()
    
    if len(parts) < 5 or len(parts) > 6:
        timeframes_text = ", ".join(TIMEFRAMES.keys())
        bot.reply_to(message, 
            'Usage: /bbalert <symbol> <band> <period> <std_dev> [timeframe]\n'
            'Example: /bbalert BTC upper 160 2.7 4h\n'
            f'Available timeframes: {timeframes_text}'
        )
        return
    
    symbol = parts[1].upper()
    band = parts[2].lower()
    
    if band not in ['upper', 'lower']:
        bot.reply_to(message, 'Invalid band. Use "upper" or "lower".')
        return
    
    try:
        period = int(parts[3])
    except ValueError:
        bot.reply_to(message, 'Invalid period. Please enter a valid number.')
        return
    
    try:
        std_dev = float(parts[4])
    except ValueError:
        bot.reply_to(message, 'Invalid standard deviation. Please enter a valid number.')
        return
    
    # Default timeframe is 1h
    timeframe = '1h'
    
    # Parse optional timeframe
    if len(parts) == 6:
        timeframe = parts[5]
        if timeframe not in TIMEFRAMES:
            timeframes_text = ", ".join(TIMEFRAMES.keys())
            bot.reply_to(message, f'Invalid timeframe. Available options: {timeframes_text}')
            return
    
    # Verify we can calculate BB for this symbol
    bb_data = calculate_bollinger_bands(symbol, period, std_dev, timeframe)
    if bb_data is None:
        bot.reply_to(message, f"Could not calculate Bollinger Bands for {symbol}. Please check if it's supported and has enough historical data.")
        return
    
    user_id = message.from_user.id
    
    if user_id not in user_alerts:
        user_alerts[user_id] = []
    
    alert_id = len(user_alerts[user_id]) + 1
    
    # Set the condition based on the band
    if band == 'upper':
        condition = '>='
        target_price = bb_data['upper_band']
        condition_desc = "price crosses above upper band"
    else:  # lower
        condition = '<='
        target_price = bb_data['lower_band']
        condition_desc = "price crosses below lower band"
    
    user_alerts[user_id].append({
        'id': alert_id,
        'type': 'bollinger',
        'symbol': symbol,
        'band': band,
        'period': period,
        'std_dev': std_dev,
        'timeframe': timeframe,
        'condition': condition,
        'price': None,  # This will be dynamically calculated
        'triggered': False
    })
    
    bot.reply_to(message, f"Bollinger Band Alert #{alert_id} set: {symbol} when {condition_desc} (Period: {period}, StdDev: {std_dev}, Timeframe: {timeframe})")

# View alerts command
@bot.message_handler(commands=['alerts'])
def handle_view_alerts(message):
    user_id = message.from_user.id
    
    if user_id not in user_alerts or not user_alerts[user_id]:
        bot.reply_to(message, "You don't have any active alerts.")
        return
    
    alerts_text = "Your active alerts:\n\n"
    
    for alert in user_alerts[user_id]:
        if not alert['triggered']:
            if alert['type'] == 'price':
                alerts_text += f"Alert #{alert['id']}: {alert['symbol']} {alert['condition']} ${alert['price']:,.2f}\n"
            else:  # bollinger
                band_name = "upper" if alert['band'] == 'upper' else "lower"
                alerts_text += f"Alert #{alert['id']}: {alert['symbol']} crosses {band_name} Bollinger Band (Period: {alert['period']}, StdDev: {alert['std_dev']}, Timeframe: {alert['timeframe']})\n"
    
    bot.reply_to(message, alerts_text)

# Delete alert command
@bot.message_handler(commands=['deletealert'])
def handle_delete_alert(message):
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, 'Usage: /deletealert <alert_id>')
        return
    
    try:
        alert_id = int(parts[1])
    except ValueError:
        bot.reply_to(message, 'Invalid alert ID. Please enter a valid number.')
        return
    
    user_id = message.from_user.id
    
    if user_id not in user_alerts:
        bot.reply_to(message, "You don't have any alerts.")
        return
    
    for i, alert in enumerate(user_alerts[user_id]):
        if alert['id'] == alert_id:
            del user_alerts[user_id][i]
            bot.reply_to(message, f"Alert #{alert_id} deleted.")
            return
    
    bot.reply_to(message, f"Alert #{alert_id} not found.")

# Function to create hard-coded alerts for all specified symbols and timeframes
def create_hard_coded_alerts():
    # Use the admin chat ID for the hard-coded alerts
    if ADMIN_CHAT_ID not in user_alerts:
        user_alerts[ADMIN_CHAT_ID] = []
    
    alert_id = 1
    
    # Create upper and lower band alerts for all combinations
    for symbol in CRYPTO_SYMBOLS:
        for timeframe in ALERT_TIMEFRAMES:
            # Upper band alert
            user_alerts[ADMIN_CHAT_ID].append({
                'id': alert_id,
                'type': 'bollinger',
                'symbol': symbol,
                'band': 'upper',
                'period': BB_PERIOD,
                'std_dev': BB_STD_DEV,
                'timeframe': timeframe,
                'condition': '>=',
                'price': None,  # Will be dynamically calculated
                'triggered': False,
                'last_triggered': None  # Track when it was last triggered
            })
            alert_id += 1
            
            # Lower band alert
            user_alerts[ADMIN_CHAT_ID].append({
                'id': alert_id,
                'type': 'bollinger',
                'symbol': symbol,
                'band': 'lower',
                'period': BB_PERIOD,
                'std_dev': BB_STD_DEV,
                'timeframe': timeframe,
                'condition': '<=',
                'price': None,  # Will be dynamically calculated
                'triggered': False,
                'last_triggered': None  # Track when it was last triggered
            })
            alert_id += 1
    
    print(f"Created {alert_id-1} hard-coded Bollinger Band alerts for admin chat ID: {ADMIN_CHAT_ID}")

# Thread to check alerts
def check_alerts_thread():
    while True:
        print("Checking alerts...")
        for user_id, alerts in user_alerts.items():
            for alert in alerts:
                # For hard-coded alerts, we want to reset the trigger after some time
                current_time = datetime.now()
                
                # Reset triggered status for hard-coded alerts after 24 hours
                if alert.get('last_triggered') and (current_time - alert['last_triggered']).total_seconds() > 86400:
                    alert['triggered'] = False
                
                if not alert['triggered']:
                    # Price alert
                    if alert['type'] == 'price':
                        current_price = get_crypto_price(alert['symbol'])
                        if current_price is None:
                            continue
                        
                        condition_met = False
                        if alert['condition'] == '>' and current_price > alert['price']:
                            condition_met = True
                        elif alert['condition'] == '<' and current_price < alert['price']:
                            condition_met = True
                        elif alert['condition'] == '>=' and current_price >= alert['price']:
                            condition_met = True
                        elif alert['condition'] == '<=' and current_price <= alert['price']:
                            condition_met = True
                        
                        if condition_met:
                            alert['triggered'] = True
                            alert['last_triggered'] = current_time
                            try:
                                bot.send_message(
                                    chat_id=user_id,
                                    text=f"🚨 PRICE ALERT: {alert['symbol']} is now ${current_price:,.2f}, which is {alert['condition']} your alert price of ${alert['price']:,.2f}"
                                )
                            except Exception as e:
                                print(f"Error sending message: {e}")
                    
                    # Bollinger Band alert
                    elif alert['type'] == 'bollinger':
                        bb_data = calculate_bollinger_bands(
                            alert['symbol'], 
                            alert['period'], 
                            alert['std_dev'], 
                            alert['timeframe']
                        )
                        
                        if bb_data is None:
                            continue
                        
                        current_price = bb_data['price']
                        
                        condition_met = False
                        if alert['band'] == 'upper' and current_price > bb_data['upper_band']:
                            condition_met = True
                            band_value = bb_data['upper_band']
                            band_name = "upper"
                        elif alert['band'] == 'lower' and current_price < bb_data['lower_band']:
                            condition_met = True
                            band_value = bb_data['lower_band']
                            band_name = "lower"
                        
                        if condition_met:
                            alert['triggered'] = True
                            alert['last_triggered'] = current_time
                            try:
                                bot.send_message(
                                    chat_id=user_id,
                                    text=f"🚨 BOLLINGER BAND ALERT: {alert['symbol']} price (${current_price:,.2f}) has crossed the {band_name} band (${band_value:,.2f})\n"
                                         f"BB Parameters: Period {alert['period']}, StdDev {alert['std_dev']}, Timeframe: {alert['timeframe']}"
                                )
                            except Exception as e:
                                print(f"Error sending message: {e}")
        
        # Sleep for 1 hour before checking again
        print(f"Finished checking alerts. Sleeping for 1 hour until {datetime.now() + timedelta(hours=1)}")
        time.sleep(3600)  # Check every hour (3600 seconds)

# Start the bot
if __name__ == "__main__":
    print("Creating hard-coded alerts...")
    create_hard_coded_alerts()
    
    print("Starting alert checking thread...")
    alert_thread = threading.Thread(target=check_alerts_thread)
    alert_thread.daemon = True
    alert_thread.start()
    
    print("Bot started! Press Ctrl+C to exit.")
    bot.infinity_polling()