# 考试日程日历订阅 — 设计

日期：2026-11-22

## 目标

从教务系统抓取本学期考试安排，生成 `output/考试.ics`，通过 GitHub Pages 提供手机日历订阅。所有者：`SynDecon/personal-examine`（public）。

考试页面字段：课程序号、课程名称、考试类别、考试日期、考试安排（时段）、考试地点、考场座位号、考试情况、其它说明。

## 数据源

- 教务入口：`http://39.164.230.243:91/eams/stdExamTable.action`（首页 iframe「我的考试」）
- 登录：与课表仓库相同的 CAS SPA（`http://39.164.230.243:9527`），`create_session()` 原样复用
- 学期：页面隐藏字段 `semester.id`（当前 322），每次运行动态解析，不写死
- 表格无分页；页面不含学号/姓名

## 结构

```
config/settings.yaml   # 时区、日历名
src/fetcher.py         # 登录 + fetch_exam_table()
src/parser.py          # 考试表格 → Exam 列表
src/ics_builder.py     # Exam → ICS
src/main.py            # 编排入口
tests/                 # 合成 HTML fixture，不含真实页面
.github/workflows/update.yml
```

## 抓取策略

`stdExamTable.action` 先 GET；若返回登录页 → `LoginError`；若含「考场座位号」表头 → 成功。否则解析 `semester.id` 后依次尝试 POST、带参 GET，均失败则抛出带脱敏诊断的 `FetchError`（只含状态码、路径、长度、行数、布尔标记）。

## 事件映射

| ICS 字段 | 来源 |
| --- | --- |
| SUMMARY | 课程名称 |
| DTSTART / DTEND | 考试日期 + `08:00~09:40`（兼容 `-`、`～`、`至`），TZID `Asia/Shanghai` |
| LOCATION | 考试地点，去掉「鹤壁工程技术学院」并压缩空白，如 `A310(1号教学楼)` |
| DESCRIPTION | `考场座位号：32`、`考试类别：期末考试`；座位为空写「待公布」；异常状态和说明追加 |
| UID | `sha1(课程序号|日期|开始时间)[:24]@hebi-exam` |

座位号和地点不进 UID：座位后公布或考场调整时，客户端按 UID 更新原事件，不会产生重复。

## 刷新与发布

- cron `0 18 * * *`（北京 02:00），workflow 第一步判断北京日期是否为 1 号或 15 号，否则跳过；`workflow_dispatch` 无条件执行
- 这样避开「每月 1/15」在二月、小月的 cron 陷阱
- 成功后用 Pages artifact 发布整个 `output/` 目录

## 失败策略

- 登录失败、页面结构不认识、解析到 0 场考试：退出非零，不覆盖已有 ICS，避免把线上日历清空
- 任何异常信息不得包含学号（URL 的 `ids` 参数）或密码

## 测试

- fixture 按真实表格结构手写，不使用导出的真实页面
- 覆盖：正常行、座位为空、时段分隔符兼容、空表、缺表头报错、UID 在座位变化时保持稳定、时区偏移

## 一次性手动设置

1. 仓库 Secrets：`SCHOOL_USER`、`SCHOOL_PASS`（用户本人填写）
2. Pages：Source 选择 GitHub Actions