# 设计与维护指南

## 1. 项目设计初衷

这个项目的目标不是做一个通用 AI Gateway，也不是做一个功能丰富的代理层，而是解决一个非常具体、已经被验证存在的兼容性问题：

- Cursor 在使用 Base URL override 时
- 某些请求会把 Responses API 风格的请求体发送到 `/v1/chat/completions`
- 上游如果严格按 Chat Completions 协议校验，就会报错：
  - `field messages is required`

也就是说，问题的根因不是：

- 上游 `new-api` 不支持 OpenAI-compatible
- 模型本身不支持
- API Key 无效
- 网络不通

而是：

- **请求体语义更接近 `/v1/responses`**
- **请求路径却落到了 `/v1/chat/completions`**

因此，这个项目的设计原则从一开始就非常明确：

- 只修复路径与请求体语义错配
- 不扩大职责
- 不替代上游服务
- 不做与问题无关的管理功能

## 2. 这个项目解决了什么问题

它解决的是下面这类请求：

```http
POST /v1/chat/completions
Authorization: Bearer <upstream-key>
Content-Type: application/json

{
  "model": "gpt-5.4",
  "input": "hello",
  "stream": false
}
```

这类请求的问题在于：

- 路径是 `/v1/chat/completions`
- 但 body 里没有 `messages`
- body 却有 `input`

对于严格的 Chat Completions 处理器来说，这类请求天然不合法，因为它期待的是：

```json
{
  "model": "gpt-5.4",
  "messages": [
    {"role": "user", "content": "hello"}
  ]
}
```

所以如果不加这一层兼容代理，后果通常是：

- Cursor 报请求失败
- 上游返回 `field messages is required`
- 用户会误以为是 `new-api` 或模型兼容性问题

本项目通过最小方式修复这一点：

- 当检测到请求是 Responses 风格
- 且又被错误地发到了 `/v1/chat/completions`
- 就只修改目标上游路径，把它转发到 `/v1/responses`
- body 不做协议重写
- `Authorization` 不做替换

## 3. 为什么采用现在这个设计

### 3.1 为什么不做 LiteLLM

LiteLLM 很适合做统一网关、多 provider 路由、虚拟 key、日志和策略管理，但它不是这个问题的最小必要解。

当前项目的目标只有一个：

- 修复 Cursor 把 Responses 风格 body 发错到 Chat Completions 路径的问题

如果直接上 LiteLLM，会带来额外复杂度：

- 额外部署层
- 更多配置项
- 更重的维护成本
- 更大的故障面

而当前问题已经证明：

- 只做条件式路径改写就足够解决

所以这个项目刻意不引入 LiteLLM。

### 3.2 为什么不做本地鉴权

这个代理默认只监听 `127.0.0.1`，服务对象是本机上的 Cursor。

在这个前提下，本地再加一层单独 API Key，会带来这些额外成本：

- Cursor 侧配置更复杂
- 用户需要维护两份 key
- 需要说明“本地 key”和“上游 key”的区别
- 容易在排障时混淆哪一层鉴权失败

因为它只服务本机，且默认不暴露到局域网和公网，所以这里选择：

- 不做本地鉴权
- 直接透传客户端传入的 `Authorization`

### 3.3 为什么不保存上游 API Key

这个代理不是凭据托管层。

当前选择是：

- 由客户端直接持有真实上游 key
- 代理只做透传

这样有几个好处：

- 配置更简单
- 代理层无状态
- 不需要加密存储密钥
- 不会引入“本地配置错了但 Cursor 配的是对的”这类双重配置问题

### 3.4 为什么只监听 `127.0.0.1`

因为这个项目没有本地鉴权。

一旦绑定到 `0.0.0.0` 或暴露到局域网，这个代理就会变成一个“无本地鉴权的透明转发口”，这不符合当前安全边界。

所以这里的默认安全假设是：

- 只服务本机
- 不作为共享网关

## 4. 迁移说明与迁移后果

这个项目是从之前的临时 PoC 演化出来的，但在正式独立项目中，设计已经做了收敛。

### 4.1 从临时 PoC 到正式项目的变化

旧的临时版本包含过这些能力：

