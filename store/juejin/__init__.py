# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/store/juejin/__init__.py
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


# -*- coding: utf-8 -*-
from typing import List

import config
from base.base_crawler import AbstractStore
from model.m_juejin import JuejinComment, JuejinContent, JuejinCreator
from tools import utils
from var import source_keyword_var
from ._store_impl import (JuejinCsvStoreImplement,
                          JuejinDbStoreImplement,
                          JuejinJsonStoreImplement,
                          JuejinJsonlStoreImplement,
                          JuejinSqliteStoreImplement,
                          JuejinMongoStoreImplement,
                          JuejinExcelStoreImplement)


class JuejinStoreFactory:
    STORES = {
        "csv": JuejinCsvStoreImplement,
        "db": JuejinDbStoreImplement,
        "postgres": JuejinDbStoreImplement,
        "json": JuejinJsonStoreImplement,
        "jsonl": JuejinJsonlStoreImplement,
        "sqlite": JuejinSqliteStoreImplement,
        "mongodb": JuejinMongoStoreImplement,
        "excel": JuejinExcelStoreImplement,
    }

    @staticmethod
    def create_store() -> AbstractStore:
        store_class = JuejinStoreFactory.STORES.get(config.SAVE_DATA_OPTION)
        if not store_class:
            raise ValueError(
                "[JuejinStoreFactory.create_store] Invalid save option only supported csv or db or json or sqlite or mongodb or excel ..."
            )
        return store_class()


async def batch_update_juejin_contents(contents: List[JuejinContent]):
    """Batch update Juejin contents."""
    if not contents:
        return
    for content_item in contents:
        await update_juejin_content(content_item)


async def update_juejin_content(content_item: JuejinContent):
    """Update Juejin content."""
    content_item.source_keyword = source_keyword_var.get()
    local_db_item = content_item.model_dump()
    local_db_item.update({"last_modify_ts": utils.get_current_timestamp()})
    utils.logger.info(f"[store.juejin.update_juejin_content] juejin content: {local_db_item}")
    await JuejinStoreFactory.create_store().store_content(local_db_item)


async def batch_update_juejin_comments(comments: List[JuejinComment]):
    """Batch update Juejin content comments."""
    if not comments:
        return
    for comment_item in comments:
        await update_juejin_content_comment(comment_item)


async def update_juejin_content_comment(comment_item: JuejinComment):
    """Update Juejin content comment."""
    local_db_item = comment_item.model_dump()
    local_db_item.update({"last_modify_ts": utils.get_current_timestamp()})
    utils.logger.info(
        f"[store.juejin.update_juejin_content_comment] juejin content comment:{local_db_item}"
    )
    await JuejinStoreFactory.create_store().store_comment(local_db_item)


async def save_creator(creator: JuejinCreator):
    """Save Juejin creator information."""
    if not creator:
        return
    local_db_item = creator.model_dump()
    local_db_item.update({"last_modify_ts": utils.get_current_timestamp()})
    await JuejinStoreFactory.create_store().store_creator(local_db_item)
