# 医药代表学术拜访管理子系统：REST API 契约

## 1. 文档目标与范围

本文档基于 [业务规则](business-rules.md)、[数据库设计](database-design.md) 和
[系统架构](architecture.md)，定义 MVP 的 REST API 契约。本文只设计接口，不实现代码。

API 统一以 `/api` 为前缀，使用 JSON。MVP 不提供认证、无计划拜访、计划修改/取消、报告更正、
文件上传或地图 SDK 接口。

## 2. 资源标识与关键取舍

### 2.1 `/visits/{id}` 的 ID 语义

数据库将 `visit_plans` 和 `visits` 分开：`PLANNED` 时只有计划行，首次签到才创建实际拜访行。
因此，`/api/visits/{id}` 中的 `{id}` 定义为公开的 **拜访工作流 ID**，其值就是
`visit_plans.id`，而不是尚未创建的 `visits.id`。

- 创建计划时生成工作流 ID，并立即返回给前端。
- `POST /api/visits/{id}/check-in` 根据工作流 ID 锁定计划，并创建唯一的实际拜访行。
- 后续签到、签退、报告、详情接口始终使用同一个工作流 ID。
- Service/Repository 层通过 `visits.plan_id` 查找可选的实际拜访行。
- `visits.id` 是持久化层内部标识，本 MVP API 不暴露，避免前端在签到前后切换资源 ID。
- 这只是公开 API 的聚合标识约定，不合并计划表和实际拜访表，也不改变二者 `1 : 0..1` 的关系。

`POST /api/visits` 不存在，因此客户端不能创建无计划拜访。

### 2.2 状态派生

API 返回的 `status` 由数据库事实派生，不接受客户端写入：

| API 状态      | 数据事实                 |
| ------------- | ------------------------ |
| `PLANNED`     | 计划存在，实际拜访不存在 |
| `CHECKED_IN`  | 实际拜访存在，尚未签退   |
| `CHECKED_OUT` | 已签退，报告不存在       |
| `REPORTED`    | 报告存在                 |

## 3. 通用约定

### 3.1 命名、类型与时间

- JSON 字段使用 `camelCase`；枚举值和稳定错误码使用大写下划线格式。
- ID 使用标准 UUID 字符串；路径中的非 UUID 值返回 `422 VALIDATION_ERROR`。
- 经纬度是 WGS 84 十进制度数：纬度 `[-90, 90]`，经度 `[-180, 180]`。
- API 时间使用 RFC 3339，必须携带 `Z` 或明确的 UTC offset，例如
  `2026-09-16T09:30:00+08:00`。服务端响应统一序列化为 UTC `Z`。
- 不带时区的请求时间返回 `422 TIMEZONE_REQUIRED`。
- 数据库存储 `TIMESTAMPTZ`；前端按响应中的业务时区配置进行显示。
- 距离单位为米，停留时长单位为秒；返回值是服务端计算结果，显示时可格式化但不能反写。
- 请求 JSON 默认拒绝未定义字段，返回 `422 UNEXPECTED_FIELD`，防止静默接受可信业务字段。

### 3.2 分页

列表接口使用页码分页：

| 参数       | 默认值 | 约束           |
| ---------- | ------ | -------------- |
| `page`     | `1`    | 整数，`>= 1`   |
| `pageSize` | `20`   | 整数，`1..100` |

统一分页响应：

```json
{
  "items": [],
  "page": 1,
  "pageSize": 20,
  "total": 0
}
```

越界或类型错误返回 `422 VALIDATION_ERROR`。超过最后一页返回空 `items`，不是 `404`。

### 3.3 统一错误格式

```json
{
  "error": {
    "code": "VISIT_ALREADY_CHECKED_IN",
    "message": "The visit has already been checked in.",
    "details": [
      {
        "field": "id",
        "reason": "CURRENT_STATUS_CHECKED_IN"
      }
    ]
  },
  "requestId": "01J7..."
}
```

- `code`：稳定、供前端分支判断的机器可读代码。
- `message`：面向人的说明，可调整措辞，前端不得依赖其精确文本。
- `details`：数组；无字段级信息时返回空数组，不返回 `null`。
- `requestId`：可选的请求追踪标识，不属于业务判断条件。

HTTP 状态区分：

