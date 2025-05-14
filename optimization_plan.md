# Mailu Telegram Forwarder 详细优化计划

**目标：** 全面提升 `mailu-telegram-forwarder` 的用户体验、功能丰富度、系统健壮性和可配置性。

**第一部分：邮件内容呈现与可读性优化**

1.  **HTML 内容解析与格式化增强 (优先级：高)**
    *   **目标：** 更准确、美观地将 HTML 邮件内容转换为适合 Telegram 阅读的格式。
    *   **具体措施：**
        *   **主要转换引擎：** 评估并优先选用 `markdownify` 库进行 HTML 到 Markdown 的转换，以期获得最佳的结构保留（如列表、表格、代码块）。
        *   **备选与补充：** 保留 `html2text` 作为备选，或用于特定场景（例如，当 `markdownify` 处理复杂或损坏的 HTML 出错时）。进一步优化 `html2text` 的配置，特别是针对链接和图片 `alt` 文本的显示。
        *   **表格处理：** 确保 HTML 表格能被转换为 Markdown 表格。如果 Markdown 表格在 Telegram 中显示效果不佳，则转换为易于阅读的文本列表格式。
        *   **特殊元素处理：** 优化对邮件中常见但非标准 HTML 元素（如某些邮件客户端产生的特定 `<div>` 结构）的识别和处理。
2.  **邮件引用处理的用户自定义选项 (优先级：高)**
    *   **目标：** 允许用户根据自己的偏好选择如何处理邮件中的引用内容。
    *   **具体措施：**
        *   通过环境变量（例如 `EMAIL_QUOTE_HANDLING`）提供以下选项：
            *   `remove`: 完全移除所有引用内容。
            *   `markdown`: 将引用内容转换为 Markdown 的引用格式 (`> `)。
            *   `preserve_text`: 保留引用文本，但移除 `>` 等引用符号。
            *   `tag_and_collapse` (高级/可选): 标记引用块，并尝试在 Telegram 中默认折叠。
        *   更新 `cleanup_quote_symbols` 或引入新的处理函数以实现这些选项。
3.  **邮件头部信息展示优化 (优先级：中)**
    *   **目标：** 使邮件头部信息更简洁、易读，并可配置。
    *   **具体措施：**
        *   **默认展示：** 默认清晰展示主题、发件人、日期。
        *   **可选字段：** 通过环境变量（例如 `TELEGRAM_HEADER_FIELDS`）允许用户选择显示/隐藏收件人、抄送等字段。
        *   **视觉分隔：** 使用更美观的 Unicode 符号或 Markdown 分隔符来组织头部信息。
        *   **重要性标记：** 如果邮件包含 `Importance` 头，在 Telegram 消息中以醒目标识（如 ❗）展示。
4.  **附件处理增强 (优先级：中)**
    *   **目标：** 提升附件在 Telegram 中的呈现方式和信息量。
    *   **具体措施：**
        *   **图片预览：** 对常见图片格式附件（如 JPG, PNG, GIF），如果文件大小在 Telegram 允许范围内（例如 < 5MB），尝试直接作为图片消息发送预览，而非仅作为文件。提供环境变量（例如 `TELEGRAM_IMAGE_PREVIEW=true/false`）控制此行为。
        *   **文件名清晰化：** 确保附件文件名在 Telegram 中正确显示，特别是包含特殊字符或多语言的文件名。
5.  **长邮件与摘要处理 (优先级：低)**
    *   **目标：** 改善非常长的邮件在 Telegram 中的阅读体验。
    *   **具体措施：**
        *   **自动摘要：** 对于超过特定长度（例如 3000 字符）的邮件正文，自动提取前 N 个字符或句子作为摘要发送，并在末尾附加一个提示，如“_(邮件过长，已截断)_”。
        *   **智能分割：** 优化 `split_message` 函数，使其在分割点上更智能，例如尽量在段落结束处分割。

**第二部分：用户配置与交互性增强**

1.  **细粒度转发规则配置 (优先级：高)**
    *   **目标：** 赋予用户更大的控制权，决定哪些邮件被转发以及如何转发。
    *   **具体措施：**
        *   **发件人/收件人/主题过滤：** 通过环境变量实现基于正则表达式的黑名单/白名单过滤。
            *   `FILTER_SENDER_BLACKLIST_REGEX`
            *   `FILTER_SENDER_WHITELIST_REGEX` (如果设置，则黑名单失效)
            *   `FILTER_SUBJECT_BLACKLIST_REGEX`
        *   **附件转发控制：** 环境变量 `FORWARD_ATTACHMENTS=true/false` 控制是否转发附件。
        *   **正文转发控制：** 环境变量 `FORWARD_BODY=true/false` 控制是否转发邮件正文。
