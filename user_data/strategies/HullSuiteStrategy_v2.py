# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file
# --- Do not remove these libs ---
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import datetime
from typing import Optional, Union

from freqtrade.strategy import (
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    IStrategy,
    merge_informative_pair,
)

# --------------------------------
# Add your lib to import here
import talib.abstract as ta
import pandas_ta as pta
from technical import qtpylib
from functools import reduce

import time


class HullSuiteStrategy_v2(IStrategy):
    """
    This is a strategy template to get you started.
    More information in https://www.freqtrade.io/en/latest/strategy-customization/

    You can:
        :return: a Dataframe with all mandatory indicators for the strategies
    - Rename the class name (Do not forget to update class_name)
    - Add any methods you want to build your strategy
    - Add any lib you need to build your strategy

    You must keep:
    - the lib in the section "Do not remove these libs"
    - the methods: populate_indicators, populate_entry_trend, populate_exit_trend
    You should keep:
    - timeframe, minimal_roi, stoploss, trailing_*
    """

    # Strategy interface version - allow new iterations of the strategy interface.
    # Check the documentation or the Sample strategy to get the latest version.
    INTERFACE_VERSION = 3

    # Optimal timeframe for the strategy.
    # timeframe = '1h'
    timeframe = "4h"

    # Can this strategy go short?
    can_short: bool = False

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {
        # "60": 0.01,
        # "30": 0.02,
        # "0": 0.04
        "0": 10
    }

    # Optimal stoploss designed for the strategy.
    # This attribute will be overridden if the config file contains "stoploss".
    stoploss = -0.10

    # Trailing stoploss
    trailing_stop = False
    # trailing_only_offset_is_reached = False
    # trailing_stop_positive = 0.01
    # trailing_stop_positive_offset = 0.0  # Disabled / not configured

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30

    # HULL SUITE
    # hull_length = 55
    hull_length = IntParameter(27, 200, default=75, space="buy")
    buy_trigger = CategoricalParameter(["hma", "thma", "ehma"], default="ehma", space="buy")
    use_macd_buy = BooleanParameter(default=False, space="buy")
    use_macd_sell = BooleanParameter(default=False, space="sell")

    print("macd", use_macd_buy)
    # time.sleep(10000)

    # Optional order type mapping.
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    # Optional order time in force.
    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    @property
    def plot_config(self):
        return {
            # Main plot indicators (Moving averages, ...)
            "main_plot": {
                "hma_55": {"color": "yellow"},
            },
            "subplots": {
                # Subplots - each dict defines one additional plot
                "MACD": {
                    "macd": {"color": "blue"},
                    "macdsignal": {"color": "orange"},
                }
            },
        }

    def informative_pairs(self):
        """
        Define additional, informative pair/interval combinations to be cached from the exchange.
        These pair/interval combinations are non-tradeable, unless they are part
        of the whitelist as well.
        For more information, please consult the documentation
        :return: List of tuples in the format (pair, interval)
            Sample: return [("ETH/USDT", "5m"),
                            ("BTC/USDT", "15m"),
                            ]
        """
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame

        Performance Note: For the best performance be frugal on the number of indicators
        you are using. Let uncomment only the indicator you are using in your strategies
        or your hyperopt configuration, otherwise you will waste your memory and CPU usage.
        :param dataframe: Dataframe with data from the exchange
        :param metadata: Additional information, like the currently traded pair
        :return: a Dataframe with all mandatory indicators for the strategies
        """

        # MACD
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        # dataframe['macdhist'] = macd['macdhist']

        # HULL SUITE
        # HMA
        for val in self.hull_length.range:
            wma1 = ta.WMA(dataframe["close"], int(val / 2))
            wma2 = ta.WMA(dataframe["close"], val)
            dataframe[f"hma_{val}"] = ta.WMA(2 * wma1 - wma2, int(np.sqrt(val)))

        # THMA
        for val in self.hull_length.range:
            # val = val // 2
            wma_1 = ta.WMA(dataframe["close"], val // 3) * 3
            wma_2 = ta.WMA(dataframe["close"], val // 2)
            wma_3 = ta.WMA(dataframe["close"], val)
            dataframe[f"thma_{val}"] = ta.WMA(wma_1 - wma_2 - wma_3, val)

        # EHMA
        for val in self.hull_length.range:
            ema_1 = ta.EMA(dataframe["close"], val // 2)
            ema_2 = ta.EMA(dataframe["close"], val)
            dataframe[f"ehma_{val}"] = ta.EMA(2 * ema_1 - ema_2, int(np.sqrt(val)))

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """

        conditions = []
        if self.use_macd_buy.value:
            conditions.append(qtpylib.crossed_above(dataframe["macd"], dataframe["macdsignal"]))

        if self.buy_trigger.value == "hma":
            conditions.append(
                dataframe[f"hma_{self.hull_length.value}"]
                > dataframe[f"hma_{self.hull_length.value}"].shift(2)
            )
        if self.buy_trigger.value == "thma":
            conditions.append(
                dataframe[f"thma_{self.hull_length.value}"]
                > dataframe[f"thma_{self.hull_length.value}"].shift(2)
            )
        if self.buy_trigger.value == "ehma":
            conditions.append(
                dataframe[f"ehma_{self.hull_length.value}"]
                > dataframe[f"ehma_{self.hull_length.value}"].shift(2)
            )

        conditions.append(dataframe["volume"] > 0)
        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "enter_long"] = 1

            # Print the Analyzed pair
            print(f"result for {metadata['pair']}")

            # Inspect the last 5 rows
            print(dataframe.tail())

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with exit columns populated
        """
        conditions = []
        if self.use_macd_sell.value:
            conditions.append(qtpylib.crossed_above(dataframe["macdsignal"], dataframe["macd"]))

        if self.buy_trigger.value == "hma":
            conditions.append(
                dataframe[f"hma_{self.hull_length.value}"]
                < dataframe[f"hma_{self.hull_length.value}"].shift(2)
            )
        if self.buy_trigger.value == "thma":
            conditions.append(
                dataframe[f"thma_{self.hull_length.value}"]
                < dataframe[f"thma_{self.hull_length.value}"].shift(2)
            )
        if self.buy_trigger.value == "ehma":
            conditions.append(
                dataframe[f"ehma_{self.hull_length.value}"]
                < dataframe[f"ehma_{self.hull_length.value}"].shift(2)
            )

        conditions.append(dataframe["volume"] > 0)
        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), "exit_long"] = 1

            # Print the Analyzed pair
            print(f"result for {metadata['pair']}")

            # Inspect the last 5 rows
            print(dataframe.tail())

        return dataframe