| HTTP 状态                   | 使用场景                                         | 代表错误码                                              |
| --------------------------- | ------------------------------------------------ | ------------------------------------------------------- |
| `404 Not Found`             | UUID 格式正确，但工作流或引用资源不存在          | `VISIT_WORKFLOW_NOT_FOUND`、`REFERENCE_NOT_FOUND`       |
| `409 Conflict`              | 请求结构正确、资源存在，但与当前生命周期状态冲突 | `VISIT_ALREADY_CHECKED_IN`、`VISIT_ALREADY_CHECKED_OUT` |
| `422 Unprocessable Content` | 字段、查询参数、时间、坐标、集合或跨字段语义无效 | `VALIDATION_ERROR`、`TIMEZONE_REQUIRED`                 |

数据库唯一/外键冲突必须由应用层转换为本文规定的稳定错误码，不能向客户端泄露约束名或 SQL。

### 3.4 通用只读表示

计划摘要 `VisitPlanView`：

```json
{
  "id": "c85353dc-a8d4-4ccd-b63c-96d4ff06ee85",
  "status": "PLANNED",
  "plannedAt": "2026-09-21T01:30:00Z",
  "createdAt": "2026-09-16T02:00:00Z",
  "mr": { "id": "...", "code": "MR-SH-001", "name": "王晨" },
  "hcpPractice": {
    "id": "...",
    "hcp": { "id": "...", "code": "HCP-SH-001", "name": "陈医生" },
    "hospital": { "id": "...", "code": "HOSP-SH-RJ", "name": "瑞金医院" },
    "department": { "id": "...", "code": "DEPT-CARD", "name": "心内科" }
  },
  "targetProducts": [
    { "id": "...", "code": "PROD-CARD-001", "name": "心血管产品 A" }
  ]
}
```

其中 `id` 是第 2.1 节定义的工作流 ID。代码和名称使用计划创建时的历史快照。

实际执行对象 `actualVisit` 在 `PLANNED` 时为 `null`；签到后结构如下：

```json
{
  "checkIn": {
    "at": "2026-09-21T01:28:10Z",
    "latitude": 31.210461,
    "longitude": 121.473651,
    "distanceMeters": 0.15
  },
  "checkOut": null,
  "durationSeconds": null,
  "products": [
    { "id": "...", "code": "PROD-CARD-001", "name": "心血管产品 A" }
  ],
  "complianceStatus": "IN_PROGRESS",
  "complianceFindings": []
}
```

`checkOut` 签退后与 `checkIn` 同结构；`durationSeconds` 同时变为服务端生成值。`PLANNED`
通过 `actualVisit = null` 表达；实际拜访中的 `complianceStatus`：

- `IN_PROGRESS`：已签到未签退且当前尚无异常；
- `NORMAL`：已签退且没有异常；
- `ABNORMAL`：已签退且至少有一个异常。

生命周期状态与合规状态是两个维度：成功签退后生命周期统一为 `CHECKED_OUT`，合规状态再由
`complianceFindings` 是否为空派生为 `NORMAL` 或 `ABNORMAL`，数据库不保存冗余状态列。

结构化异常字段：

```json
{
  "code": "CHECKIN_TOO_FAR",
  "message": "Check-in location is more than 500 meters from the hospital",
  "actualValue": "612.345678",
  "threshold": "500.000000",
  "phase": "CHECK_IN",
  "unit": "METERS",
  "detectedAt": "2026-09-21T01:28:10Z"
}
```

## 4. 创建拜访计划

### `POST /api/visit-plans`

请求：

```json
{
  "mrId": "75a75d6a-b562-493b-bc87-41a39234d040",
  "hcpId": "b989df77-d693-45f9-97d0-bce457f5b66a",
  "hospitalId": "3b881a35-e514-4a24-ae3f-45eddf2a1948",
  "departmentId": "0912d04c-12e6-4a8d-b5e9-2055959392bd",
  "plannedAt": "2026-09-21T09:30:00+08:00",
  "productIds": [
    "f84b5ef1-3459-4ee2-aeaf-ce1316363094",
    "15db359b-7aeb-42f9-9ad6-d52d8881a34a"
  ]
}
```

