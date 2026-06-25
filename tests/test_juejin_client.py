import config
import pytest

from media_platform.juejin.client import JuejinClient
from model.m_juejin import JuejinContent


def make_client() -> JuejinClient:
    return JuejinClient(headers={}, cookie_dict={})


@pytest.mark.asyncio
async def test_get_child_comments_uses_reply_list_payload(monkeypatch):
    client = make_client()
    captured = {}

    async def fake_post(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {"data": [], "cursor": "0", "has_more": False}

    monkeypatch.setattr(client, "_post", fake_post)

    await client.get_child_comments("article-1", "root-1", cursor="20", limit=10)

    assert "/interact_api/v1/comment/reply_list?" in captured["url"]
    assert captured["payload"] == {
        "cursor": "20",
        "item_id": "article-1",
        "item_type": 2,
        "comment_id": "root-1",
        "client_type": 2608,
        "limit": 10,
    }


@pytest.mark.asyncio
async def test_juejin_comment_limit_applies_to_root_comments(monkeypatch):
    client = make_client()
    monkeypatch.setattr(config, "ENABLE_GET_SUB_COMMENTS", False)
    pages = iter(
        [
            {
                "data": [
                    {
                        "comment_info": {
                            "comment_id": str(index),
                            "comment_content": "x",
                        }
                    }
                    for index in range(20)
                ],
                "cursor": "20",
                "has_more": True,
            },
            {
                "data": [
                    {
                        "comment_info": {
                            "comment_id": "20",
                            "comment_content": "x",
                        }
                    }
                ],
                "cursor": "21",
                "has_more": False,
            },
        ]
    )

    async def fake_root_comments(*args, **kwargs):
        return next(pages)

    monkeypatch.setattr(client, "get_root_comments", fake_root_comments)

    comments = await client.get_note_all_comments(
        JuejinContent(content_id="article-1"), max_count=10
    )

    assert len(comments) == 10
    assert [comment.comment_id for comment in comments] == [
        str(index) for index in range(10)
    ]


@pytest.mark.asyncio
async def test_juejin_fetches_paginated_child_comments_when_enabled(monkeypatch):
    client = make_client()
    monkeypatch.setattr(config, "ENABLE_GET_SUB_COMMENTS", True)
    child_cursors = []

    async def fake_root_comments(*args, **kwargs):
        return {
            "data": [
                {
                    "comment_info": {
                        "comment_id": "root-1",
                        "comment_content": "root",
                        "reply_count": 2,
                    }
                }
            ],
            "cursor": "1",
            "has_more": False,
        }

    async def fake_child_comments(article_id, comment_id, cursor="0", limit=20):
        child_cursors.append(cursor)
        page_number = len(child_cursors)
        return {
            "data": [
                {
                    "comment_info": {
                        "comment_id": f"child-{page_number}",
                        "reply_id": "root-1",
                        "comment_content": "child",
                    }
                }
            ],
            "cursor": str(page_number),
            "has_more": page_number == 1,
        }

    monkeypatch.setattr(client, "get_root_comments", fake_root_comments)
    monkeypatch.setattr(client, "get_child_comments", fake_child_comments)
    monkeypatch.setattr("media_platform.juejin.client.utils.crawler_sleep", _no_sleep)

    comments = await client.get_note_all_comments(
        JuejinContent(content_id="article-1"), crawl_interval=0
    )

    assert child_cursors == ["0", "1"]
    assert [item.comment_id for item in comments] == [
        "root-1",
        "child-1",
        "child-2",
    ]
    assert [item.parent_comment_id for item in comments[1:]] == [
        "root-1",
        "root-1",
    ]
    assert all(item.content_id == "article-1" for item in comments)


@pytest.mark.asyncio
async def test_juejin_root_limit_does_not_count_child_comments(monkeypatch):
    client = make_client()
    monkeypatch.setattr(config, "ENABLE_GET_SUB_COMMENTS", True)

    async def fake_root_comments(*args, **kwargs):
        return {
            "data": [
                {
                    "comment_info": {
                        "comment_id": "root-1",
                        "comment_content": "root",
                        "reply_count": 1,
                    }
                },
                {
                    "comment_info": {
                        "comment_id": "root-2",
                        "comment_content": "root",
                        "reply_count": 0,
                    }
                },
            ],
            "cursor": "2",
            "has_more": False,
        }

    async def fake_child_comments(*args, **kwargs):
        return {
            "data": [
                {
                    "comment_info": {
                        "comment_id": "child-1",
                        "comment_content": "child",
                    }
                }
            ],
            "cursor": "1",
            "has_more": False,
        }

    monkeypatch.setattr(client, "get_root_comments", fake_root_comments)
    monkeypatch.setattr(client, "get_child_comments", fake_child_comments)

    comments = await client.get_note_all_comments(
        JuejinContent(content_id="article-1"), max_count=1
    )

    assert [item.comment_id for item in comments] == ["root-1", "child-1"]
    assert comments[1].parent_comment_id == "root-1"


async def _no_sleep(_):
    return 0.0
