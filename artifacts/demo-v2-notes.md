# 浏览器完整流程录屏 V2

录制日期：2026-09-16（Asia/Shanghai）。

文件：[mr-hcp-core-flow-demo-720p.mp4](mr-hcp-core-flow-demo-720p.mp4)，H.264，1512 × 948，599.920 秒，约 22 MiB，无音轨。

按用户要求沿用远程仓库原有文件名并替换旧录屏；只重命名，不重新压缩。文件名中的 `720p` 是历史命名，实际分辨率为 1512 × 948。

## 本次优化

- 使用用户最大化后的独立 Chrome 窗口，单独采集浏览器，不录 Codex 主界面、桌面或桌面浮窗。
- 文字和坐标按字符输入，在下拉选择、弹窗和结果展示之间保留阅读停顿。
- 所有写操作通过真实网页和本地 API 完成；没有 mock、修改服务器时钟、回写签到时间或降低合规阈值。
- 正常拜访签到后，穿插演示异常流程和查询功能，实际超过五分钟后才签退。

## 覆盖内容

| 功能 | 实际演示结果 |
| --- | --- |
| 创建计划 | 必填字段提示、MR 选择、医院—科室—医生联动、日期、多目标产品、成功跳转详情 |
| 现场执行 | 手工坐标输入、服务器签到/签退时间、状态变化、服务端时长和距离 |
| 正常拜访 | 348.340614 秒，签到和签退距离均为 0 米，NORMAL，无 finding |
| 异常拜访 | 17.569895 秒，DURATION_TOO_SHORT、CHECKIN_TOO_FAR、CHECKOUT_TOO_FAR 同时保存 |
| 报告 | 谈话要点、医生反馈、备注、实际产品、各产品学术内容、首次提交、更新及详情查看 |
| 派发资料 | 正常拜访派发“合规学术文献摘要（演示）”2 份；异常拜访演示无派发资料 |
| 列表 | 状态筛选、计划日期范围筛选、重置、每页数量切换、进入详情 |
| 月度看板 | 柱状图和明细表，待评估、正常和异常分类，多产品分别计数，月份选择、无数据空状态 |
| 系统状态 | 健康检查及重新检查，结果为 ok |

## 可复查的演示记录

- 正常流程工作流 ID：`1cb3f03c-9dfb-47f4-863d-c78fe5b30c16`，最终 REPORTED / NORMAL。
  - 签到：`2026-09-16T12:35:16.604563Z`。
  - 签退：`2026-09-16T12:41:04.945177Z`。
  - 实际沟通：心血管产品 A、代谢产品 B。
- 异常流程工作流 ID：`fedaacce-5fcc-4c81-91d1-70ca871a155f`，最终 REPORTED / ABNORMAL。
  - 签到坐标：90.000000, 121.453720；距离 6538520.906662 米。
  - 签退坐标：31.207750, 121.453720；距离 1111.950802 米。
  - 报告更新后，三个 finding 及原始现场事实仍保留。
- 2026-09 看板最终结果（包含已有演示数据）：
  - 心血管产品 A：总数 6、正常 2、异常 4、待评估 0。
  - 代谢产品 B：总数 4、正常 1、异常 3、待评估 0。

## 录制阶段实际检查与命令

录制程序和原始素材放在 `/tmp`，未加入业务代码。使用 ScreenCaptureKit 的独立窗口采集与 AVAssetWriter；程序完成状态为 2（completed）。

```sh
/tmp/window-recorder 169231 /tmp/mr-hcp-full-demo-raw.mov 1200
avconvert --source /tmp/mr-hcp-full-demo-raw.mov --output artifacts/mr-hcp-full-browser-demo-v2.mp4 --preset PresetPassthrough
avmediainfo artifacts/mr-hcp-full-browser-demo-v2.mp4
/tmp/extract-video-frames /tmp/mr-hcp-full-demo-raw.mov /tmp/mr-hcp-full-demo-qa 5 75 100 215 280 335 400 445 480 530 575 595
curl --noproxy '*' -fsS http://127.0.0.1:8000/health
curl --noproxy '*' -fsS http://127.0.0.1:8000/api/visits/1cb3f03c-9dfb-47f4-863d-c78fe5b30c16
curl --noproxy '*' -fsS http://127.0.0.1:8000/api/visits/fedaacce-5fcc-4c81-91d1-70ca871a155f
curl --noproxy '*' -fsS 'http://127.0.0.1:8000/api/dashboard/monthly-visits-by-product?month=2026-09'
```

1200 秒是录制上限，流程完成后通过停止标记正常结束，实际视频约十分钟。导出命令成功，媒体检查为 0 error；关键帧确认展示真实浏览器内容、输入过程、异常明细和多产品报告，没有黑屏或 Codex 主界面。

## 说明与覆盖边界

- 录制前 Chrome 重启及窗口定位问题已处理，预检素材没有混入正式视频。
- 输入纬度 91 时，前端数字控件在失焦后自动收敛到上限 90；因此这段展示的是坐标边界及超距异常，不能宣称验证了后端 INVALID_COORDINATES 错误。
- 期间存在下拉框/滚动尚未稳定引起的操作定位偏移，已重新选择并核对保存结果；未据此修改应用代码或业务规则。
- 当前只有 8 条记录，展示了分页大小切换，没有产生多页数据来演示第二页。
- 视频是关键用户流程演示，不替代并发签到、数据库事务回滚、500 米精确边界等自动化测试。
- 本次只更新录屏交付物及说明，没有修改业务源码，未运行 lint、build 或 pytest。被替换的旧版视频可从 Git 历史恢复；其他录屏素材和用户已有 PDF 不在本次提交范围。

建议提交信息：`docs: add maximized browser demo covering normal and abnormal workflows`。
