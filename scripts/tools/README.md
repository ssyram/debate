# Tools

日志格式转换与迁移工具。

## convert_json_log_to_md.py

将 JSON 辩论日志转换为可读的 Markdown 格式。

### 用法

```bash
python3 scripts/tools/convert_json_log_to_md.py <log.json> [--output FILE] [--stdout]
```

### 选项

| 选项 | 说明 |
|------|------|
| `--output FILE` | 输出文件路径（默认：`<stem>_debate_log.md`） |
| `--stdout` | 输出到终端而非文件 |

### 示例

```bash
python3 scripts/tools/convert_json_log_to_md.py debate_log.json --stdout
```

## convert_md_log_to_json.py

将旧版 Markdown 辩论日志转换为 JSON 格式（用于 resume / compact）。

### 用法

```bash
python3 scripts/tools/convert_md_log_to_json.py <log.md> [--output FILE]
```

### 选项

| 选项 | 说明 |
|------|------|
| `--output FILE` | 输出文件路径（默认：`<stem>_debate_log.json`） |

### 示例

```bash
python3 scripts/tools/convert_md_log_to_json.py debate_log.md
```

## migrate_v1_to_v2.py

将 v1 格式日志迁移到 v2 格式。

### 用法

```bash
python3 scripts/tools/migrate_v1_to_v2.py TOPIC_FILE LOG_FILE [--output OUTPUT]
```

### 示例

```bash
python3 scripts/tools/migrate_v1_to_v2.py topic.md v1_log.json --output v2_log.json
```
