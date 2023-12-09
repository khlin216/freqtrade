from freqtrade.strategy.interface import IStrategy
from pandas import DataFrame
import talib.abstract as ta


class AdxSmasStrategy(IStrategy):
    """
    Strategy Description
    """
    INTERFACE_VERSION = 3

    # Define the minimal ROI, stoploss, timeframe, etc.
    minimal_roi = {
        "2160": 0.025,
        "1440": 0.05,
        "720": 0.075,
        "0": 0.1
    }

    stoploss = -0.25
    timeframe = '1h'

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # SMA Indicators
        dataframe['sma6'] = ta.SMA(dataframe, timeperiod=3)
        dataframe['sma40'] = ta.SMA(dataframe, timeperiod=10)

        # ADX Indicator
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['adx'] > 25) &
                (dataframe['sma6'].shift(1) < dataframe['sma40']) &
                (dataframe['sma6'] > dataframe['sma40'])
            ),
            'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['adx'] < 25) &
                (dataframe['sma40'].shift(1) < dataframe['sma6']) &
                (dataframe['sma40'] > dataframe['sma6'])
            ),
            'exit_long'] = 1

        return dataframe
