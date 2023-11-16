import yfinance as yf
import numpy as np
import pandas as pd
import os
import datetime
from datetime import datetime, time, timedelta, timezone
from concurrent import futures
from pandas import DataFrame
import pandas_datareader.data as web
import pymongo
import requests_cache
import time
import pytz
import mplfinance as mpf

#### SCRAPE CODE HERE

# Original start date in Eastern Time (UTC-5) for scrape
start_date_et = datetime(2023, 9, 20, 10, 0, tzinfo=timezone(timedelta(hours=-5)))
end_date_et = datetime(2023, 11, 16, 10, 0, tzinfo=timezone(timedelta(hours=-5)))

# Convert to UTC
start_date_utc = start_date_et.astimezone(timezone.utc)
end_date_utc = end_date_et.astimezone(timezone.utc)

#yfinance is annoying. if want 15m pitch can only do 60 days. 
btc = yf.Ticker("BTC-USD")
btc_df = btc.history(start=start_date_utc, end=end_date_utc, interval="15m")# Fetch data for S&P 500 index

# Drop 'Dividends' and 'Stock Splits' columns
btc_df = btc_df.drop(columns=['Dividends', 'Stock Splits'])

# Add the rate of change over 1/3/6/24 hours and 7 days
intervals_per_hour = 4
btc_df['d1H'] = btc_df['Close'] - btc_df['Close'].shift(1 * intervals_per_hour)
btc_df['d3H'] = btc_df['Close'] - btc_df['Close'].shift(3 * intervals_per_hour)
btc_df['d6H'] = btc_df['Close'] - btc_df['Close'].shift(6 * intervals_per_hour)
btc_df['d1D'] = btc_df['Close'] - btc_df['Close'].shift(24 * intervals_per_hour)
btc_df['d7D'] = btc_df['Close'] - btc_df['Close'].shift(7 * 24 * intervals_per_hour)

# for simplicity lets just trash NaN
btc = btc_df.dropna().copy()
# and add the current (15m) rate of change
btc['Current'] = btc['High'] - btc['Low']

#### HERE IS THE BOT
'''Class TradingBot:
Attributes:
bank_account: To track the balance.
holding: To track whether the bot currently holds BTC.
buy_price: The price at which the bot last bought BTC.
ledger: A list (or another suitable data structure) to record transaction details.
Methods:
__init__: Constructor to initialize the bank account, holding status, buy price, and ledger.
evaluate_buy: To check if the current rate's steepness exceeds the 3-hour rate and decide whether to buy.
evaluate_sell: To check if the profit exceeds 10% and decide whether to sell.
record_transaction: To record the details of each transaction in the ledger.
print_warning: To print a warning in case of a fast enough drop.
apply_to_data: To apply the bot's logic to a dataframe and simulate trading.

The bot checks if there's a drop of more than 2% in the closing price compared to the previous 15-minute interval's closing price.
If such a drop is detected, the print_warning method is called, printing a warning message with the timestamp and the rate of the drop.
This check is performed only if the bot is currently holding BTC (i.e., after a buy and before a sell).


Invest a Fixed Amount ($100) Per Trade: Instead of investing the entire bank account, the bot will only invest $100 in each trade.
Print a Warning if the Bank Account Gets Below $200: Add a check to print a warning if the bank account balance falls below $200.
Handle NaN Values: Ensure the bot skips rows with NaN values to avoid erroneous calculations.
Print an Alert for NaN Values: Print an alert when encountering a row with NaN values.

'''

