from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import config
from database.models import Base, JuejinComment, JuejinContent, JuejinCreator
from store.juejin import JuejinStoreFactory
from store.juejin import _store_impl as juejin_store_impl
from store.juejin._store_impl import (
    JuejinCsvStoreImplement,
    JuejinDbStoreImplement,
    JuejinExcelStoreImplement,
    JuejinJsonStoreImplement,
    JuejinJsonlStoreImplement,
    JuejinMongoStoreImplement,
    JuejinSqliteStoreImplement,
)


def test_juejin_store_factory_registers_all_existing_options():
    assert JuejinStoreFactory.STORES == {
        "csv": JuejinCsvStoreImplement,
        "db": JuejinDbStoreImplement,
        "postgres": JuejinDbStoreImplement,
        "json": JuejinJsonStoreImplement,
        "jsonl": JuejinJsonlStoreImplement,
        "sqlite": JuejinSqliteStoreImplement,
        "mongodb": JuejinMongoStoreImplement,
        "excel": JuejinExcelStoreImplement,
    }


def test_juejin_store_factory_error_lists_supported_options(monkeypatch):
    monkeypatch.setattr(config, "SAVE_DATA_OPTION", "unsupported")

    with pytest.raises(ValueError) as exc_info:
        JuejinStoreFactory.create_store()

    message = str(exc_info.value)
    for option in sorted(JuejinStoreFactory.STORES):
        assert option in message


def test_juejin_business_ids_are_unique_and_required():
    for column in (
        JuejinContent.__table__.c.content_id,
        JuejinComment.__table__.c.comment_id,
        JuejinCreator.__table__.c.user_id,
    ):
        assert column.unique is True
        assert column.nullable is False


@pytest.mark.asyncio
async def test_juejin_database_upserts_are_idempotent(tmp_path, monkeypatch):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'juejin-store.db'}"
    )
    session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    @asynccontextmanager
    async def isolated_get_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(juejin_store_impl, "get_session", isolated_get_session)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=[
                        JuejinContent.__table__,
                        JuejinComment.__table__,
                        JuejinCreator.__table__,
                    ],
                )
            )

        store = JuejinDbStoreImplement()
        await store.store_content(
            {"content_id": "content-1", "title": "first title"}
        )
        await store.store_content(
            {"content_id": "content-1", "title": "updated title"}
        )
        await store.store_comment(
            {
                "comment_id": "comment-1",
                "content_id": "content-1",
                "content": "first comment",
            }
        )
        await store.store_comment(
            {
                "comment_id": "comment-1",
                "content_id": "content-1",
                "content": "updated comment",
            }
        )
        await store.store_creator(
            {"user_id": "creator-1", "user_nickname": "first creator"}
        )
        await store.store_creator(
            {"user_id": "creator-1", "user_nickname": "updated creator"}
        )

        async with session_factory() as session:
            content_count = await session.scalar(
                select(func.count()).select_from(JuejinContent)
            )
            comment_count = await session.scalar(
                select(func.count()).select_from(JuejinComment)
            )
            creator_count = await session.scalar(
                select(func.count()).select_from(JuejinCreator)
            )
            content_title = await session.scalar(
                select(JuejinContent.title).where(
                    JuejinContent.content_id == "content-1"
                )
            )
            comment_text = await session.scalar(
                select(JuejinComment.content).where(
                    JuejinComment.comment_id == "comment-1"
                )
            )
            creator_name = await session.scalar(
                select(JuejinCreator.user_nickname).where(
                    JuejinCreator.user_id == "creator-1"
                )
            )

        assert content_count == 1
        assert comment_count == 1
        assert creator_count == 1
        assert content_title == "updated title"
        assert comment_text == "updated comment"
        assert creator_name == "updated creator"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "payload", "expected_message"),
    [
        ("store_content", {}, "Juejin content_id is required"),
        ("store_content", {"content_id": "   "}, "Juejin content_id is required"),
        ("store_comment", {}, "Juejin comment_id is required"),
        ("store_comment", {"comment_id": "   "}, "Juejin comment_id is required"),
        ("store_creator", {}, "Juejin user_id is required"),
        ("store_creator", {"user_id": "   "}, "Juejin user_id is required"),
    ],
)
async def test_juejin_database_rejects_missing_business_ids(
    method_name,
    payload,
    expected_message,
):
    store = JuejinDbStoreImplement()

    with pytest.raises(ValueError, match=expected_message):
        await getattr(store, method_name)(payload)
