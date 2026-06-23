# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/juejin/field.py
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


from enum import Enum


class SearchType(Enum):
    """
    Juejin search_type parameter.
    """
    GENERAL = 0  # 综合 (comprehensive, covers articles)
    ARTICLE = 2  # 文章 (article only)
    PIN = 1  # 动态 / 沸点 (pin / dynamic)
    USER = 9  # 用户 (user)


class SearchSort(Enum):
    """
    Juejin search sort_type parameter.
    """
    DEFAULT = 0  # 综合排序 (default / comprehensive)
    HOT = 1  # 热度排序 (by popularity)
    TIME = 2  # 时间排序 (newest)


class CreatorArticleSort(Enum):
    """
    Juejin creator article list sort_type parameter.
    """
    TIME = 1  # 按发布时间排序
    HOT = 2  # 按热度排序


class CommentSort(Enum):
    """
    Juejin comment list sort_type parameter.
    """
    DEFAULT = 0  # 默认排序
    HOT = 1  # 按热度排序
    TIME = 2  # 按时间排序
