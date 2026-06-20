# 断点续爬使用说明

MediaCrawler 默认开启断点续爬。断点状态独立保存在本地 SQLite 文件中，不依赖业务数据保存方式。

默认断点目录：

```text
data/resume/
```

同一条命令再次执行时，会自动使用相同的断点任务继续爬取。

## 常用命令

正常续爬：

```shell
uv run main.py --platform zhihu --lt qrcode --type search --save_data_option postgres
```

关闭断点续爬：

```shell
uv run main.py --platform zhihu --lt qrcode --type search --save_data_option postgres --no_resume
```

清空当前命令对应的断点并重新开始：

```shell
uv run main.py --platform zhihu --lt qrcode --type search --save_data_option postgres --reset_resume
```

指定固定断点任务 ID：

```shell
uv run main.py --platform zhihu --lt qrcode --type search --save_data_option postgres --resume_task_id zhihu_ai_task_001
```

固定任务 ID 适合长期任务。后续继续执行同一个 `--resume_task_id`，就会继续使用同一份断点。

## 断点粒度

第一版断点续爬支持三层状态：

- 搜索页进度：记录每个关键词的页码是否完成。
- 内容详情进度：记录每条内容是否已经写入详情。
- 评论任务进度：记录每条内容的评论任务是否完成。

注意：当前评论断点是“评论任务级”。如果程序中断在某条内容的评论分页中间，下次会重跑这条内容的评论任务。数据库存储通过内容 ID、评论 ID 做更新/去重，避免重复写入。

## 重新爬取并更新知乎空正文

知乎搜索列表接口经常只返回摘要，不返回完整回答正文。现在知乎 search 模式会在写入 `zhihu_content` 前，再进入回答/文章详情页补全文；只有拿到回答正文后才会标记该内容详情完成。

如果之前已经爬过知乎，并且 `zhihu_content.content_text` 有大量空值，建议清空当前断点后重跑同一批关键词：

```shell
uv run main.py --platform zhihu --lt qrcode --type search --save_data_option postgres --reset_resume
```

如果你想把这次重跑和旧断点完全隔离，可以指定新的任务 ID：

```shell
uv run main.py --platform zhihu --lt qrcode --type search --save_data_option postgres --resume_task_id zhihu_refill_content_text_001 --reset_resume
```

重跑时，PostgreSQL 存储会按 `content_id` 更新已有记录，因此新抓到的回答正文会覆盖原来为空的 `content_text`。

可以用下面的 SQL 检查修复效果：

```sql
select content_type,
       count(*) as total,
       sum(case when content_text is null or content_text = '' then 1 else 0 end) as empty_text
from zhihu_content
group by content_type;
```

视频类型 `zvideo` 没有回答正文，`content_text` 为空是正常情况。重点关注 `answer` 类型。
