# --- Do not remove these libs ---
import freqtrade.vendor.qtpylib.indicators as qtpylib

import numpy as np
# --------------------------------
import talib.abstract as ta
#from freqtrade.strategy.interface import IStrategy
from freqtrade.strategy import IStrategy, merge_informative_pair
from pandas import DataFrame, Series, DatetimeIndex, merge


def bollinger_bands(stock_price, window_size, num_of_std):
    rolling_mean = stock_price.rolling(window=window_size).mean()
    rolling_std = stock_price.rolling(window=window_size).std()
    lower_band = rolling_mean - (rolling_std * num_of_std)
    return np.nan_to_num(rolling_mean), np.nan_to_num(lower_band)


class RHComb2(IStrategy):
    # Based on a backtesting:
    # - the best perfomance is reached with "max_open_trades" = 2 (in average for any market),
    #   so it is better to increase "stake_amount" value rather then "max_open_trades" to get more profit
    # - if the market is constantly green(like in JAN 2018) the best performance is reached with
    #   "max_open_trades" = 2 and minimal_roi = 0.01

    order_types = {
        "buy": 'limit',
        "sell": 'limit',
        "stoploss": 'market',
        "stoploss_on_exchange": True,
        "stoploss_on_exchange_interval": 60,
        "stoploss_on_exchange_limit_ratio": 0.99,
    }


    protections = [
    {
        "method": "StoplossGuard",
        "lookback_period_candles": 300,
        "trade_limit": 2,
        "stop_duration_candles": 300,
        "only_per_pair": "true"
    },
    {
        "method": "LowProfitPairs",
        "lookback_period_candles": 24,
        "trade_limit": 1,
        "stop_duration": 300,
        "required_profit": 0.001
    },
    {
        "method": "CooldownPeriod",
        "stop_duration_candles": 2
    },
    {
        "method": "MaxDrawdown",
        "lookback_period_candles": 96,
        "trade_limit": 5,
        "stop_duration_candles": 48,
        "max_allowed_drawdown": 0.2
    }
    ]

    # ROI table:
    minimal_roi = {
        "0": 0.143,
        "10": 0.035,
        "58": 0.016,
        "93": 0
    }

    # Stoploss:
    stoploss = -0.347

    # Trailing stop:
    trailing_stop = True
    trailing_stop_positive = 0.217
    trailing_stop_positive_offset = 0.23
    trailing_only_offset_is_reached = True

    timeframe = '5m'
    #startup_candle_count = 20
    process_only_new_candles = False

    use_sell_signal = True
    sell_profit_only = False
    ignore_roi_if_buy_signal = False

    def informative_pairs(self):
        informative_pairs = [("BTC/USDT", "5m"),]
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:

        # Informative
        if not self.dp:
            # Don't do anything if DataProvider is not available.
            return dataframe
        inf_tf = '5m'
        informative = self.dp.get_pair_dataframe("BTC/USDT", "5m")
        #informative['plus_di'] = ta.PLUS_DI(informative)
        #informative['minus_di'] = ta.MINUS_DI(informative)
        #informative['cmf'] = self.chaikin_mf(informative)
        informative['sma50'] = ta.SMA(informative, timeperiod=50)
        informative['sma200'] = ta.SMA(informative, timeperiod=200)
        informative['pct'] = informative['close'].pct_change(1)
        dataframe = merge_informative_pair(dataframe, informative, self.timeframe, inf_tf, ffill=True)

        # strategy BinHV45
        mid, lower = bollinger_bands(dataframe['close'], window_size=40, num_of_std=2)
        dataframe['lower'] = lower
        dataframe['bbdelta'] = (mid - dataframe['lower']).abs()
        dataframe['closedelta'] = (dataframe['close'] - dataframe['close'].shift()).abs()
        dataframe['tail'] = (dataframe['close'] - dataframe['low']).abs()
        # strategy ClucMay72018
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']

        dataframe['ema100'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['volume_mean_slow'] = dataframe['volume'].rolling(window=30).mean()

	# MACD
	#macd = ta.MACD(dataframe)
	#dataframe['macd'] = macd['macd']
 	#dataframe['macdsignal'] = macd['macdsignal']
 	#dataframe['macdhist'] = macd['macdhist']

	# strategy BBRSI
        #dataframe['rsi'] = ta.RSI(dataframe)
        bollinger4 = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=4)
        dataframe['bb_lowerband4'] = bollinger4['lower']


        # Checks
        #dataframe['btc_bear'] = dataframe['sma200_5m'].lt(dataframe['sma200_5m'].shift(10))
        dataframe['btc_sma_delta'] = ( ( (dataframe['sma50_5m'] - dataframe['sma200_5m']) / dataframe['sma50_5m']) * 100)
        #dataframe['pct'] = dataframe['close'].pct_change(1)
        dataframe['body_pct'] = ((dataframe['open'] - dataframe['close']) * 100) / ((dataframe['open'] - dataframe['close']) + (dataframe['close'] - dataframe['low']))

        dataframe['bb_width'] = ((dataframe['bb_upperband'] - dataframe['bb_lowerband']) / dataframe['bb_middleband'])
        #dataframe['bbw_expansion'] = dataframe['bb_width'].rolling(window=window_size).apply(self.bbw_expansion)

        return dataframe

    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (  # strategy BinHV45
                    (dataframe['btc_sma_delta'] > -2) &
                    (dataframe["bb_width"] > 0.045) &
                    (dataframe['body_pct'] > 70) &
                    dataframe['lower'].shift().gt(0) &
                    dataframe['bbdelta'].gt(dataframe['close'] * 0.008) &
                    dataframe['closedelta'].gt(dataframe['close'] * 0.0175) &
                    dataframe['tail'].lt(dataframe['bbdelta'] * 0.25) &
                    dataframe['close'].lt(dataframe['lower'].shift()) &
                    dataframe['close'].le(dataframe['close'].shift()) &
                    (dataframe['volume'] > 0) # Make sure Volume is not 0
            ) |
            (  # strategy ClucMay72018
                    (dataframe['btc_sma_delta'] > -2) &
                    (dataframe["bb_width"] > 0.045) &
                    (dataframe['body_pct'] > 70) &
                    (dataframe['close'] < dataframe['ema100']) &
                    (dataframe['close'] < 0.985 * dataframe['bb_lowerband']) &
                    (dataframe['volume'] < (dataframe['volume_mean_slow'].shift(1) * 20)) &
                    (dataframe['volume'] > 0) # Make sure Volume is not 0
            #) |
            #(  # strategy BBRSI
            #        (dataframe['btc_sma_delta'] > -2) &
            #        (dataframe['body_pct'] > 70) &
            #        (dataframe["bb_width"] > 0.045) &
            #        (dataframe['rsi'] < 12) &
            #        (dataframe['close'] < dataframe['bb_lowerband4']) &
            #        (dataframe['volume'] > 0) # Make sure Volume is not 0
            ),
            'buy'
        ] = 1
        return dataframe

    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        """
        dataframe.loc[
            #( # Improves the profit slightly.
            #    (dataframe['close'] > dataframe['bb_upperband']) &
            #    (dataframe['close'].shift(1) > dataframe['bb_upperband'].shift(1)) &
            #    (dataframe['volume'] > 0) # Make sure Volume is not 0
            #) |
            (
                dataframe['close'] > dataframe['bb_middleband']
            ),
            'sell'
        ] = 1
        return dataframe

    def chaikin_mf(self, df, periods=20):
        close = df['close']
        low = df['low']
        high = df['high']
        volume = df['volume']

        mfv = ((close - low) - (high - close)) / (high - low)
        mfv = mfv.fillna(0.0)
        mfv *= volume
        cmf = mfv.rolling(periods).sum() / volume.rolling(periods).sum()

        return Series(cmf, name='cmf')
