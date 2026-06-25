import config
import pytest

from cmd_arg import parse_cmd


@pytest.mark.asyncio
async def test_juejin_detail_cli_normalizes_article_urls():
    await parse_cmd(
        [
            "--platform",
            "juejin",
            "--type",
            "detail",
            "--specified_id",
            "https://juejin.cn/post/6990140519342932004?utm_source=test,7000000000000000000",
        ]
    )

    assert config.JUEJIN_SPECIFIED_ID_LIST == [
        "6990140519342932004",
        "7000000000000000000",
    ]


@pytest.mark.asyncio
async def test_juejin_creator_cli_normalizes_creator_urls():
    await parse_cmd(
        [
            "--platform",
            "juejin",
            "--type",
            "creator",
            "--creator_id",
            "https://juejin.cn/user/3084299593/posts,1234567890",
        ]
    )

    assert config.JUEJIN_CREATOR_ID_LIST == ["3084299593", "1234567890"]