| 字段           | 必填 | 规则                                          |
| -------------- | ---- | --------------------------------------------- |
| `mrId`         | 是   | 存在且启用的 MR UUID                          |
| `hcpId`        | 是   | 存在且启用的 HCP UUID                         |
| `hospitalId`   | 是   | 存在且启用的医院 UUID                         |
| `departmentId` | 是   | 存在且启用的标准科室 UUID                     |
| `plannedAt`    | 是   | 带时区 RFC 3339 时间                          |
| `productIds`   | 是   | 至少 1 个；每个产品存在且启用；请求内不可重复 |

Service 必须使用四个主数据 ID 精确解析一条启用的 `hcp_practices`：指定医院必须开设指定科室，
且指定 HCP 必须在该医院科室执业。客户端不直接提交内部 `hcpPracticeId`。

成功：`201 Created`，响应为 `VisitPlanView`；`Location` 为 `/api/visits/{id}`。

错误：

| 状态  | code                    | 场景                                     |
| ----- | ----------------------- | ---------------------------------------- |
| `404` | `MR_NOT_FOUND`          | MR 不存在                                |
| `404` | `HCP_NOT_FOUND`         | HCP 不存在                               |
| `404` | `HOSPITAL_NOT_FOUND`    | 医院不存在                               |
| `404` | `DEPARTMENT_NOT_FOUND`  | 科室不存在                               |
| `404` | `PRODUCT_NOT_FOUND`     | 一个或多个产品不存在                     |
| `422` | `REFERENCE_INACTIVE`    | 任一主数据已停用                         |
| `422` | `HCP_PRACTICE_MISMATCH` | 医院科室关系或 HCP 执业关系不存在/已停用 |
| `422` | `PRODUCTS_REQUIRED`     | `productIds` 为空                        |
| `422` | `DUPLICATE_PRODUCT_ID`  | `productIds` 中存在重复值                |
| `422` | `TIMEZONE_REQUIRED`     | `plannedAt` 不带时区                     |
| `422` | `VALIDATION_ERROR`      | UUID、时间或请求结构无效                 |

重复/幂等：本接口不是幂等接口；两个相同请求会创建两个不同计划。MVP 不支持幂等键。

允许客户端提交的字段只有上表六项。禁止提交 `hcpPracticeId`、`id`、`status`、`createdAt`、快照名称/代码、
签到/签退字段、距离、时长、异常和报告字段。

## 5. 查询拜访计划

### `GET /api/visit-plans`

计划视角的轻量列表，返回分页 `VisitPlanView`。

筛选与排序：

| 参数                        | 规则                                                       |
| --------------------------- | ---------------------------------------------------------- |
| `status`                    | 可重复；`PLANNED`、`CHECKED_IN`、`CHECKED_OUT`、`REPORTED` |
| `mrId`                      | MR UUID                                                    |
| `hcpId`                     | HCP UUID，通过计划保存的执业关系筛选                       |
| `hospitalId`                | 医院 UUID，通过执业关系筛选                                |
| `departmentId`              | 标准科室 UUID，通过执业关系筛选                            |
| `productId`                 | 计划目标产品 UUID                                          |
| `plannedFrom` / `plannedTo` | 带时区 RFC 3339 半开区间 `[from, to)`；可单独使用          |
| `sort`                      | `plannedAt` 或 `createdAt`，默认 `plannedAt`               |
| `order`                     | `asc` 或 `desc`，默认 `desc`                               |
| `page` / `pageSize`         | 见通用分页                                                 |

若 `plannedFrom >= plannedTo`，返回 `422 INVALID_TIME_RANGE`。筛选无匹配时返回 `200` 空页。

成功：`200 OK`。本接口无请求体，不修改状态，重复请求是安全、幂等的只读操作。

## 6. 查询拜访工作流

### `GET /api/visits`

返回用于执行和复核的工作流摘要列表。为使前端能从列表进入签到，结果包含 `PLANNED`；
“实际拜访统计”仍只包含已签到记录，不能把此列表条数当作看板数据。

每个 item 包含 `VisitPlanView` 的全部字段，并增加轻量的 `executionSummary`：

```json
{
  "executionSummary": {
    "checkInAt": "2026-09-21T01:28:10Z",
    "checkOutAt": null,
    "durationSeconds": null,
    "isAbnormal": false,
    "findingCodes": []
  },
  "reportSubmittedAt": null
}
```

`PLANNED` 时 `executionSummary` 为 `null`。详情接口才返回包含坐标、距离和全部异常的
`actualVisit`。

筛选与排序：

