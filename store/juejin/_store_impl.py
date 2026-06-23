# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/store/juejin/_store_impl.py
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
# @Desc    : Juejin storage implementation class
import json
from typing import Dict

from sqlalchemy import String, Text, select

from base.base_crawler import AbstractStore
from database.db_session import get_session
from database.models import JuejinComment, JuejinContent, JuejinCreator
from database.mongodb_store_base import MongoDBStoreBase
from tools import utils
from tools.async_file_writer import AsyncFileWriter
from var import crawler_type_var


class JuejinCsvStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="juejin", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        """Juejin content CSV storage implementation."""
        await self.writer.write_to_csv(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        """Juejin comment CSV storage implementation."""
        await self.writer.write_to_csv(item_type="comments", item=comment_item)

    async def store_creator(self, creator: Dict):
        """Juejin creator CSV storage implementation."""
        await self.writer.write_to_csv(item_type="creators", item=creator)


class JuejinDbStoreImplement(AbstractStore):
    @staticmethod
    def _stringify_text_value(value):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @classmethod
    def _normalize_item_for_model(cls, model, item: Dict) -> Dict:
        normalized_item = dict(item)
        for column in model.__table__.columns:
            if column.name not in normalized_item:
                continue
            if isinstance(column.type, (String, Text)):
                normalized_item[column.name] = cls._stringify_text_value(
                    normalized_item[column.name]
                )
        return normalized_item

    async def store_content(self, content_item: Dict):
        """Juejin content DB storage implementation."""
        content_item = self._normalize_item_for_model(JuejinContent, content_item)
        content_id = content_item.get("content_id")
        async with get_session() as session:
            stmt = select(JuejinContent).where(JuejinContent.content_id == content_id)
            result = await session.execute(stmt)
            existing_content = result.scalars().first()
            if existing_content:
                for key, value in content_item.items():
                    if hasattr(existing_content, key):
                        setattr(existing_content, key, value)
            else:
                if "add_ts" not in content_item:
                    content_item["add_ts"] = utils.get_current_timestamp()
                new_content = JuejinContent(**content_item)
                session.add(new_content)
            await session.commit()

    async def store_comment(self, comment_item: Dict):
        """Juejin comment DB storage implementation."""
        comment_item = self._normalize_item_for_model(JuejinComment, comment_item)
        comment_id = comment_item.get("comment_id")
        async with get_session() as session:
            stmt = select(JuejinComment).where(JuejinComment.comment_id == comment_id)
            result = await session.execute(stmt)
            existing_comment = result.scalars().first()
            if existing_comment:
                for key, value in comment_item.items():
                    if hasattr(existing_comment, key):
                        setattr(existing_comment, key, value)
            else:
                if "add_ts" not in comment_item:
                    comment_item["add_ts"] = utils.get_current_timestamp()
                new_comment = JuejinComment(**comment_item)
                session.add(new_comment)
            await session.commit()

    async def store_creator(self, creator: Dict):
        """Juejin creator DB storage implementation."""
        creator = self._normalize_item_for_model(JuejinCreator, creator)
        user_id = creator.get("user_id")
        async with get_session() as session:
            stmt = select(JuejinCreator).where(JuejinCreator.user_id == user_id)
            result = await session.execute(stmt)
            existing_creator = result.scalars().first()
            if existing_creator:
                for key, value in creator.items():
                    if hasattr(existing_creator, key):
                        setattr(existing_creator, key, value)
            else:
                if "add_ts" not in creator:
                    creator["add_ts"] = utils.get_current_timestamp()
                new_creator = JuejinCreator(**creator)
                session.add(new_creator)
            await session.commit()


class JuejinJsonStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="juejin", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        """Content JSON storage implementation."""
        await self.writer.write_single_item_to_json(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        """Comment JSON storage implementation."""
        await self.writer.write_single_item_to_json(item_type="comments", item=comment_item)

    async def store_creator(self, creator: Dict):
        """Creator JSON storage implementation."""
        await self.writer.write_single_item_to_json(item_type="creators", item=creator)


class JuejinJsonlStoreImplement(AbstractStore):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.writer = AsyncFileWriter(platform="juejin", crawler_type=crawler_type_var.get())

    async def store_content(self, content_item: Dict):
        await self.writer.write_to_jsonl(item_type="contents", item=content_item)

    async def store_comment(self, comment_item: Dict):
        await self.writer.write_to_jsonl(item_type="comments", item=comment_item)

    async def store_creator(self, creator: Dict):
        await self.writer.write_to_jsonl(item_type="creators", item=creator)


class JuejinSqliteStoreImplement(JuejinDbStoreImplement):
    """Juejin content SQLite storage implementation."""
    pass


class JuejinMongoStoreImplement(AbstractStore):
    """Juejin MongoDB storage implementation."""

    def __init__(self):
        self.mongo_store = MongoDBStoreBase(collection_prefix="juejin")

    async def store_content(self, content_item: Dict):
        """Store content to MongoDB."""
        content_id = content_item.get("content_id")
        if not content_id:
            return

        await self.mongo_store.save_or_update(
            collection_suffix="contents",
            query={"content_id": content_id},
            data=content_item,
        )
        utils.logger.info(f"[JuejinMongoStoreImplement.store_content] Saved content {content_id} to MongoDB")

    async def store_comment(self, comment_item: Dict):
        """Store comment to MongoDB."""
        comment_id = comment_item.get("comment_id")
        if not comment_id:
            return

        await self.mongo_store.save_or_update(
            collection_suffix="comments",
            query={"comment_id": comment_id},
            data=comment_item,
        )
        utils.logger.info(f"[JuejinMongoStoreImplement.store_comment] Saved comment {comment_id} to MongoDB")

    async def store_creator(self, creator_item: Dict):
        """Store creator information to MongoDB."""
        user_id = creator_item.get("user_id")
        if not user_id:
            return

        await self.mongo_store.save_or_update(
            collection_suffix="creators",
            query={"user_id": user_id},
            data=creator_item,
        )
        utils.logger.info(f"[JuejinMongoStoreImplement.store_creator] Saved creator {user_id} to MongoDB")


class JuejinExcelStoreImplement:
    """Juejin Excel storage implementation - Global singleton"""

    def __new__(cls, *args, **kwargs):
        from store.excel_store_base import ExcelStoreBase

        return ExcelStoreBase.get_instance(
            platform="juejin",
            crawler_type=crawler_type_var.get(),
        )
