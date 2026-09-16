# 拜访合规性校验模块设计

## 1. 目标与范围

本模块把一次完整拜访的时间和位置事实转换为零到多个结构化 `finding`。核心算法是无数据库、无网络、无系统时钟依赖的纯函数：相同输入必须得到相同输出，不修改输入，也不读取当前时间。

本设计定义领域算法和测试策略；持久化对齐由后续签退切片的 Alembic migration 完成。

### 1.1 持久化对齐

签退切片通过 migration `20260916_0002` 完成以下对齐：

1. 将旧距离异常码迁移为 `CHECKIN_TOO_FAR` 和 `CHECKOUT_TOO_FAR`。
2. 在 `compliance_findings` 的代码集合和语义 CHECK 中加入 `INVALID_TIME_SEQUENCE`。
3. 允许该 finding 保存有符号时间差，并规定阈值为 `0` 秒。
4. 移除 `visits` 对签退时间顺序和非负时长的 CHECK，以保留服务端采集到的原始事实；异常由纯函数判定。

数据库仍只负责单行字段完整性和 finding 语义；只有 `CHECKED_IN` 可以签退、重复签退不得覆盖
首次结果等状态机规则由 Service 在锁定工作流行的事务内保证。

## 2. 业务常量

| 常量                       |            值 | 说明                               |
| -------------------------- | ------------: | ---------------------------------- |
| `MIN_DURATION_SECONDS`     |         `300` | 5 分钟；小于该值异常，等于该值正常 |
| `MAX_DISTANCE_METERS`      |         `500` | 大于该值异常，等于该值正常         |
| `EARTH_MEAN_RADIUS_METERS` | `6_371_008.8` | IUGG 平均地球半径                  |
| `DISTANCE_EPSILON_METERS`  |    `0.000001` | 距离边界比较容差，即 1 微米        |

这些常量属于规则版本的一部分。调用方不能在每次调用时自行覆盖，否则同一业务规则会产生不同结论。

## 3. 输入模型

建议使用不可变模型：

```text
GeoPoint
  latitude: float   # [-90, 90]，必须为有限数
  longitude: float  # [-180, 180]，必须为有限数

VisitComplianceInput
  check_in_at: datetime       # 必须包含 UTC offset
  check_out_at: datetime      # 必须包含 UTC offset
  hospital_location: GeoPoint
  check_in_location: GeoPoint
  check_out_location: GeoPoint
```

输入坐标应当是即将持久化或已经持久化的规范坐标。当前数据库精度为六位小数，因此应用层应先按数据库精度规范化坐标，再把同一组值同时传给本模块和持久化层，避免“计算用坐标”和“审计用坐标”不同。

### 3.1 输入校验

以下情况属于输入错误，而不是合规 finding：

- 时间不是 `datetime` 或缺少 UTC offset；
- 坐标是 `NaN`、正负无穷；
- 纬度或经度超出合法范围；
- 必填事实缺失。

纯函数应抛出明确的领域输入异常，由 API 或 Service 转换为参数错误。合规 finding 只表达格式合法的业务事实违反了哪条规则。

函数不接收 `now`，也不能在内部调用 `datetime.now()`。

## 4. 输出模型

```text
ComplianceResult
  duration_seconds: Decimal
  check_in_distance_meters: Decimal
  check_out_distance_meters: Decimal
  findings: tuple[ComplianceFinding, ...]
```

- `duration_seconds` 是 `check_out_at - check_in_at` 的有符号秒数，保留微秒精度。
- 距离统一为米。
- `findings` 是不可变、有稳定顺序的 tuple；没有异常时为空 tuple。
- 输出不包含 `detected_at`。检测时间属于应用层审计数据，应由 Service 注入的 Clock 生成，不能破坏领域函数纯度。

## 5. Finding 结构

```text
ComplianceFinding
  code: FindingCode
  phase: FindingPhase
  measured_value: Decimal
  threshold_value: Decimal
  unit: FindingUnit

FindingCode
  DURATION_TOO_SHORT
  CHECKIN_TOO_FAR
  CHECKOUT_TOO_FAR
  INVALID_TIME_SEQUENCE

FindingPhase
  CHECK_IN
  CHECK_OUT

FindingUnit
  SECONDS
  METERS
```

字段语义如下：