| 参数                                                       | 规则                                                                                                               |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `status`                                                   | 可重复；四种生命周期状态                                                                                           |
| `mrId`、`hcpId`、`hospitalId`、`departmentId`、`productId` | UUID 精确筛选                                                                                                      |
| `isAbnormal`                                               | `true`/`false`；使用该筛选会排除 `PLANNED`；`false` 只表示实际拜访当前无已发现异常，不代表未签退拜访已完成合规校验 |
| `plannedFrom` / `plannedTo`                                | 计划时间的带时区 RFC 3339 半开区间 `[from, to)`；可单独使用                                                        |
| `checkInFrom` / `checkInTo`                                | 签到时间的带时区 RFC 3339 半开区间 `[from, to)`；使用任一签到时间筛选时自动排除 `PLANNED`                          |
| `sort`                                                     | `plannedAt`、`checkInAt` 或 `createdAt`；默认 `plannedAt`                                                          |
| `order`                                                    | `asc` 或 `desc`；默认 `desc`；空签到时间排在最后                                                                   |
| `page` / `pageSize`                                        | 见通用分页                                                                                                         |

成功：`200 OK`。无请求体，重复请求是安全、幂等的只读操作。无效范围返回
`422 INVALID_TIME_RANGE`。

### `GET /api/visits/{id}`

返回完整工作流详情，顶层字段如下：

| 字段             | 类型            | 含义                      |
| ---------------- | --------------- | ------------------------- |
| `id`             | UUID            | 工作流 ID                 |
| `status`         | enum            | 当前派生状态              |
| `plan`           | `VisitPlanView` | 计划及历史快照            |
| `actualVisit`    | object/null     | 签到后存在，结构见 3.4 节 |
| `report`         | object/null     | `REPORTED` 时存在         |
| `allowedActions` | string[]        | 当前状态允许的下一步操作  |

`report` 包含 `conversationSummary`、`hcpFeedback`、`detailingRecords`、
`materialDistributions`、服务端 `submittedAt` 和 `createdAt`。两类子项字段与第 9 节的允许输入相同；
资料项额外返回服务端生成的 `id`。`report` 在 `REPORTED` 前为 `null`。

`allowedActions` 与状态机严格对应：`PLANNED` 为 `["CHECK_IN"]`，`CHECKED_IN` 为
`["CHECK_OUT"]`，`CHECKED_OUT` 为 `["SUBMIT_REPORT"]`，`REPORTED` 为空数组。

成功：`200 OK`。

错误：

- `{id}` 不是 UUID：`422 VALIDATION_ERROR`；
- UUID 合法但工作流不存在：`404 VISIT_WORKFLOW_NOT_FOUND`。

本接口无请求体，重复请求是安全、幂等的只读操作。

## 7. 签到

### `POST /api/visits/{id}/check-in`

路径 `{id}` 是工作流 ID。状态前置条件：只能是 `PLANNED`。

请求仅允许坐标：

```json
{
  "latitude": 31.210461,
  "longitude": 121.473651
}
```

成功事务会锁定计划行，创建实际拜访、复制全部计划产品快照、用服务端 UTC Clock 生成签到时间，
并计算和保存可信的 Haversine 距离。成功返回 `200 OK` 和完整工作流详情。本轮签到接口只记录
距离事实，不执行 500 米阈值判断，也不创建 `compliance_findings`；合规异常将在后续合规切片实现。

错误：

| 状态  | code                       | 场景                                    |
| ----- | -------------------------- | --------------------------------------- |
| `404` | `VISIT_NOT_FOUND`          | 工作流不存在                            |
| `409` | `VISIT_ALREADY_CHECKED_IN` | 当前为 `CHECKED_IN`；重复或并发落后请求 |
| `409` | `INVALID_VISIT_STATE`      | 当前为 `CHECKED_OUT` 或 `REPORTED`      |
| `422` | `INVALID_COORDINATES`      | 纬度或经度超出范围或不是有限数值        |
| `422` | `UNEXPECTED_FIELD`         | 请求包含坐标以外的字段                  |
| `422` | `VALIDATION_ERROR`         | 请求缺字段、类型错误或路径 ID 非法      |

重复/并发：接口不是“重复成功”式幂等。第一次成功后，仍处于 `CHECKED_IN` 的重复或并发落后请求
稳定返回 `409 VISIT_ALREADY_CHECKED_IN`；已经签退或报告完成后再次签到返回
`409 INVALID_VISIT_STATE`。任何失败请求都不覆盖首次时间、坐标、距离或实际产品快照。