- 本地代理单独 API Key
- 代理保存固定上游 API Key
- 模型白名单
- 在另一个本地工作仓库中以临时目录存在

现在的正式版本去掉了这些东西，变成：

- 独立项目目录
- 不做本地鉴权
- 不保存上游 key
- 直接透传客户端 `Authorization`
- 只保留与兼容问题直接相关的逻辑

### 4.2 迁移后的直接影响

迁移到当前版本后，使用方式会发生这些变化：

- Cursor 中的 API Key 必须填写真实上游 key，而不是本地代理 key
- 本地代理不再有“代理内置上游 key”的概念
- 本地代理不再限制模型名
- 本地代理默认只做透明兼容转发

### 4.3 如果继续沿用旧配置，会出现什么问题

如果你还沿用旧 PoC 的思路，可能会出现以下后果：

- 如果 Cursor 仍填旧的本地 key：
  - 上游会收到一个无效 key
  - 最终表现为上游鉴权失败，而不是代理失败

- 如果你误以为代理仍然保存上游 key：
  - 你会在 Cursor 里留空或填错 key
  - 请求会直接被上游拒绝

- 如果你把监听地址改成 `0.0.0.0`：
  - 会扩大暴露面
  - 在没有本地鉴权的前提下，不符合当前设计边界

### 4.4 如果以后决定做共享代理

那就意味着当前设计假设已经失效，需要重新引入：

- 本地鉴权
- 更严格的监听地址和访问控制
- 日志脱敏
- 更明确的配置管理

不要在当前代码上只改一个监听地址就拿去多人共用。

## 5. 当前是如何解决问题的

### 5.1 请求处理流程

当前请求流程如下：

1. 客户端把请求发到本地代理
2. 代理读取请求路径、方法、Header 和 body
3. 如果 body 是 JSON，就尝试解析
4. 如果满足“Responses 风格 body 误发到 `/v1/chat/completions`”这一条件
   - 把上游目标路径改成 `/v1/responses`
5. 否则保留原始路径
6. 保留原始 `Authorization`，直接转发到上游
7. 将上游响应原样返回给客户端

### 5.2 命中改写的判断条件

当前判断逻辑是：

- `POST /v1/chat/completions`
- `Content-Type` 包含 `application/json`
- 请求体中存在 `input`
- 请求体中不存在 `messages`

这组判断的目的，是尽量只拦住已知错配，而不去干扰正常的 Chat Completions 请求。

### 5.3 为什么不改 body

因为当前已验证：

- 上游 `new-api` 能正确处理 `/v1/responses`
- 问题主要出在路径错配，而不是 body 本身不合法

既然问题不是 body，就不要额外增加 body 转换逻辑。

这也是“最小变更”原则的一部分。

## 6. 代码结构与修改入口

### 6.1 核心文件

- `src/cursor_openai_compat_proxy/config.py`
  - 负责读取环境变量
  - 负责校验 `UPSTREAM_BASE_URL`

- `src/cursor_openai_compat_proxy/proxy.py`
  - 负责判断是否命中改写
  - 负责构造上游 URL
  - 负责过滤 hop-by-hop header
  - 这是最核心的协议兼容逻辑所在

- `src/cursor_openai_compat_proxy/app.py`
  - 负责创建 FastAPI 应用
  - 负责 HTTP 请求生命周期
  - 负责把解析逻辑、改写逻辑、转发逻辑串起来
  - 负责普通响应和流式响应透传

- `src/cursor_openai_compat_proxy/main.py`
  - 程序入口

### 6.2 如果以后出现新问题，应该先看哪里

#### 场景 A：正常 chat 请求也被错误改写

先看：

- `proxy.py` 中的 `is_responses_style_payload`
- `proxy.py` 中的 `rewrite_target_path`

重点检查：

- 是否误把某些普通 chat 请求识别成 Responses 风格
- 是否需要收紧判断条件

#### 场景 B：Cursor 新版本改了请求格式

先看：

- `proxy.py` 中的 `RESPONSES_HINT_KEYS`
- `parse_json_body`
- `rewrite_target_path`

可能要做的修改：

- 增加或减少 Responses 风格识别字段
- 调整命中条件