| code                    | phase       | measured_value | threshold_value | unit      |
| ----------------------- | ----------- | -------------- | --------------- | --------- |
| `INVALID_TIME_SEQUENCE` | `CHECK_OUT` | 有符号停留秒数 | `0`             | `SECONDS` |
| `DURATION_TOO_SHORT`    | `CHECK_OUT` | 实际停留秒数   | `300`           | `SECONDS` |
| `CHECKIN_TOO_FAR`       | `CHECK_IN`  | 签到距离       | `500`           | `METERS`  |
| `CHECKOUT_TOO_FAR`      | `CHECK_OUT` | 签退距离       | `500`           | `METERS`  |

### 5.1 时间规则的去重取舍

当 `check_out_at <= check_in_at` 时，输出 `INVALID_TIME_SEQUENCE`，并跳过 `DURATION_TOO_SHORT` 判断。原因是此时时长不是合法停留时长，同时输出“时长过短”会针对同一根因产生重复且可能误导的结论。

位置规则仍然继续执行。因此非法时间顺序可以与签到超距、签退超距同时存在。如果产品最终要求等时刻同时产生两个时间 finding，应先明确修改本取舍和对应测试，而不是在实现中隐式改变。

### 5.2 Finding 稳定顺序

finding 不按集合或数据库返回顺序排列，而按固定规则顺序追加：

1. `INVALID_TIME_SEQUENCE` 或 `DURATION_TOO_SHORT`；
2. `CHECKIN_TOO_FAR`；
3. `CHECKOUT_TOO_FAR`。

稳定顺序使 API、测试、日志和 Demo 展示可预测，但业务逻辑不应依赖数组下标判断是否异常。

## 6. Haversine 公式

设医院点为 `(lat1, lon1)`，现场点为 `(lat2, lon2)`。所有角度先从度转换为弧度：

```text
phi1 = radians(lat1)
phi2 = radians(lat2)
delta_phi = radians(lat2 - lat1)
delta_lambda = radians(normalized_longitude_delta(lon2 - lon1))

a = sin²(delta_phi / 2)
    + cos(phi1) * cos(phi2) * sin²(delta_lambda / 2)

a = clamp(a, 0, 1)
c = 2 * atan2(sqrt(a), sqrt(1 - a))
distance_meters = EARTH_MEAN_RADIUS_METERS * c
```

`normalized_longitude_delta` 把经度差规范到 `[-180, 180]`，确保跨越国际日期变更线时选择较短弧线。将 `a` 夹到 `[0, 1]` 可以避免浮点舍入导致 `sqrt` 域错误。

该公式计算球面大圆距离，适合本项目 500 米量级的合规判断；MVP 不引入 PostGIS 或椭球测地线依赖。

## 7. 伪代码

```text
function evaluate_visit_compliance(input):
    validate_aware_datetime(input.check_in_at)
    validate_aware_datetime(input.check_out_at)
    validate_geo_point(input.hospital_location)
    validate_geo_point(input.check_in_location)
    validate_geo_point(input.check_out_location)

    duration_microseconds = exact_datetime_delta_microseconds(
        input.check_out_at,
        input.check_in_at,
    )
    duration_seconds = Decimal(duration_microseconds) / Decimal(1_000_000)

    check_in_distance = haversine_meters(
        input.hospital_location,
        input.check_in_location,
    )
    check_out_distance = haversine_meters(
        input.hospital_location,
        input.check_out_location,
    )

    findings = []

    if duration_microseconds <= 0:
        findings.append(
            finding(INVALID_TIME_SEQUENCE, CHECK_OUT,
                    duration_seconds, 0, SECONDS)
        )
    else if duration_microseconds < 300_000_000:
        findings.append(
            finding(DURATION_TOO_SHORT, CHECK_OUT,
                    duration_seconds, 300, SECONDS)
        )

    if is_distance_above_limit(check_in_distance, 500, epsilon=0.000001):
        findings.append(
            finding(CHECKIN_TOO_FAR, CHECK_IN,
                    check_in_distance, 500, METERS)
        )

    if is_distance_above_limit(check_out_distance, 500, epsilon=0.000001):
        findings.append(
            finding(CHECKOUT_TOO_FAR, CHECK_OUT,
                    check_out_distance, 500, METERS)
        )

    return ComplianceResult(
        duration_seconds=duration_seconds,
        check_in_distance_meters=check_in_distance,
        check_out_distance_meters=check_out_distance,
        findings=tuple(findings),
    )
```

