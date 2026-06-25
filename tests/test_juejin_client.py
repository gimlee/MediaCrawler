import config
import pytest

from media_platform.juejin.client import JuejinClient
from model.m_juejin import JuejinContent


def make_client() -> JuejinClient:
    return JuejinClient(headers={}, cookie_dict={})


class FakePlaywrightPage:
    def __init__(self, article_data):
        self.article_data = article_data
        self.goto_calls = []
        self.evaluate_calls = []

    async def goto(self, url, wait_until=None):
        self.goto_calls.append((url, wait_until))

    async def evaluate(self, script):
        self.evaluate_calls.append(script)
        return self.article_data


@pytest.mark.asyncio
async def test_get_article_info_fills_missing_fields_from_dom(monkeypatch):
    page = FakePlaywrightPage(
        {
            "content_text": "Rendered article body",
            "title": "Rendered article title",
            "desc": "Rendered article description",
        }
    )
    client = JuejinClient(headers={}, cookie_dict={}, playwright_page=page)

    async def fake_detail_api(_article_id):
        return JuejinContent(
            content_id="6990140519342932004",
            content_text=" ",
            title=" ",
            desc=" ",
        )

    monkeypatch.setattr(client, "_get_article_detail_api", fake_detail_api)
    monkeypatch.setattr("media_platform.juejin.client.asyncio.sleep", _no_sleep)

    detail = await client.get_article_info("6990140519342932004")

    assert detail.content_text == "Rendered article body"
    assert detail.title == "Rendered article title"
    assert detail.desc == "Rendered article description"
    assert len(page.evaluate_calls) == 1
    assert "article-title" in page.evaluate_calls[0]
    assert 'meta[name="description"]' in page.evaluate_calls[0]


@pytest.mark.asyncio
async def test_get_article_info_preserves_api_fields_when_dom_has_values(monkeypatch):
    page = FakePlaywrightPage(
        {
            "content_text": "Rendered article body",
            "title": "Rendered article title",
            "desc": "Rendered article description",
        }
    )
    client = JuejinClient(headers={}, cookie_dict={}, playwright_page=page)

    async def fake_detail_api(_article_id):
        return JuejinContent(
            content_id="6990140519342932004",
            content_text="API article body",
            title="API article title",
            desc="API article description",
        )

    monkeypatch.setattr(client, "_get_article_detail_api", fake_detail_api)
    monkeypatch.setattr("media_platform.juejin.client.asyncio.sleep", _no_sleep)

    detail = await client.get_article_info("6990140519342932004")

    assert detail.content_text == "API article body"
    assert detail.title == "API article title"
    assert detail.desc == "API article description"


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

    assert "/interact_api/v1/reply/list?" in captured["url"]
    assert captured["payload"] == {
        "comment_id": "root-1",
        "item_id": "article-1",
        "item_type": 2,
        "cursor": "20",
        "limit": 10,
        "client_type": 2608,
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
                    "reply_info": {
                        "reply_id": f"child-{page_number}",
                        "reply_comment_id": "root-1",
                        "reply_content": "child",
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
                    "reply_info": {
                        "reply_id": "child-1",
                        "reply_comment_id": "root-1",
                        "reply_content": "child",
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


@pytest.mark.asyncio
async def test_juejin_uses_embedded_replies_and_deduplicates_full_reply_list(
    monkeypatch,
):
    client = make_client()
    monkeypatch.setattr(config, "ENABLE_GET_SUB_COMMENTS", True)

    async def fake_root_comments(*args, **kwargs):
        return {
            "data": [
                {
                    "comment_info": {
                        "comment_id": "root-1",
                        "comment_content": "root",
                        "reply_count": 3,
                    },
                    "reply_infos": [
                        {
                            "reply_info": {
                                "reply_id": "child-1",
                                "reply_comment_id": "root-1",
                                "reply_content": "embedded",
                            }
                        }
                    ],
                }
            ],
            "cursor": "1",
            "has_more": False,
        }

    async def fake_child_comments(*args, **kwargs):
        return {
            "data": [
                {
                    "reply_info": {
                        "reply_id": "child-1",
                        "reply_comment_id": "root-1",
                        "reply_content": "duplicate",
                    }
                },
                {
                    "reply_info": {
                        "reply_id": "child-2",
                        "reply_comment_id": "root-1",
                        "reply_content": "new child",
                    }
                },
            ],
            "cursor": "2",
            "has_more": False,
        }

    monkeypatch.setattr(client, "get_root_comments", fake_root_comments)
    monkeypatch.setattr(client, "get_child_comments", fake_child_comments)

    comments = await client.get_note_all_comments(
        JuejinContent(content_id="article-1")
    )

    assert [comment.comment_id for comment in comments] == [
        "root-1",
        "child-1",
        "child-2",
    ]


async def _no_sleep(_):
    return 0.0
