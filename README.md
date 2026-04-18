# cursor-openai-compat-proxy

一个极薄的本机兼容代理，专门修复 Cursor 在 Base URL override 场景下，把 Responses 风格请求体误发到 `/v1/chat/completions` 的问题。

## 这个项目做什么

- 只监听 `127.0.0.1`
- 不做本地鉴权
- 不保存或替换上游 API Key
- 直接透传客户端传入的 `Authorization: Bearer ...`
- 仅在命中已知错配时，把 `/v1/chat/completions` 改写到 `/v1/responses`
- 其余路径、请求体、流式响应全部透传

## 为什么存在这个项目

Cursor 在 Base URL override 场景下，可能会把 Responses 风格的请求体发到 `/v1/chat/completions`。  
这会让上游严格的 Chat Completions 处理器返回类似下面的错误：

- `field messages is required`

这个项目不改 body，不做协议转换，只做最小的路径纠正。

完整背景、设计初衷、迁移影响、代码修改策略和详细使用指南见：

- [设计与维护指南](docs/design-and-maintenance.md)

## 何时会改写

仅当同时满足以下条件时，代理才会改写到上游 `/v1/responses`：

- 请求方法为 `POST`
- 路径为 `/v1/chat/completions`
- `Content-Type` 为 JSON
- 请求体中存在 `input`
- 请求体中不存在 `messages`

其余请求都按原路径透传。

## 快速开始

复制示例环境变量：

```bash
cp .env.example .env
```

环境变量说明：

- `LISTEN_HOST`：监听地址，默认 `127.0.0.1`
- `LISTEN_PORT`：监听端口，默认 `4000`
- `UPSTREAM_BASE_URL`：上游 OpenAI-compatible 根地址，必须以 `/v1` 结尾
- `REQUEST_TIMEOUT_SECONDS`：上游请求超时，默认 `600`
- `LOG_LEVEL`：日志级别，默认 `INFO`

### 本地运行

推荐使用 `uv`：

```bash
cd /path/to/cursor-openai-compat-proxy
uv run --with . --env-file .env cursor-openai-compat-proxy
```

如果你的 `uv` 版本不支持 `--env-file`，可以这样运行：

```bash
cd /path/to/cursor-openai-compat-proxy
set -a
source .env
set +a
uv run --with . cursor-openai-compat-proxy
```

### Docker 运行

```bash
cd /path/to/cursor-openai-compat-proxy
docker compose up -d --build
```

停止：

```bash
cd /path/to/cursor-openai-compat-proxy
docker compose down
```

默认只绑定到本机：

- `127.0.0.1:4000:4000`

## Cursor 配置

Cursor 中填写：

- Model：你在上游使用的模型名，例如 `gpt-5.4`
- Base URL：`http://127.0.0.1:4000/v1`
- API Key：直接填写你原本要发给上游 `new-api` 的真实 key

也就是说，这个代理不会替你持有 key，而是原样透传到上游。

## 验证

健康检查：

```bash
curl -fsS http://127.0.0.1:4000/healthz
```

验证模型列表透传：

```bash
curl -fsS \
  -H "Authorization: Bearer <your-upstream-key>" \
  http://127.0.0.1:4000/v1/models
```

验证路径改写：

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

如果命中改写，响应头会带上：

- `x-cursor-compat-rewrite: 1`
- `x-cursor-compat-upstream-path: /v1/responses`

## 测试

```bash
cd /path/to/cursor-openai-compat-proxy
uv run --with '.[dev]' pytest
```

这里对 `.[dev]` 加了引号，是为了避免 zsh 把方括号当成 glob 处理。
