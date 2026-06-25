from media_platform.juejin.field import CommentSort, CreatorArticleSort
from media_platform.juejin.help import JuejinExtractor


def test_juejin_sort_enums_expose_all_supported_values():
    assert CreatorArticleSort.TIME.value == 1
    assert CreatorArticleSort.HOT.value == 2
    assert CommentSort.DEFAULT.value == 0
    assert CommentSort.HOT.value == 1
    assert CommentSort.TIME.value == 2


def test_extract_juejin_comment_preserves_parent_id():
    comments = JuejinExtractor().extract_comments(
        [
            {
                "comment_info": {
                    "comment_id": "child-1",
                    "reply_id": "root-1",
                    "comment_content": "<p>reply</p>",
                    "ctime": "100",
                    "digg_count": 3,
                    "reply_count": 0,
                },
                "user_info": {"user_id": "u1", "user_name": "Alice"},
            }
        ]
    )

    assert comments[0].comment_id == "child-1"
    assert comments[0].parent_comment_id == "root-1"
    assert comments[0].content == "reply"


def test_extract_juejin_comment_supports_parent_id_fallbacks():
    comments = JuejinExtractor().extract_comments(
        [
            {
                "comment_info": {
                    "comment_id": "child-1",
                    "reply_to_comment_id": 123,
                    "comment_content": "reply",
                }
            },
            {
                "comment_info": {
                    "comment_id": "child-2",
                    "parent_comment_id": "root-2",
                    "comment_content": "reply",
                }
            },
        ]
    )

    assert [comment.parent_comment_id for comment in comments] == ["123", "root-2"]


def test_extract_juejin_reply_uses_real_reply_info_shape():
    comments = JuejinExtractor().extract_comments(
        [
            {
                "reply_info": {
                    "reply_id": "child-1",
                    "reply_comment_id": "root-1",
                    "reply_content": "<p>child reply</p>",
                    "ctime": "101",
                    "digg_count": 2,
                },
                "user_info": {"user_id": "u2", "user_name": "Bob"},
            }
        ]
    )

    assert len(comments) == 1
    assert comments[0].comment_id == "child-1"
    assert comments[0].parent_comment_id == "root-1"
    assert comments[0].content == "child reply"
    assert comments[0].sub_comment_count == 0
