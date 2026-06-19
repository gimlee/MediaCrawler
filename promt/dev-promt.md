
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
1. 请把当前代码的远程仓库改为：
https://github.com/gimlee/MediaCrawler

2. 