客户端禁止提交 `checkInAt`、医院坐标快照、`distanceMeters`、`status`、`durationSeconds`、
`complianceStatus`、`complianceFindings` 或任何签退/报告字段；出现这些字段返回
`422 UNEXPECTED_FIELD`。

## 8. 签退

### `POST /api/visits/{id}/check-out`

路径 `{id}` 是工作流 ID。状态前置条件：只能是 `CHECKED_IN`。

请求仅允许坐标：

```json
{
  "latitude": 31.21047,
  "longitude": 121.47366
}
```

成功事务使用服务端 UTC Clock 生成签退时间，由数据库生成列计算精确停留秒数，调用纯函数
计算签到/签退距离与全部合规异常，并在同一事务中一次性保存签退事实和 findings。成功返回
`200 OK` 和完整工作流详情；生命周期状态为 `CHECKED_OUT`，合规状态独立派生为 `NORMAL`
或 `ABNORMAL`。

错误：

| 状态  | code                        | 场景                               |
| ----- | --------------------------- | ---------------------------------- |
| `404` | `VISIT_WORKFLOW_NOT_FOUND`  | 工作流不存在                       |
| `409` | `VISIT_NOT_CHECKED_IN`      | 当前为 `PLANNED`                   |
| `409` | `VISIT_ALREADY_CHECKED_OUT` | 当前为 `CHECKED_OUT` 或 `REPORTED` |
| `422` | `INVALID_COORDINATES`       | 纬度或经度非法                     |
| `422` | `UNEXPECTED_FIELD`          | 请求包含坐标以外的字段             |
| `422` | `VALIDATION_ERROR`          | 请求结构或路径 ID 非法             |

重复/并发：第一次成功后，重复请求稳定返回 `409 VISIT_ALREADY_CHECKED_OUT`；不得覆盖首次
签退时间、坐标、距离、时长或异常。正好 300 秒正常，小于 300 秒生成
`DURATION_TOO_SHORT`；距离正好 500 米正常，大于 500 米才生成地点异常。

客户端禁止提交 `checkOutAt`、`distanceMeters`、`durationSeconds`、`status`、异常、阈值或任何
报告字段；出现这些字段返回 `422 UNEXPECTED_FIELD`。

## 9. 提交完整拜访记录

### `PUT /api/visits/{id}/report`

首次创建报告的状态前置条件：只能是 `CHECKED_OUT`，并且尚未存在报告。`REPORTED` 只允许执行
下文定义的相同内容幂等重试，不允许再次创建或修改。

请求：

```json
{
  "conversationSummary": "讨论了适应症和最新临床研究结果。",
  "hcpFeedback": "医生关注长期安全性数据。",
  "detailingRecords": [
    {
      "productId": "f84b5ef1-3459-4ee2-aeaf-ce1316363094",
      "contentSummary": "介绍了指南证据和主要研究终点。"
    }
  ],
  "materialDistributions": [
    {
      "productId": "f84b5ef1-3459-4ee2-aeaf-ce1316363094",
      "materialCode": "LIT-2026-001",
      "materialName": "临床研究文献复印件",
      "quantity": 1,
      "isCompliant": true
    }
  ]
}
```

字段规则：

| 字段                                | 规则                                                               |
| ----------------------------------- | ------------------------------------------------------------------ |
| `conversationSummary`               | 必填、去除首尾空白后非空                                           |
| `hcpFeedback`                       | 必填、去除首尾空白后非空                                           |
| `detailingRecords`                  | 至少一项；`productId` 不重复，且集合必须与实际拜访产品集合完全一致 |
| `detailingRecords[].contentSummary` | 非空                                                               |
| `materialDistributions`             | 必填数组，可为空，表示未派发资料                                   |
| `materialDistributions[].productId` | 可省略或为 `null`，表示通用资料；非空时必须属于实际拜访产品        |
| `materialCode` / `materialName`     | 非空                                                               |
| `quantity`                          | 正整数                                                             |
| `isCompliant`                       | 必填布尔值                                                         |

成功：`200 OK`，返回完整工作流详情，`status = REPORTED`。`submittedAt` 由服务端生成。

错误：

