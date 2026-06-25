import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

import config
from database.db_session import create_tables, get_session
from database.models import JuejinComment, JuejinContent, JuejinCreator
from store.juejin._store_impl import JuejinDbStoreImplement


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 to use local PostgreSQL",
)


@pytest.mark.asyncio
async def test_juejin_postgres_upserts(monkeypatch):
    unique_suffix = uuid4().hex
    content_id = f"integration-content-{unique_suffix}"
    comment_id = f"integration-comment-{unique_suffix}"
    creator_id = f"integration-creator-{unique_suffix}"

    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "postgres")
    await create_tables("postgres")

    store = JuejinDbStoreImplement()
    try:
        await store.store_content(
            {"content_id": content_id, "title": "first title"}
        )
        await store.store_content(
            {"content_id": content_id, "title": "updated title"}
        )
        await store.store_comment(
            {
                "comment_id": comment_id,
                "content_id": content_id,
                "content": "integration comment",
            }
        )
        await store.store_creator(
            {
                "user_id": creator_id,
                "user_nickname": "integration creator",
            }
        )

        async with get_session() as session:
            content_count = await session.scalar(
                select(func.count())
                .select_from(JuejinContent)
                .where(JuejinContent.content_id == content_id)
            )
            content_title = await session.scalar(
                select(JuejinContent.title).where(
                    JuejinContent.content_id == content_id
                )
            )
            comment_count = await session.scalar(
                select(func.count())
                .select_from(JuejinComment)
                .where(JuejinComment.comment_id == comment_id)
            )
            creator_count = await session.scalar(
                select(func.count())
                .select_from(JuejinCreator)
                .where(JuejinCreator.user_id == creator_id)
            )

        assert content_count == 1
        assert content_title == "updated title"
        assert comment_count == 1
        assert creator_count == 1
    finally:
        async with get_session() as session:
            await session.execute(
                delete(JuejinComment).where(
                    JuejinComment.comment_id == comment_id
                )
            )
            await session.execute(
                delete(JuejinContent).where(
                    JuejinContent.content_id == content_id
                )
            )
            await session.execute(
                delete(JuejinCreator).where(
                    JuejinCreator.user_id == creator_id
                )
            )
