# --- Do not remove these libs ---
from freqtrade.strategy.interface import IStrategy
from typing import Dict, List
from functools import reduce
from pandas import DataFrame

# --------------------------------
import talib.abstract as ta
import numpy as np
import freqtrade.vendor.qtpylib.indicators as qtpylib
import datetime
from technical.util import resample_to_interval, resampled_merge
from datetime import datetime, timedelta
from freqtrade.persistence import Trade
from freqtrade.strategy import (
    stoploss_from_open,
    merge_informative_pair,
    DecimalParameter,
    IntParameter,
    CategoricalParameter,
)
import technical.indicators as ftt
import math
import logging

logger = logging.getLogger(__name__)

# @Rallipanos # changes by IcHiAT