#### 场景 C：上游接口地址变了

先看：

- `.env`
- `config.py`

通常不需要改代码，只需要改：

- `UPSTREAM_BASE_URL`

#### 场景 D：流式请求异常

先看：

- `app.py` 中 `payload.get("stream") is True` 的分支
- `StreamingResponse`
- `client.send(..., stream=True)`

#### 场景 E：Header 透传异常

先看：

- `proxy.py` 中的 `build_upstream_headers`
- `proxy.py` 中的 `HOP_BY_HOP_HEADERS`

### 6.3 修改时的原则

修改这类兼容代理时，优先遵守下面几条：

- 优先改判断条件，不要一上来就改 body
- 优先收紧职责，不要顺手做成通用网关
- 优先保持 `Authorization` 透明透传
- 优先保持默认只监听 `127.0.0.1`
- 增加新兼容规则时，必须同步补测试

## 7. 如何判断一个新问题是否应该在这里修

出现新问题时，先问 3 个问题：

1. 问题是不是“客户端请求和上游协议之间的兼容性错位”？
2. 问题能不能通过极小的透明改写解决？
3. 修复后会不会明显扩大这个项目的职责边界？

如果答案分别是：

- 是
- 能
- 不会

那这个问题适合继续在这里修。

如果答案变成：

- 需要多 provider 路由
- 需要本地 key 管理
- 需要用户界面
- 需要策略控制
- 需要共享给多人

那就说明你需要的是另一个层级的系统，而不是继续给这个项目堆功能。

## 8. 详细使用指南

### 8.1 准备环境

要求：

- Python 3.11 及以上
- 建议安装 `uv`

复制配置：

```bash
cd /path/to/cursor-openai-compat-proxy
cp .env.example .env
```

默认配置中，上游地址已经指向：

- `https://your-openai-compatible-endpoint.example/v1`

### 8.2 本地开发运行

```bash
cd /path/to/cursor-openai-compat-proxy
set -a
source .env
set +a
uv run --with . cursor-openai-compat-proxy
```

启动后，本地监听：

- `http://127.0.0.1:4000`

### 8.3 Docker 运行

```bash
cd /path/to/cursor-openai-compat-proxy
docker compose up -d --build
```

查看日志：

```bash
cd /path/to/cursor-openai-compat-proxy
docker compose logs -f
```

停止：

```bash
cd /path/to/cursor-openai-compat-proxy
docker compose down
```

### 8.4 Cursor 中如何填写

- Base URL：`http://127.0.0.1:4000/v1`
- API Key：填写真实上游 key
- Model：填写你在上游要使用的模型，例如 `gpt-5.4`

注意：

- 这里的 API Key 不是本地代理 key
- 它会被原样透传到上游

### 8.5 快速验证

健康检查：

```bash
curl -fsS http://127.0.0.1:4000/healthz
```

验证代理是否透传模型列表：

```bash
curl -fsS \
  -H "Authorization: Bearer <your-upstream-key>" \
  http://127.0.0.1:4000/v1/models
```

验证条件式改写：

```bash
curl -sS -D - \
  -H "Authorization: Bearer <your-upstream-key>" \
  -H "Content-Type: application/json" \
  http://127.0.0.1:4000/v1/chat/completions \
  -d '{
    "model": "gpt-5.4",
    "input": "hello",
    "stream": false
  }'
```

如果命中改写，响应头中会出现：

- `x-cursor-compat-rewrite: 1`
- `x-cursor-compat-upstream-path: /v1/responses`

### 8.6 运行测试

```bash
cd /path/to/cursor-openai-compat-proxy
uv run --with '.[dev]' pytest
```

这里对 `.[dev]` 加了引号，是为了避免 zsh 把方括号当成 glob 处理。

## 9. 后续维护建议

- 先观察 Cursor 后续版本是否改变请求格式
- 如果未来确认问题完全消失，可以保留这个项目但不常驻运行
- 如果未来要共享给多人使用，不要直接扩大监听地址，应先重做鉴权与边界设计
- 如果未来出现第二类、第三类兼容问题，先判断是否仍然属于“极薄兼容层”的合理职责