## 8. 精度与边界策略

### 8.1 时间

时间比较不使用浮点容差。应把 `timedelta.days`、`seconds` 和 `microseconds` 转换成有符号整数微秒：

```text
total_microseconds =
    ((days * 86_400) + seconds) * 1_000_000 + microseconds
```

- `< 300_000_000` 且时间顺序有效：`DURATION_TOO_SHORT`；
- `== 300_000_000`：正常；
- `> 300_000_000`：正常；
- `<= 0`：`INVALID_TIME_SEQUENCE`，不再判断时长过短。

Python 的 aware datetime 相减会按绝对时间处理 offset，因此跨午夜或不同 offset 不应通过比较本地钟面字符串判断。

### 8.2 距离

Haversine 内部使用双精度浮点，但规则比较采用明确容差：

```text
too_far = distance_meters > MAX_DISTANCE_METERS + DISTANCE_EPSILON_METERS
```

- `distance <= 500 + 0.000001` 视为边界内，正常；
- `distance > 500 + 0.000001` 才判定超距；
- 展示层的四舍五入值不能参与合规判断；
- 测量值转 `Decimal` 时使用十进制字符串转换，避免直接暴露二进制浮点尾差；
- 数据库存储精度为六位小数，持久化适配器采用明确的 `ROUND_HALF_UP`，但 finding 是否产生应基于上述未展示舍入的规则值。

1 微米容差只吸收公式计算在 500 米边界附近的数值噪声，不用于掩盖 GPS 本身的测量误差。业务阈值仍然是 500 米。

## 9. 边界测试构造

### 9.1 精确距离测试点

不要手写一个“看起来约 500 米”的经纬度。以赤道上的医院点 `(0°, 0°)` 为基准，沿同一经线向北构造距离为 `d` 的点：

```text
latitude_delta_degrees = degrees(d / EARTH_MEAN_RADIUS_METERS)
point_for_distance(d) = (latitude_delta_degrees, 0°)
```

在球面模型和相同地球半径下，该点的理论大圆距离就是 `d`。分别用 `499`、`500`、`501` 米构造普通边界用例，并增加：

- `500 + epsilon / 2`：正常；
- `500 + 2 * epsilon`：超距。

这两个额外用例直接固定 epsilon 策略，防止实现者先把距离舍入成整数再比较。

### 9.2 经纬度边界

- `(-90, -180)`、`(90, 180)` 都是格式合法输入；
- 相同边界点到自身距离必须为 0；
- `(0, 180)` 与 `(0, -180)` 表示同一反经线位置，距离应接近 0；
- 超出边界、NaN 和无穷应触发输入异常，不产生 finding。

## 10. Pytest 参数化测试表

测试辅助值：

```text
H = GeoPoint(0, 0)
P(d) = point_for_distance(d)
T0 = 2026-09-16T10:00:00+08:00
```

除非特别说明，未关注的位置使用 `H`，未关注的签退时间使用 `T0 + 5 minutes`。