2.  **Telegram Bot 命令交互 (优先级：中)**
    *   **目标：** 提供通过 Telegram Bot 管理和监控服务的基本能力。
    *   **具体措施：** 实现以下 Bot 命令：
        *   `/status`: 显示服务当前运行状态。
        *   `/pause_forwarding`: 暂时停止新的邮件转发。
        *   `/resume_forwarding`: 恢复邮件转发。
        *   `/test_connection`: 主动测试与 IMAP 服务器的连接和登录。
        *   `/get_config`: (安全考虑，可选) 显示当前部分非敏感配置。
        *   `/help`: 显示可用命令列表和说明。
3.  **增强型错误与状态通知 (优先级：中)**
    *   **目标：** 更及时、更清晰地向用户反馈服务状态和问题。
    *   **具体措施：**
        *   **关键错误通知：** 对于 IMAP 认证失败、Telegram Bot Token 无效、连续连接失败等严重问题，通过 Telegram 向 `TELEGRAM_CHAT_ID` 发送告警消息。
        *   **配置错误提示：** 启动时如果检测到 `.env` 文件中关键配置缺失或格式错误，在日志中明确指出，并尝试通过 Telegram 发送启动失败通知。

**第三部分：系统健壮性与性能**

1.  **智能重试与连接管理 (优先级：高)**
    *   **目标：** 提高服务在网络波动或临时服务不可用时的自我恢复能力。
    *   **具体措施：**
        *   在 `imap_handler.py` 中针对 IMAP 连接和操作引入更完善的重试逻辑，采用指数退避算法。
        *   区分永久性错误（如认证失败）和临时性错误（如网络超时），前者不应无限重试。
        *   优化 IMAP `IDLE` 模式的保活和超时处理。
2.  **异步任务处理优化 (优先级：中)**
    *   **目标：** 确保应用高效处理并发任务，避免阻塞。
    *   **具体措施：**
        *   全面审查代码，确保所有涉及网络 I/O 的操作都通过 `asyncio` 正确管理。
        *   对于 CPU 密集型任务，评估是否需要移至 `ThreadPoolExecutor`。

**第四部分：安全性**

1.  **敏感信息过滤选项 (优先级：低)**
    *   **目标：** 提供基础的内容过滤能力。
    *   **具体措施：**
        *   通过环境变量允许用户定义一组正则表达式和替换文本。
        *   **注意：** 此功能实现复杂且效果有限，需明确告知用户其局限性。

**整体架构和流程图 (Mermaid):**

```mermaid
graph LR
    subgraph "用户配置 (.env)"
        direction LR
        C1[IMAP设置]
        C2[Telegram设置]
        C3[日志级别]
        C4[处理后文件夹]
        C5[新增: 引用处理方式 EMAIL_QUOTE_HANDLING]
        C6[新增: 头部字段 TELEGRAM_HEADER_FIELDS]
        C7[新增: 图片预览 TELEGRAM_IMAGE_PREVIEW]
        C8[新增: 过滤规则 FILTER_...]
        C9[新增: 附件/正文转发开关 FORWARD_ATTACHMENTS/BODY]
    end

    subgraph "应用核心 (app/)"
        direction TB
        M[main.py: 启动与信号处理] --> IH[imap_handler.py: IMAP交互];
        IH -- 新邮件 --> EP[email_parser.py: 解析邮件];
        EP -- 解析结果 --> TS[telegram_sender.py: 发送至Telegram];
        
        subgraph "email_parser.py 增强"
            EP1[HTML解析 (markdownify/html2text)]
            EP2[引用处理 (根据C5配置)]
            EP3[头部信息提取]
            EP4[附件提取]
            EP5[长邮件摘要 (可选)]
        end
        EP --> EP1; EP --> EP2; EP --> EP3; EP --> EP4; EP --> EP5;

        subgraph "telegram_sender.py 增强"
            TS1[格式化消息 (根据C6, C7)]
            TS2[Bot命令处理 (部分逻辑)]
            TS3[错误通知发送]
            TS4[附件发送逻辑 (含预览)]
        end
        TS --> TS1; TS --> TS2; TS3 --> TS; TS --> TS4;
        
        CONF[config.py: 加载所有配置] --> IH;
        CONF --> EP;
        CONF --> TS;
        CONF --> M;
    end
    
    U[用户] -- 操作 --> TG_BOT[Telegram Bot];
    TG_BOT -- 命令 --> TS2;
    TS -- 消息/文件 --> TG_BOT;
    TG_BOT -- 消息 --> U;

    IMAP[IMAP服务器] <--> IH;

    style U fill:#c9f,stroke:#333,stroke-width:2px
    style TG_BOT fill:#9cf,stroke:#333,stroke-width:2px
    style IMAP fill:#f9c,stroke:#333,stroke-width:2px