class TradingBot:
    def __init__(self):
        self.bank_account = 1000  # Starting amount in the bank account
        self.holding = False
        self.buy_price = None
        self.ledger = []
        self.total_trades = 0
        self.total_profit = 0
        self.investment_per_trade = 100

    def evaluate_buy(self, current_rate, rate_3h):
        return current_rate > rate_3h

    def evaluate_sell(self, current_price):
        if self.holding and ((current_price / self.buy_price) - 1) >= 0.1:
            return True
        return False

    def record_transaction(self, time, action, price, profit=None, reason=''):
        self.ledger.append({'time': time, 'action': action, 'price': price, 'profit': profit, 'reason': reason})
        self.total_trades += 1
        if profit:
            self.total_profit += profit

    def print_warning(self, message):
        print(f"Warning: {message}")

    def apply_to_data(self, df):
        for index, row in df.iterrows():
            # Skip rows with NaN values
            if row.isnull().any():
                self.print_warning(f"NaN value detected at {index}. Skipping row.")
                continue

            current_rate = row['Current']
            rate_3h = row['d3H']
            current_price = row['Close']

            if not self.holding and self.evaluate_buy(current_rate, rate_3h):
                if self.bank_account >= self.investment_per_trade:
                    self.holding = True
                    self.buy_price = current_price
                    self.bank_account -= self.investment_per_trade
                    self.record_transaction(index, 'buy', current_price, reason='Rate steeper than 3H rate')
                elif self.bank_account < 200:
                    self.print_warning(f"Account balance below $200 at {index}.")
            elif self.holding and self.evaluate_sell(current_price):
                profit = (current_price - self.buy_price) * (self.investment_per_trade / self.buy_price)
                self.bank_account += self.investment_per_trade + profit
                self.holding = False
                self.record_transaction(index, 'sell', current_price, profit=profit, reason='Gained more than 10%')

        # Print total trades and total profit/loss
        print(f"Total trades: {self.total_trades}")
        print(f"Total profit/loss: {self.total_profit}")

        return self.ledger

# Initialize the bot
bot = TradingBot()

#test data
btc_df_test = btc.copy() #or just load in some csv

# Ensure that the index of btc_df is a datetime index
btc_df_test['Timestamp'] = pd.to_datetime(btc_df_test.index)
btc_df_test.set_index('Timestamp', inplace=True)

# Apply the bot to a section of the dataframe (for example, 'btc_df')
bot.apply_to_data(btc_df_test['2023-09-28':'2023-11-15'])

# Check the ledger for transactions
print(bot.ledger)






# let it use the whole account
# buy if the current rate > 6 h rate

class TradingBotAggressive:
    def __init__(self):
        self.bank_account = 1000  # Starting amount in the bank account
        self.holdings = []  # List to track multiple holdings
        self.ledger = []
        self.total_trades = 0
        self.total_profit = 0
        self.investment_per_trade = 1000

    def evaluate_buy(self, current_rate, rate_6h):
        return current_rate > rate_6h

    def evaluate_sell(self, current_price):
        for holding in self.holdings:
            if ((current_price / holding['buy_price']) - 1) >= 0.1:
                return True
        return False

    def record_transaction(self, time, action, price, profit=None, reason=''):
        self.ledger.append({'time': time, 'action': action, 'price': price, 'profit': profit, 'reason': reason})
        self.total_trades += 1
        if profit:
            self.total_profit += profit

    def print_warning(self, message):
        print(f"Warning: {message}")

    def apply_to_data(self, df):
        for index, row in df.iterrows():
            # Skip rows with NaN values
            if row.isnull().any():
                self.print_warning(f"NaN value detected at {index}. Skipping row.")
                continue

            current_rate = row['Current']
            rate_6h = row['d6H']
            current_price = row['Close']

            # Buy logic
            if self.evaluate_buy(current_rate, rate_6h):
                if self.bank_account >= self.investment_per_trade:
                    self.bank_account -= self.investment_per_trade
                    self.holdings.append({'buy_price': current_price, 'amount': self.investment_per_trade})
                    self.record_transaction(index, 'buy', current_price, reason='Rate steeper than 6H rate')
                elif self.bank_account < 200:
                    self.print_warning(f"Account balance below $200 at {index}.")

            # Sell logic
            if self.evaluate_sell(current_price):
                for holding in self.holdings:
                    profit = (current_price - holding['buy_price']) * (holding['amount'] / holding['buy_price'])
                    self.bank_account += holding['amount'] + profit
                    self.record_transaction(index, 'sell', current_price, profit=profit, reason='Gained more than 10%')
                self.holdings.clear()  # Clear holdings after selling

        # Print total trades and total profit/loss
        print(f"Total trades: {self.total_trades}")
        print(f"Total profit/loss: {self.total_profit}")

        return self.ledger

    
# need logic around when to sell the parcels. its all BTC after all right? 

# Initialize the bot
aggressivebot = TradingBotAggressive()

# Apply the bot to a section of the dataframe (for example, 'btc_df')
aggressivebot.apply_to_data(btc_df_test['2023-09-28':'2023-11-15'])