| 状态  | code                             | 场景                                                     |
| ----- | -------------------------------- | -------------------------------------------------------- |
| `404` | `VISIT_WORKFLOW_NOT_FOUND`       | 工作流不存在                                             |
| `409` | `VISIT_NOT_CHECKED_OUT`          | 当前为 `PLANNED` 或 `CHECKED_IN`                         |
| `409` | `VISIT_REPORT_ALREADY_SUBMITTED` | 当前为 `REPORTED` 且请求内容与原报告不同；不得覆盖原报告 |
| `422` | `DETAILING_RECORDS_REQUIRED`     | 沟通记录为空                                             |
| `422` | `DUPLICATE_DETAILING_PRODUCT`    | 沟通产品重复                                             |
| `422` | `REPORT_PRODUCT_SET_MISMATCH`    | 沟通产品集合不等于实际产品集合                           |
| `422` | `REPORT_PRODUCT_NOT_IN_VISIT`    | 资料项引用了非本次拜访产品                               |
| `422` | `VALIDATION_ERROR`               | 文本、数量、UUID 或结构无效                              |

重复/幂等：PUT 可安全重试。成功后使用语义相同的完整请求体重试，返回 `200 OK` 和原报告，
且不更新 `submittedAt`、`createdAt` 或任何子项；使用不同内容重试返回
`409 VISIT_REPORT_ALREADY_SUBMITTED`。这里的“语义相同”指通过校验和首尾空白规范化后，两个摘要
相同、沟通记录按 `productId` 组成的映射相同、资料派发项按全部业务字段组成的多重集合相同；数组
顺序不影响判断。MVP 不提供报告更正或覆盖。

客户端禁止提交 `submittedAt`、`createdAt`、`status`、签到/签退时间、距离、时长、异常或异常
阈值；出现这些字段返回 `422 UNEXPECTED_FIELD`。

## 10. 产品月度拜访看板

### `GET /api/dashboard/monthly-visits-by-product`

查询参数：

| 参数        | 必填 | 规则                                      |
| ----------- | ---- | ----------------------------------------- |
| `month`     | 是   | `YYYY-MM`，例如 `2026-09`                 |
| `productId` | 否   | 产品 UUID；省略时返回当月所有有拜访的产品 |

业务时区由服务端配置，客户端不能传入或覆盖。服务端按该时区计算自然月边界，再转换成 UTC
半开区间 `[startUtc, endUtc)`，并按实际 `checkInAt` 筛选。

