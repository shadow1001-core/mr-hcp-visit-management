# 按产品统计月度拜访次数设计

## 1. 目标与范围

本文设计 `GET /api/dashboard/monthly-visits-by-product` 的后端统计查询。接口按配置的业务时区，
统计指定自然月内已经签到的实际拜访，并按产品返回总拜访数、正常数、异常数和待判定数。

本设计只定义查询口径、分层职责和建议 SQL，不实现 API、Repository 或前端代码。MVP 不引入物化
视图、缓存、分析数据库，也不允许前端下载全部拜访后自行聚合。

核心决定：

- 月份使用严格的 `YYYY-MM` 格式；统计依据是 `visits.check_in_at`，不是计划或签退时间。
- 产品关系使用签到时固化的 `visit_products`，不是计划产品或报告中的沟通明细。
- 已签到但未签退且尚无 finding 的拜访计入 `pending_count`；已有签到超距 finding 时计入异常数。
- 异常判断采用 `EXISTS compliance_findings`，避免多个 finding 放大计数。
- 推荐查询形状能保证每个“产品 + 拜访”只有一行，因此聚合可使用 `COUNT(*)`；不依赖
  `COUNT(DISTINCT visit_id)` 掩盖错误 JOIN。
- MVP 默认不返回当月计数为零的产品，与现有 API 契约一致。

## 2. 统计口径

### 2.1 纳入范围

一个实际拜访满足以下条件时计入指定月份：

```text
check_in_at >= start_utc
AND check_in_at < end_utc
```

其中 `[start_utc, end_utc)` 是指定业务自然月在业务时区中的起止边界转换为 UTC 后得到的半开
区间。数据库中的 `visits` 只在签到成功后创建，因此该条件自然排除尚未签到的计划。

状态口径为：

| 实际拜访情况 | 计入 `total_count` | 计入 `normal_count` | 计入 `abnormal_count` | 计入 `pending_count` |
| --- | ---: | ---: | ---: | ---: |
| `CHECKED_IN`，尚未签退且无 finding | 是 | 否 | 否 | 是 |
| `CHECKED_IN`，存在签到超距 finding | 是 | 否 | 是 | 否 |
| `CHECKED_OUT`，无 finding | 是 | 是 | 否 | 否 |
| `REPORTED`，无 finding | 是 | 是 | 否 | 否 |
| `CHECKED_OUT` 或 `REPORTED`，至少一个 finding | 是 | 否 | 是 | 否 |

四个计数应始终满足：

```text
total_count = normal_count + abnormal_count + pending_count
```

用户要求的三个主要指标为 `total_count`、`normal_count` 和 `abnormal_count`。仍建议响应中增加
`pending_count`：已签到未签退的拜访已经属于总数，但完整合规结论尚未产生，将其算作“正常”会
造成误导；如果只返回三个指标，调用方只能看到总数大于正常数与异常数之和，却无法解释差值。

### 2.2 异常与正常判定

当前 Schema 不持久化单独的 `compliance_status` 字段；看板根据签退事实和 finding 是否存在派生
分类，避免冗余状态与明细不一致：

- 待判定：`check_out_at IS NULL` 且不存在 `compliance_findings`。
- 异常：至少存在一条 `compliance_findings`；签到超距可以在签退前确定。
- 正常：`check_out_at IS NOT NULL` 且不存在 `compliance_findings`。

未签退且存在签到 finding 的拜访已能确定“至少异常”，因此计入异常数；这不表示最终 finding
集合已经完整，停留时长和签退位置仍需在签退时评估。

## 3. 产品统计来源

统计使用 `visit_products`，理由如下：

| 候选来源 | 是否采用 | 原因 |
| --- | --- | --- |
| `visit_plan_products` | 否 | 表示计划目标，会包含未签到计划；计划内容也不是已经发生的实际拜访事实 |
| `visit_products` | 是 | 签到时从计划目标固化，代表已发生拜访关联的产品；复合主键保证同一拜访同一产品最多一行 |
| `academic_detailing_records` | 否 | 只有提交报告后才存在；用它会漏掉仍处于 `CHECKED_IN` 或 `CHECKED_OUT` 的拜访 |

