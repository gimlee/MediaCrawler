# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/tools/utils.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


import argparse
import asyncio
import logging
import random
from numbers import Real
from typing import Optional, Sequence

from .crawler_util import *
from .slider_util import *
from .time_util import *


def init_loging_config():
    level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s (%(filename)s:%(lineno)d) - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    _logger = logging.getLogger("MediaCrawler")
    _logger.setLevel(level)

    # Disable httpx INFO level logs
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return _logger


logger = init_loging_config()

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def get_crawler_sleep_seconds(interval: Optional[object] = None) -> float:
    if interval is None:
        import config
        interval = config.CRAWLER_MAX_SLEEP_SEC

    if isinstance(interval, Sequence) and not isinstance(interval, (str, bytes)):
        if len(interval) != 2:
            raise ValueError("Crawler sleep interval range must contain exactly two values")
        start, end = float(interval[0]), float(interval[1])
        if start > end:
            start, end = end, start
        return random.uniform(start, end)

    if isinstance(interval, Real):
        return float(interval)

    return float(interval)  # type: ignore[arg-type]


async def crawler_sleep(interval: Optional[object] = None) -> float:
    sleep_seconds = get_crawler_sleep_seconds(interval)
    if sleep_seconds > 0:
        await asyncio.sleep(sleep_seconds)
    return sleep_seconds
