# Proxy

OpenCode 代理服务，让 AI 编程 Agent 作为辩手参与辩论。

## 概述

通过 OpenAI-compatible 本地 HTTP 代理，将 OpenCode 会话包装为辩论参与者。每个 Agent 在独立工作区中运行，可在辩论过程中实时探索代码库。

## 脚本

### opencode_proxy.py

代理服务器本体。启动一个 OpenAI-compatible HTTP 服务，将请求转发给 OpenCode 会话。

### debate_with_opencode.py

启动器。解析 topic 文件，自动为 localhost-proxy 类型的辩手启动 `opencode_proxy`，然后拉起辩论。

## 用法

```bash
python3 scripts/proxy/debate_with_opencode.py <topic.md>
```

## proxy_workspace/

代理运行时的工作目录，每个辩手实例使用独立的隔离工作区。