报告中的实际沟通产品在语义上比计划目标更接近“确实沟通了什么”，但它无法同时满足当前规则
“所有已签到拜访都计入”。因此 MVP 使用 `visit_products`。如果未来业务将口径改为“只统计已确认
实际沟通的产品”，应明确改用 `academic_detailing_records`，并接受未报告拜访无法按实际沟通产品
归类，或者新增现场沟通产品的独立采集时点；不能在同一指标中混用两套来源。

分组键始终是稳定的 `product_id`。响应中的名称和编码默认读取当前 `products` 主数据，以保证每个
产品只返回一行；`visit_products` 中的快照用于历史审计，不用于拆分统计分组。若将来需要按拜访
发生时的产品名称展示，应另行定义展示规则，避免一次改名把同一产品拆成多行。

## 4. 业务月份与时区

### 4.1 参数校验

- `month` 必填，严格匹配 `^\d{4}-(0[1-9]|1[0-2])$`，并能构造有效年月。
- 非法值返回 `422 INVALID_MONTH`，例如 `2026-9`、`2026-00`、`2026-13`。
- 业务时区来自服务端配置，默认 `Asia/Shanghai`；客户端不得覆盖。
- 配置必须是有效的 IANA 时区名称，应用启动时校验，配置错误应使启动失败，而不是静默回退。

### 4.2 UTC 边界计算

Service 层按以下步骤计算范围：

1. 在业务时区中构造该月第一天 `00:00:00`。
2. 使用日历运算构造下个月第一天 `00:00:00`，不能用固定天数相加。
3. 将两个带时区时间点分别转换为 UTC。
4. 把 UTC 边界作为查询参数传给 Repository。

例如业务时区为 `Asia/Shanghai` 时，`2026-09` 对应：

```text
start_utc = 2026-08-31T16:00:00Z
end_utc   = 2026-09-30T16:00:00Z
```

半开区间保证月初边界被纳入、下个月月初边界不被纳入，并避免 `23:59:59.999999` 之类的不可靠
上界。边界先在业务时区中做日历计算，再转换 UTC，这也适用于有夏令时的 IANA 时区。

SQL 的 `WHERE` 应直接比较 `TIMESTAMPTZ`：

```sql
v.check_in_at >= :start_utc
AND v.check_in_at < :end_utc
```

不要在过滤列上使用 `DATE_TRUNC`、`TO_CHAR` 或 `AT TIME ZONE`，否则可能使
`idx_visits_check_in_at_id` 无法进行高效范围扫描。

## 5. 避免多表 JOIN 重复计数

### 5.1 重复产生方式

一个拜访可以关联多个产品，也可以有多个 compliance finding。如果直接连接：

```text
visits -> visit_products -> compliance_findings
```

则某个拜访有 2 个产品、3 个 finding 时会产生 6 行。随后直接 `COUNT(*)` 会同时放大总数和异常
数。即便总数使用 `COUNT(DISTINCT visit_id)`，后续再连接其他一对多表仍容易引入隐蔽错误。

### 5.2 推荐查询形状

先把每个拜访归类为唯一一行，再连接具有唯一约束的 `visit_products`。异常使用相关 `EXISTS`，
不把 finding 行加入主结果集。

```sql
WITH eligible_visits AS (
    SELECT
        v.id AS visit_id,
        (
            v.check_out_at IS NULL
            AND NOT EXISTS (
                SELECT 1
                FROM compliance_findings AS cf
                WHERE cf.visit_id = v.id
            )
        ) AS is_pending,
        (
            EXISTS (
                SELECT 1
                FROM compliance_findings AS cf
                WHERE cf.visit_id = v.id
            )
        ) AS is_abnormal
    FROM visits AS v
    WHERE v.check_in_at >= :start_utc
      AND v.check_in_at < :end_utc
),
product_visits AS (
    SELECT
        vp.product_id,
        ev.visit_id,
        ev.is_pending,
        ev.is_abnormal
    FROM eligible_visits AS ev
    JOIN visit_products AS vp
      ON vp.visit_id = ev.visit_id
    WHERE (:product_id IS NULL OR vp.product_id = :product_id)
),
aggregated AS (
    SELECT
        product_id,
        COUNT(*) AS total_count,
        COUNT(*) FILTER (
            WHERE NOT is_pending AND NOT is_abnormal
        ) AS normal_count,
        COUNT(*) FILTER (
            WHERE is_abnormal
        ) AS abnormal_count,
        COUNT(*) FILTER (
            WHERE is_pending
        ) AS pending_count
    FROM product_visits
    GROUP BY product_id
)
SELECT
    p.id AS product_id,
    p.code AS product_code,
    p.name AS product_name,
    a.total_count,
    a.normal_count,
    a.abnormal_count,
    a.pending_count
FROM aggregated AS a
JOIN products AS p
  ON p.id = a.product_id
ORDER BY a.total_count DESC, p.code ASC;
```

