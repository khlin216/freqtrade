import numpy as np
import pandas as pd
import pandas_ta as ta
import talib.abstract as talib
from technical import qtpylib
from freqtrade.strategy import IStrategy, stoploss_from_open, stoploss_from_absolute
from freqtrade.persistence import Trade
from datetime import datetime


class VWAPStrategy_v14(IStrategy):

    INTERFACE_VERSION = 2

    timeframe = '5m'

    minimal_roi = {
        "0": 1
    }

    stoploss = -0.2

    use_custom_stoploss = True

    custom_info = {}

    exit_profit_only = True


    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime, current_rate: float, current_profit: float, after_fill: bool, **kwargs) -> float:

        # Retrieves the analyzed dataframe for the specified currency pair and timeframe
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        # Extracts the last candle (most recent data point) from the dataframe
        last_candle = dataframe.iloc[-1].squeeze()

        if trade.id in self.custom_info:
            # If trade.id is already in custom info -
            # divide current profit by 2
                divided_current_profit = current_profit / 2
                if current_profit >= 0.01 and divided_current_profit > self.custom_info[trade.id]:
                        # If current profit is equal to or greater than 0.01 and if the divided current profit is greater than the already set value -
                        # update the custom_info for the trade with the new divided profit
                        self.custom_info[trade.id] = divided_current_profit
                        # Return new stoploss value (0.5 of current profit)
                        return divided_current_profit
                else:
                    # If current profit is not >= 0.01 or the new stoploss value is lower than the new one -
                    # return previously set stoploss value for the trade
                    return self.custom_info[trade.id]            
        elif pd.notna(last_candle['ATR_stoploss']):
            # Sets custom_info for trade to the last candle ATR stoploss value, if no custom info was previously set
            self.custom_info[trade.id] = last_candle['ATR_stoploss']
            # Return stoploss value based on ATR stoploss
            return last_candle['ATR_stoploss']
        else:
             # If none of the above conditions are true, return None (sets deafult value as stoploss)
             return None

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:

        # Convert 'date' column to datetime format and store it in a new column
        dataframe['date_copy'] = pd.to_datetime(dataframe['date'])

        # Remove timezone information from 'date_copy' column
        dataframe['date_copy'] = dataframe['date_copy'].dt.tz_localize(None)

        # Set 'date_copy' column as the DataFrame index
        dataframe.set_index('date_copy', inplace=True)

        # Calculate and add the Volume Weighted Average Price (VWAP) to the dataframe
        dataframe['VWAP'] = ta.vwap(dataframe['high'], dataframe['low'], dataframe['close'], dataframe['volume'], anchor='D', offset=None)

        # Calclate ATR
        dataframe['ATR'] = ta.atr(dataframe['high'], dataframe['low'], dataframe['close'], length=150)

        # Calculate ATR-based stoploss
        dataframe['ATR_stoploss'] = dataframe['close'] - dataframe['ATR'] * 3.5

        # Calculate EMA
        dataframe['ema200'] = talib.EMA(dataframe, 200)

        # Calculate and add the Relative Strength Index (RSI) to the dataframe
        dataframe['rsi'] = ta.rsi(dataframe['close'], length=16)

        # Calculate the 14-period Simple Moving Average (SMA)
        sma = dataframe['close'].rolling(14).mean()

        # Calculate the Standard Deviation for the same period
        std_dev = dataframe['close'].rolling(14).std()

        # Calculate the Upper Bollinger Band
        dataframe['upper_band'] = sma + (std_dev * 2.0)

        # Calculate the Lower Bollinger Band
        dataframe['lower_band'] = sma - (std_dev * 2.0)

        # Initialize a list to store VWAP signals and set the number of backcandles to consider
        VWAP_signal = [0] * len(dataframe)
        backcandles = 15

        # Iterate over rows in the dataframe to determine VWAP signals
        for row in range(backcandles, len(dataframe)):
            # Initialize flags for up_trend and down_trend
            up_trend = 1
            down_trend = 1

            # Iterate over a range of previous candles to check the relationship between prices and VWAP
            for i in range(row - backcandles, row + 1):
                # Check if the maximum price (open or close) is greater than or equal to VWAP
                if max(dataframe['open'][i], dataframe['close'][i]) >= dataframe['VWAP'][i]:
                    down_trend = 0  # Set down_trend to 0

                # Check if the minimum price (open or close) is less than or equal to VWAP
                if min(dataframe['open'][i], dataframe['close'][i]) <= dataframe['VWAP'][i]:
                    up_trend = 0  # Set up_trend to 0

            # Based on up_trend and down_trend, assign a VWAP signal
            if up_trend == 1 and down_trend == 1:
                VWAP_signal[row] = 3  # Neutral signal
            elif up_trend == 1:
                # Upward trend signal - 15 candles above the VWAP line
                VWAP_signal[row] = 2
            elif down_trend == 1:
                # Downward trend signal - 15 candles below the VWAP line
                VWAP_signal[row] = 1

        # Add the calculated VWAP signals to the dataframe
        dataframe['VWAP_signal'] = VWAP_signal

        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:

        dataframe.loc[
            (
                (dataframe['volume'] > 0) &  # Buy when volume > 0
                (dataframe['VWAP_signal'] == 2) & # Buy when VWAP_signal is 2 (15 candles above VWAP line - indicating bullish trend)
                (dataframe['rsi'] < 45) & # Buy when rsi < 45
                (dataframe['close'] <= dataframe['lower_band']) & # Buy when the current closing price is less than or equal to the current lower bband
                (dataframe['close'].shift(1) <= dataframe['lower_band'].shift(1)) & # Buy when the previous closing price was less than or equal to the lower bband
                (dataframe['lower_band'] != dataframe['upper_band']) # Make sure lower and upper bband is not the same (no momentum)
            ),
            # If all conditions are True for a given row, the 'buy' column for that row is set to 1,
            'buy'
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:

        dataframe.loc[
            (
                (dataframe['volume'] > 0) &  # Sell when volume > 0
                (dataframe['close'] >= dataframe['upper_band']) & # Sell when closing price is the same or above the upper bband
                (dataframe['rsi'] > 55) & # Sell when rsi > 55
                # (dataframe['close'] > dataframe['ema200']) &
                (dataframe['lower_band'] != dataframe['upper_band']) # Make sure lower and upper bband is not the same (no momentum)
            ),
            # If all conditions are True for a given row, the 'sell' column for that row is set to 1
            'sell'
        ] = 1

        return dataframe
