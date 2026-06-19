
# 开发提示词

# P1
当前我在执行：
uv run main.py --platform xhs --lt qrcode --type search --save_data_option postgres
此时，我同时执行：
uv run main.py --platform zhihu --lt qrcode --type search --save_data_option postgres
就报错如下：
![alt text](image.png)
是不是一个程序执行的时候，进行锁库导致的。
应该只锁表就行了。


# P2
同一个关键字，我反复查询，怎么知道返回的结果有没有重复呢？
如果重复了，现在有办法去重，不写入DB吗？

# P3
1. 当前代码中不支持多个平台同时搜索，比如：
uv run main.py --platform dy --lt qrcode --type search
uv run main.py --platform ks --lt qrcode --type search
...
同时启动，对不同平台进行搜索。
请解决这种问题，可能是 CDP_DEBUG_PORT = 9222 这里配置单个端口导致。
具体问题你解决一下。至少要支持10个不同平台同时搜索。

2. 当前配置：CRAWLER_MAX_SLEEP_SEC = 10
这个停顿时间是固定10秒，请改成支持范围内的随机停顿时间，比如：
CRAWLER_MAX_SLEEP_SEC = [10, 30]
从10~30中随机选择一个数N，停顿N秒。

3. 另外，请确认，当前搜索知乎平台的时候，好像只爬取了问题(question_id)的第一个回答。（请确认）
要求至少爬取前10个（可配置）的回答，以及回答下的最多50个评论（可配置）
该配置只对知乎平台生效。


# P4
执行
uv run main.py --platform zhihu --lt qrcode --type search --save_data_option postgres
报错

# P5
当前获取知乎问题下多个回答的时候，你有进去问题页面，去获取多个回答吗？还是说只是获取到搜索的结果，默认只有一个回答，然后只是去尝试去或更多回答，不一定能够获取到？

# P6
![alt text](image-1.png)
修复该问题，网络超时不要中断程序。
当前的请求超时时间是多少？如果没有配置的地方，请增加配置，并默认设置45秒。
添加重试次数，默认3次（可以配置）
如果只是该条内容失败超过了3次，就跳过，记下失败次数。
如果失败次数（请求其他内容）超过10次(可以配置)，终止程序。


uv run main.py --platform dy --lt qrcode --type search --save_data_option postgres
uv run main.py --platform ks --lt qrcode --type search --save_data_option postgres
uv run main.py --platform tieba --lt qrcode --type search --save_data_option postgres
uv run main.py --platform wb --lt qrcode --type search --save_data_option postgres
uv run main.py --platform zhihu --lt qrcode --type search --save_data_option postgres
uv run main.py --platform bili --lt qrcode --type search --save_data_option postgres