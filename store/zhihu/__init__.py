# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/store/zhihu/__init__.py
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
from constant import zhihu as zhihu_constant
from base.base_crawler import AbstractStore
from database.db_session import get_session
from database.models import ZhihuContent as ZhihuContentModel
from model.m_zhihu import ZhihuComment, ZhihuContent, ZhihuCreator
from sqlalchemy import func, or_, select
from ._store_impl import (ZhihuCsvStoreImplement,
                                          ZhihuDbStoreImplement,
                                          ZhihuJsonStoreImplement,
                                          ZhihuJsonlStoreImplement,
                                          ZhihuSqliteStoreImplement,
                                          ZhihuMongoStoreImplement,
                                          ZhihuExcelStoreImplement)
from tools import utils
from var import source_keyword_var


class ZhihuStoreFactory:
    STORES = {
        "csv": ZhihuCsvStoreImplement,
        "db": ZhihuDbStoreImplement,
        "postgres": ZhihuDbStoreImplement,
        "json": ZhihuJsonStoreImplement,
        "jsonl": ZhihuJsonlStoreImplement,
        "sqlite": ZhihuSqliteStoreImplement,
        "mongodb": ZhihuMongoStoreImplement,
        "excel": ZhihuExcelStoreImplement,
    }

    @staticmethod
    def create_store() -> AbstractStore:
        store_class = ZhihuStoreFactory.STORES.get(config.SAVE_DATA_OPTION)
        if not store_class:
            raise ValueError("[ZhihuStoreFactory.create_store] Invalid save option only supported csv or db or json or sqlite or mongodb or excel ...")
        return store_class()

async def batch_update_zhihu_contents(contents: List[ZhihuContent]):
    """
    Batch update Zhihu contents
    Args:
        contents:

    Returns:

    """
    if not contents:
        return

    for content_item in contents:
        await update_zhihu_content(content_item)

async def update_zhihu_content(content_item: ZhihuContent):
    """
    Update Zhihu content
    Args:
        content_item:

    Returns:

    """
    content_item.source_keyword = source_keyword_var.get()
    local_db_item = content_item.model_dump()
    local_db_item.update({"last_modify_ts": utils.get_current_timestamp()})
    utils.logger.info(f"[store.zhihu.update_zhihu_content] zhihu content: {local_db_item}")
    await ZhihuStoreFactory.create_store().store_content(local_db_item)


async def get_empty_content_text_contents() -> List[ZhihuContent]:
    """
    Get Zhihu answer/article rows whose content_text is empty.
    """
    async with get_session() as session:
        if session is None:
            raise ValueError(
                "[store.zhihu.get_empty_content_text_contents] Database save option is required"
            )

        stmt = (
            select(ZhihuContentModel)
            .where(
                ZhihuContentModel.content_type.in_(
                    [zhihu_constant.ANSWER_NAME, zhihu_constant.ARTICLE_NAME]
                )
            )
            .where(
                or_(
                    ZhihuContentModel.content_text.is_(None),
                    func.length(func.trim(ZhihuContentModel.content_text)) == 0,
                )
            )
            .where(ZhihuContentModel.content_url.is_not(None))
            .where(func.length(func.trim(ZhihuContentModel.content_url)) > 0)
            .order_by(ZhihuContentModel.id.asc())
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    def to_int(value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    return [
        ZhihuContent(
            content_id=row.content_id or "",
            content_type=row.content_type or "",
            content_text=row.content_text or "",
            content_url=row.content_url or "",
            question_id=row.question_id or "",
            title=row.title or "",
            desc=row.desc or "",
            created_time=to_int(row.created_time),
            updated_time=to_int(row.updated_time),
            voteup_count=row.voteup_count or 0,
            comment_count=row.comment_count or 0,
            source_keyword=row.source_keyword or "",
            user_id=row.user_id or "",
            user_link=row.user_link or "",
            user_nickname=row.user_nickname or "",
            user_avatar=row.user_avatar or "",
            user_url_token=row.user_url_token or "",
        )
        for row in rows
    ]



async def batch_update_zhihu_note_comments(comments: List[ZhihuComment]):
    """
    Batch update Zhihu content comments
    Args:
        comments:

    Returns:

    """
    if not comments:
        return

    for comment_item in comments:
        await update_zhihu_content_comment(comment_item)


async def update_zhihu_content_comment(comment_item: ZhihuComment):
    """
    Update Zhihu content comment
    Args:
        comment_item:

    Returns:

    """
    local_db_item = comment_item.model_dump()
    local_db_item.update({"last_modify_ts": utils.get_current_timestamp()})
    utils.logger.info(f"[store.zhihu.update_zhihu_note_comment] zhihu content comment:{local_db_item}")
    await ZhihuStoreFactory.create_store().store_comment(local_db_item)


async def save_creator(creator: ZhihuCreator):
    """
    Save Zhihu creator information
    Args:
        creator:

    Returns:

    """
    if not creator:
        return
    local_db_item = creator.model_dump()
    local_db_item.update({"last_modify_ts": utils.get_current_timestamp()})
    await ZhihuStoreFactory.create_store().store_creator(local_db_item)