该 SQL 是设计示例，实际实现可使用 SQLAlchemy Core 或等价 ORM 聚合表达式，但必须保持相同的
结果集基数和统计语义。可选 `product_id` 的实现也可以生成两种静态查询，避免 `OR` 对执行计划的
影响；应使用绑定参数，不能拼接 SQL。

### 5.3 是否需要 `COUNT(DISTINCT visit_id)`

推荐查询中不需要：

- `eligible_visits` 每个 `visit_id` 只有一行；
- `visit_products` 的复合主键为 `(visit_id, product_id)`；
- 主聚合没有连接 finding 或其他一对多明细。

因此在每个产品分组内，每个拜访天然只有一行，`COUNT(*)` 即为正确计数。强行使用
`COUNT(DISTINCT visit_id)` 会增加哈希或排序成本，也可能掩盖未来错误 JOIN。

如果未来查询必须直接连接一对多明细，则需要重新证明结果集基数；无法保持唯一时才使用
`COUNT(DISTINCT visit_id)`。它是防御措施，不应替代正确的查询结构和数据库唯一约束。

## 6. 是否返回零拜访产品

MVP 建议默认只返回当月至少有一次拜访的产品，即零计数产品不返回。原因是：

- 与 `docs/api-design.md` 的当前契约一致；
- 看板重点是实际发生量，结果更紧凑；
- 不需要额外定义已停用产品、创建时间和历史月份之间的零值语义；
- 默认查询可从当月聚合结果出发，成本更低。

若未来有“完整产品矩阵”需求，可增加显式 `includeZero=true`，从 `products` 左连接聚合结果并对
计数使用 `COALESCE(..., 0)`。此模式建议返回所有当前启用产品，同时仍返回当月有拜访的停用产品，
即满足 `products.is_active OR aggregated.product_id IS NOT NULL`。不能仅因产品后来停用而隐藏历史
发生量。

默认模式下：

- 未传 `productId`：省略零计数产品。
- 传入存在但当月无拜访的 `productId`：返回空 `items`。
- `productId` 不存在：返回 `404 REFERENCE_NOT_FOUND`。

## 7. 索引设计

现有 Schema 已具备 MVP 所需索引：

| 索引或约束 | 用途 |
| --- | --- |
| `idx_visits_check_in_at_id (check_in_at, id)` | 对 UTC 月份半开区间做范围扫描，并取得连接键 |
| `PRIMARY KEY visit_products (visit_id, product_id)` | 从月份内拜访连接产品，并保证产品/拜访唯一 |
| `idx_visit_products_product_visit (product_id, visit_id)` | 指定产品筛选、按产品访问和分组 |
| `UNIQUE compliance_findings (visit_id, code)` | 以 `visit_id` 为前导列支持 finding 的 `EXISTS`，同时防止异常代码重复 |

分类发生在月份范围筛选之后，MVP 不需要单独为 `check_out_at` 建索引。也无需为此查询重复创建
`compliance_findings(visit_id)` 索引，因为现有唯一索引已经以 `visit_id` 开头。

数据量增长后应先用真实分布执行 `EXPLAIN (ANALYZE, BUFFERS)`。只有确认回表读取
`check_out_at` 成为瓶颈时，才考虑 PostgreSQL 覆盖索引：

```sql
(check_in_at, id) INCLUDE (check_out_at)
```

这不是 MVP 的前置要求，避免用额外写入和存储成本换取尚未证实的优化。

## 8. 分层职责与事务一致性

| 层 | 职责 |
| --- | --- |
| API / Schema | 校验 `month` 和 `productId` 的外部格式；序列化响应和统一错误 |
| Service | 读取并校验业务时区；计算业务月 UTC 边界；校验可选产品是否存在；编排查询 |
| Repository / Query | 使用绑定参数执行一条 PostgreSQL 聚合查询；返回每个产品的计数行 |
| PostgreSQL | 过滤、连接、`EXISTS` 判定、分组和条件聚合 |
| 前端 | 展示服务器结果；不得从拜访列表重新计算或改变统计口径 |