| case id                           | 签退时间 / 时长             | 签到位置                                                | 签退位置                          | 期望 finding code（按顺序）                                  | 断言重点                         |
| --------------------------------- | --------------------------- | ------------------------------------------------------- | --------------------------------- | ------------------------------------------------------------ | -------------------------------- |
| `duration_4m59s`                  | `T0 + 299s`                 | `H`                                                     | `H`                               | `[DURATION_TOO_SHORT]`                                       | 4 分 59 秒异常，测量值 299       |
| `duration_exact_5m`               | `T0 + 300s`                 | `H`                                                     | `H`                               | `[]`                                                         | 正好 5 分钟正常                  |
| `duration_5m1s`                   | `T0 + 301s`                 | `H`                                                     | `H`                               | `[]`                                                         | 5 分 1 秒正常                    |
| `same_as_hospital`                | `T0 + 300s`                 | `H`                                                     | `H`                               | `[]`                                                         | 两个距离均为 0                   |
| `distance_499m`                   | `T0 + 300s`                 | `P(499)`                                                | `H`                               | `[]`                                                         | 约束内正常                       |
| `distance_exact_500m`             | `T0 + 300s`                 | `P(500)`                                                | `H`                               | `[]`                                                         | 公式构造的精确边界正常           |
| `distance_500m_plus_half_epsilon` | `T0 + 300s`                 | `P(500 + epsilon/2)`                                    | `H`                               | `[]`                                                         | epsilon 内视为边界               |
| `distance_500m_plus_two_epsilon`  | `T0 + 300s`                 | `P(500 + 2*epsilon)`                                    | `H`                               | `[CHECKIN_TOO_FAR]`                                          | 超过 epsilon 后异常              |
| `distance_501m`                   | `T0 + 300s`                 | `P(501)`                                                | `H`                               | `[CHECKIN_TOO_FAR]`                                          | 约 501 米异常                    |
| `checkin_too_far`                 | `T0 + 300s`                 | `P(600)`                                                | `H`                               | `[CHECKIN_TOO_FAR]`                                          | 仅签到超距                       |
| `checkout_too_far`                | `T0 + 300s`                 | `H`                                                     | `P(600)`                          | `[CHECKOUT_TOO_FAR]`                                         | 仅签退超距                       |
| `both_locations_too_far`          | `T0 + 300s`                 | `P(600)`                                                | `P(700)`                          | `[CHECKIN_TOO_FAR, CHECKOUT_TOO_FAR]`                        | 两个独立位置 finding             |
| `duration_and_distance`           | `T0 + 299s`                 | `P(600)`                                                | `H`                               | `[DURATION_TOO_SHORT, CHECKIN_TOO_FAR]`                      | 时长和距离同时异常及顺序         |
| `checkout_before_checkin`         | `T0 - 1s`                   | `H`                                                     | `H`                               | `[INVALID_TIME_SEQUENCE]`                                    | 有符号测量值 -1，不产生时长过短  |
| `checkout_equals_checkin`         | `T0`                        | `H`                                                     | `H`                               | `[INVALID_TIME_SEQUENCE]`                                    | 测量值 0，不产生时长过短         |
| `valid_across_midnight`           | `23:58+08:00 → 00:03+08:00` | `H`                                                     | `H`                               | `[]`                                                         | 跨午夜但恰好 5 分钟，时序合法    |
| `coordinate_extremes`             | `T0 + 300s`                 | `(90, 180)`，医院同点                                   | `(-90, -180)`，医院同点分开参数化 | `[]`                                                         | 经纬度边界合法、同点距离 0       |
| `anti_meridian_same_place`        | `T0 + 300s`                 | 医院 `(0,180)`，现场 `(0,-180)`                         | 同签到                            | `[]`                                                         | 反经线归一化后距离接近 0         |
| `invalid_coordinate`              | `T0 + 300s`                 | 参数化 `lat=90.000001`、`lon=180.000001`、NaN、Infinity | `H`                               | 抛输入异常                                                   | 输入错误不转 finding             |
| `stable_three_findings`           | `T0 + 299s`                 | `P(600)`                                                | `P(700)`                          | `[DURATION_TOO_SHORT, CHECKIN_TOO_FAR, CHECKOUT_TOO_FAR]`    | 多 finding 稳定顺序              |
| `invalid_time_with_locations`     | `T0 - 1s`                   | `P(600)`                                                | `P(700)`                          | `[INVALID_TIME_SEQUENCE, CHECKIN_TOO_FAR, CHECKOUT_TOO_FAR]` | 时间非法仍继续位置检查，顺序稳定 |

建议拆成三组 `pytest.mark.parametrize`：时间规则、距离规则、组合规则。Haversine 本身另做对称性、同点、反经线和已知距离的纯函数单元测试，使规则失败时可以区分是距离计算问题还是 finding 编排问题。

## 11. 纯函数约束测试

除业务边界外，还应验证模块属性：

- 对同一输入调用两次，结果严格相等；
- 输入对象在调用前后相等；
- 测试通过显式时间输入完成，不 monkeypatch 系统时钟；
- 模块不能导入 SQLAlchemy、Repository、Session 或应用配置；
- findings 返回不可变 tuple；
- Haversine 满足 `distance(a, b) == distance(b, a)` 的误差容限；
- 多 finding 顺序不受集合、字典或数据库顺序影响。

这些约束确保合规算法可以在单元测试、Service、批量复核任务和未来规则回放中复用。