成功响应 `200 OK`：

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
      "totalVisitCount": 12,
      "abnormalVisitCount": 3,
      "compliancePendingVisitCount": 2
    }
  ]
}
```

统计口径：

- 仅统计已签到的 `CHECKED_IN`、`CHECKED_OUT`、`REPORTED`；`PLANNED` 不计入。
- 使用签到时间所属业务自然月，不使用计划时间或签退时间。
- 异常拜访仍计入 `totalVisitCount`，并计入 `abnormalVisitCount`。
- 同一拜访同一产品最多计数一次；多产品拜访分别计入各产品。
- 多个异常原因不会重复增加同一产品的 `abnormalVisitCount`。
- `compliancePendingVisitCount` 统计尚未签退的拜访。当前切片在签退时一次性运行完整合规校验，
  因此 pending 与 `abnormalVisitCount` 不重叠。
- 无筛选时只返回当月至少一次拜访的产品，按 `totalVisitCount desc, product.code asc` 排序。
- MVP 预计产品数量有限，本聚合接口不分页；列表分页规则不适用于本接口。

错误：

| 状态  | code                  | 场景                                     |
| ----- | --------------------- | ---------------------------------------- |
| `404` | `REFERENCE_NOT_FOUND` | 指定的 `productId` 不存在                |
| `422` | `INVALID_MONTH`       | `month` 缺失、格式非法或不是有效年月     |
| `422` | `VALIDATION_ERROR`    | `productId` 不是 UUID 或存在未知查询参数 |

本接口无请求体，是安全、幂等的只读查询。

## 11. 客户端字段权限汇总

| 操作      | 允许客户端提交                                                           | 明确禁止客户端提交                                      |
| --------- | ------------------------------------------------------------------------ | ------------------------------------------------------- |
| 创建计划  | `mrId`、`hcpId`、`hospitalId`、`departmentId`、`plannedAt`、`productIds` | `hcpPracticeId`、ID、状态、快照、审计时间、实际拜访数据 |
| 签到      | `latitude`、`longitude`                                                  | 签到时间、医院坐标快照、距离、状态、实际产品、异常      |
| 签退      | `latitude`、`longitude`                                                  | 签退时间、距离、时长、状态、异常和阈值                  |
| 提交报告  | 摘要、反馈、沟通记录、资料派发明细                                       | 提交时间、状态、签到/签退事实、时长、距离、异常         |
| 查询/看板 | 文档列出的路径和查询参数                                                 | 请求体、业务时区覆盖、客户端统计结果                    |

服务端时间、距离、时长、生命周期状态、合规结论和异常记录始终是服务端可信数据。前端可以输入
模拟 GPS 坐标和业务内容，但不能决定或覆盖任何派生字段。

## 12. 稳定业务错误码清单

| code                             | HTTP  | 含义                             |
| -------------------------------- | ----- | -------------------------------- |
| `VALIDATION_ERROR`               | `422` | 通用类型、格式或必填校验失败     |
| `UNEXPECTED_FIELD`               | `422` | 请求包含契约未允许字段           |
| `TIMEZONE_REQUIRED`              | `422` | 时间缺少时区                     |
| `INVALID_TIME_RANGE`             | `422` | 起止时间范围非法                 |
| `INVALID_MONTH`                  | `422` | 月份格式或值非法                 |
| `INVALID_COORDINATES`            | `422` | 经纬度非法                       |
| `MR_NOT_FOUND`                   | `404` | 医药代表不存在                   |
| `HCP_NOT_FOUND`                  | `404` | 医生不存在                       |
| `HOSPITAL_NOT_FOUND`             | `404` | 医院不存在                       |
| `DEPARTMENT_NOT_FOUND`           | `404` | 科室不存在                       |
| `PRODUCT_NOT_FOUND`              | `404` | 产品不存在                       |
| `REFERENCE_NOT_FOUND`            | `404` | 其他接口引用的主数据不存在       |
| `REFERENCE_INACTIVE`             | `422` | 引用主数据已停用                 |
| `HCP_PRACTICE_MISMATCH`          | `422` | 医院科室或医生执业关系无效       |
| `PRODUCTS_REQUIRED`              | `422` | 创建计划没有产品                 |
| `DUPLICATE_PRODUCT_ID`           | `422` | 创建计划的产品重复               |
| `VISIT_WORKFLOW_NOT_FOUND`       | `404` | 拜访工作流不存在                 |
| `VISIT_NOT_FOUND`                | `404` | 签到目标工作流不存在             |
| `VISIT_ALREADY_CHECKED_IN`       | `409` | 重复签到                         |
| `INVALID_VISIT_STATE`            | `409` | 当前状态不允许请求的生命周期操作 |
| `VISIT_NOT_CHECKED_IN`           | `409` | 尚未签到却请求签退               |
| `VISIT_ALREADY_CHECKED_OUT`      | `409` | 重复签退                         |
| `VISIT_NOT_CHECKED_OUT`          | `409` | 尚未签退却提交报告               |
| `VISIT_REPORT_ALREADY_SUBMITTED` | `409` | 已有报告且再次提交的内容不同     |
| `DETAILING_RECORDS_REQUIRED`     | `422` | 报告缺少沟通记录                 |
| `DUPLICATE_DETAILING_PRODUCT`    | `422` | 报告沟通产品重复                 |
| `REPORT_PRODUCT_SET_MISMATCH`    | `422` | 沟通产品集合与实际产品集合不一致 |
| `REPORT_PRODUCT_NOT_IN_VISIT`    | `422` | 资料引用非本次拜访产品           |

未预期服务端错误统一返回 `500 INTERNAL_SERVER_ERROR`，`details` 为空；不得返回 SQL、堆栈或敏感配置。

## 13. 事务与并发契约

- 创建计划及全部目标产品必须在一个事务完成。
- 签到锁定计划行；实际拜访创建、医院坐标快照、距离结果和产品快照在同一事务完成。本轮不创建签到异常。
- 签退使用行锁或条件更新，签退事实和新增异常在同一事务完成。
- 报告、沟通记录和资料派发在一个事务完成；任何子项失败都不产生部分报告。
- 并发状态冲突使用与顺序重复操作相同的稳定 `409` 错误码。
- API 不承诺使用数据库约束名作为错误码；Service 层必须把唯一/外键冲突翻译为本文错误码。