整个统计应在一条只读 SQL 中完成。PostgreSQL `READ COMMITTED` 下，单条语句使用同一个一致性
快照，足以保证各计数来自同一视图；MVP 不需要提高隔离级别或显式锁表。查询执行期间刚完成的
签到或签退可能在本次或下次请求中可见，这是实时看板的正常语义。

## 9. 返回结构

API 对外沿用项目现有 camelCase 风格；本设计中的 SQL 别名和内部模型可使用 snake_case。

```json
{
  "month": "2026-09",
  "businessTimezone": "Asia/Shanghai",
  "rangeStartUtc": "2026-08-31T16:00:00Z",
  "rangeEndUtc": "2026-09-30T16:00:00Z",
  "items": [
    {
      "product": {
        "id": "f84b5ef1-3459-4ee2-aeaf-ce1316363094",
        "code": "PROD-CARD-001",
        "name": "心血管产品 A"
      },
      "totalCount": 12,
      "normalCount": 7,
      "abnormalCount": 3,
      "pendingCount": 2
    }
  ]
}
```

约定：

- 所有计数均为非负整数。
- `items` 按 `totalCount DESC, product.code ASC` 稳定排序。
- 本聚合接口不分页；MVP 产品量有限，筛选由可选 `productId` 完成。
- `rangeStartUtc` 和 `rangeEndUtc` 明确返回，便于审计业务月份对应的实际 UTC 区间。
- 错误沿用统一结构 `{code, message, details}`。

建议将 `docs/api-design.md` 中现有的 `totalVisitCount`、`abnormalVisitCount`、
`compliancePendingVisitCount` 在实现前统一调整为以上更对称的命名，或者保留现有名字并补充
`normalVisitCount`。无论选择哪组字段名，四类统计语义和恒等式不得改变；契约修改应单独确认，
本设计任务不直接改写现有 API 文档。

## 10. 验证与测试设计

实现时至少覆盖以下测试：

| 场景 | 预期 |
| --- | --- |
| `Asia/Shanghai` 的 `2026-09` | UTC 范围为 `[2026-08-31T16:00:00Z, 2026-09-30T16:00:00Z)` |
| 签到时间正好等于 `start_utc` | 纳入统计 |
| 签到时间正好等于 `end_utc` | 不纳入统计，属于下月 |
| 跨 UTC 日期但属于同一业务月份 | 按业务时区月份正确纳入 |
| 使用有夏令时的测试时区 | 先做本地日历边界，再正确转换 UTC |
| 一个拜访关联两个产品 | 两个产品分别增加一次 |
| 同一拜访同一产品 | 受复合主键保护，最多增加一次 |
| 一个拜访有多个 finding | 对该产品的总数和异常数均只增加一次 |
| 已签退且无 finding | `total +1`、`normal +1` |
| 已签退且有 finding | `total +1`、`abnormal +1` |
| 已签到未签退 | `total +1`、`pending +1`，正常和异常不变 |
| 混合数据 | 每行均满足 `total = normal + abnormal + pending` |
| 当月零拜访产品 | 默认不出现在 `items` |
| 指定存在但零拜访产品 | 返回空 `items` |
| 指定不存在产品 | `404 REFERENCE_NOT_FOUND` |
| 非法月份或 UUID | 返回相应 `422` 业务错误 |

测试应使用 PostgreSQL 集成测试验证真实 JOIN、唯一约束和条件聚合语义；月份边界计算可另用不依赖
数据库的 Service 单元测试覆盖。性能验证不应只看 SQL 文本，应在具有代表性的数据量上检查执行
计划是否命中月份范围和关联索引。

## 11. 设计取舍总结

- 以签到时间定义月份，使“已发生的拜访”口径稳定，不受计划调整或跨月签退影响。
- 使用签到时固化的 `visit_products`，兼顾未完成拜访统计和历史产品关联。
- 显式返回待判定数，避免把尚未完成的拜访错误包装成正常。
- 通过 `EXISTS` 和唯一产品关联控制结果集基数，不让多 finding 重复计数。
- 默认省略零值产品，保持 MVP 查询和响应简单；未来可通过显式参数扩展。
- 在 PostgreSQL 内完成聚合，前端只展示可信统计结果。
