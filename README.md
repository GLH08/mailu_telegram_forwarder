# Mailu Telegram Forwarder

一个强大且高度可配置的工具，用于将来自 Mailu (或其他 IMAP 兼容邮箱) 的邮件自动转发到 Telegram。它不仅能转发邮件的基本信息，还提供了丰富的自定义选项，以优化您的通知体验。

## ✨ 特性

*   **实时邮件监控**: 通过 IMAP IDLE 近乎实时地接收新邮件通知。
*   **内容解析**:
    *   智能解析邮件头部 (主题, 发件人, 收件人, 抄送, 日期, Message-ID)。
    *   提取邮件正文。对于 HTML 格式的邮件，优先尝试将其**渲染为图片**发送，以最大限度保留原始排版和视觉效果。
        *   如果 HTML 转图片失败或邮件无 HTML 内容，则回退到将 HTML 内容转换为 Markdown (优先使用 `markdownify`，支持 `html2text`, `BeautifulSoup` 作为备选) 或使用纯文本正文。
        *   **长图片自动分割**：当渲染后的邮件图片过高导致无法直接发送时，会自动将其垂直切割成多张较小的图片分部分发送。
    *   提取附件信息。
*   **高度可配置的Telegram消息**:
    *   **邮件正文图片化**：HTML 邮件正文默认尝试以图片形式发送，邮件头部信息作为图片的说明文字。
    *   **自定义邮件头显示**: 用户可以通过 `TELEGRAM_HEADER_FIELDS` 选择在 Telegram 消息中显示哪些邮件头部信息 (如主题, 发件人, 日期, 重要性等)。
    *   **重要性标记**: 自动检测邮件的重要性 (高/低)，并在 Telegram 消息中以特殊图标 (❗/📉) 突出显示。
    *   **引用处理**: 用户可以通过 `EMAIL_QUOTE_HANDLING` 自定义如何处理邮件中的引用内容 (移除, 转为Markdown引用, 或仅保留文本)，此处理应用于文本回退模式。
    *   **图片附件预览**: 可选将支持的图片类型附件 (JPG, PNG, GIF) 直接作为图片预览发送，而非普通文件 (通过 `TELEGRAM_IMAGE_PREVIEW` 和 `TELEGRAM_IMAGE_PREVIEW_MAX_SIZE_MB` 控制)。
*   **细粒度转发规则**:
    *   **发件人过滤**: 支持基于正则表达式的发件人黑名单 (`FILTER_SENDER_BLACKLIST_REGEX`) 和白名单 (`FILTER_SENDER_WHITELIST_REGEX`)。
    *   **主题过滤**: 支持基于正则表达式的主题黑名单 (`FILTER_SUBJECT_BLACKLIST_REGEX`)。
    *   **内容转发控制**: 可分别控制是否转发邮件正文 (`FORWARD_BODY`) 和附件 (`FORWARD_ATTACHMENTS`)。
*   **健壮的连接管理**:
    *   采用指数退避策略进行 IMAP 连接重试。
    *   在连续多次连接失败后会进行更长时间的暂停，以避免对服务器造成过多请求。
*   **邮件处理**:
    *   成功转发后，可选择将邮件标记为已读，或移动到指定的已处理文件夹 (`PROCESSED_FOLDER_NAME`)。
*   **易于部署**: 提供 `Dockerfile` 和 `docker-compose.yml` 文件，方便 Docker 化部署。
*   **日志记录**: 详细的日志输出，可配置日志级别 (`LOG_LEVEL`)。

## 🛠️ 技术栈

*   Python 3.9+
*   `imapclient`: IMAP 交互
*   `python-telegram-bot` (v13.x): Telegram Bot API 通信
*   `python-dotenv`: 环境变量管理
*   `markdownify`: HTML 到 Markdown 转换 (文本回退模式)
*   `html2text`: HTML 到文本转换 (文本回退模式备选)
*   `BeautifulSoup4`: HTML 解析 (文本回退模式备选)
*   `imgkit`: HTML 到图片转换，依赖 `wkhtmltopdf`。
*   `Pillow`: 图像处理库，用于图片分割。
*   `chardet`: 字符编码检测
*   `asyncio`: 异步 I/O
*   Docker & Docker Compose

## 📁 项目结构

```
mailu_telegram_forwarder/
├── .env.example             # 环境变量示例文件
├── app/                     # 核心应用代码目录
│   ├── __init__.py          # 包标记
│   ├── config.py            # 配置加载与验证
│   ├── email_parser.py      # 邮件解析与格式化
│   ├── imap_handler.py      # IMAP 服务器交互与邮件监控
│   ├── main.py              # 应用主入口与事件循环
│   └── telegram_sender.py   # Telegram 消息发送
├── docker-compose.yml       # Docker Compose 配置文件
├── Dockerfile               # Docker 镜像构建文件
├── optimization_plan.md     # (开发用) 优化计划文档
├── analysis_report.md       # (开发用) 初始代码分析报告
└── requirements.txt         # Python 依赖列表
```

## 🚀 安装与部署

### 使用 Docker (推荐)

1.  **克隆项目** (如果您尚未这样做):
    ```bash
    git clone <repository_url>
    cd mailu_telegram_forwarder
    ```
2.  **创建并配置 `.env` 文件**:
    复制 `.env.example` 为 `.env`:
    ```bash
    cp .env.example .env
    ```
    然后编辑 `.env` 文件，填入您的配置信息 (详见下面的“配置”部分)。
    确保您的系统已安装 Docker 和 Docker Compose。
3.  **构建并启动 Docker 容器**:
    ```bash
    docker-compose up -d --build
    ```
    此命令会根据 `Dockerfile` 构建镜像，其中包含了安装 `wkhtmltopdf` 等系统依赖的步骤。服务将在后台运行。

    查看日志:
    ```bash
    docker-compose logs -f mail_forwarder
    ```

### 本地运行 (用于开发或不使用 Docker 的情况)

1.  **克隆项目**。
2.  **创建并配置 `.env` 文件** (同上)。
3.  **创建虚拟环境并安装依赖**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate    # Windows
    pip install -r requirements.txt
    ```
4.  **运行应用**:
    ```bash
    python -m app.main
    ```

## ⚙️ 配置

所有配置均通过项目根目录下的 `.env` 文件进行管理。请从 `.env.example` 复制创建，并根据您的需求修改。

### IMAP 服务器配置

*   `IMAP_HOST`: (必需) 您的 Mailu IMAP 服务器域名或 IP 地址。
    *   示例: `mail.example.com`
*   `IMAP_PORT`: (必需) IMAP 服务器端口，SSL/TLS 通常为 `993`。
    *   示例: `993`
*   `IMAP_USER`: (必需) 登录 IMAP 服务器的邮箱用户名。
    *   示例: `user@example.com`
*   `IMAP_PASSWORD`: (必需) 对应的邮箱密码。
    *   示例: `yourSecretPassword`
*   `IMAP_MAILBOX`: (可选) 需要监控的邮箱文件夹名称。
    *   默认值: `INBOX`
    *   示例: `INBOX` 或 `"MyFolder/SubFolder"`

### Telegram Bot 配置

*   `TELEGRAM_BOT_TOKEN`: (必需) 从 BotFather 获取的您的 Telegram Bot API Token。
    *   示例: `1234567890:AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPpQq`
*   `TELEGRAM_CHAT_ID`: (必需) 目标 Telegram 聊天或用户的唯一 ID，邮件将被转发到这里。
    *   示例: `123456789` (个人用户ID) 或 `-1001234567890` (群组/频道ID)

### 日志与邮件处理配置

*   `LOG_LEVEL`: (可选) 应用的日志记录级别。
    *   可选值: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
    *   默认值: `INFO`
*   `PROCESSED_FOLDER_NAME`: (可选) 邮件成功转发后，将其移动到 IMAP 服务器上的此文件夹内。如果留空或未设置，则仅将邮件标记为已读 (`\Seen`)。
    *   示例: `ForwardedToTelegram` 或留空

### 内容呈现与格式化配置

*   `EMAIL_QUOTE_HANDLING`: (可选) 定义如何处理邮件中的引用文本。
    *   可选值:
        *   `markdown` (默认): 将引用转换为 Markdown 格式 (例如 `> 引用内容`)。
        *   `remove`: 完全移除所有检测到的引用内容。
        *   `preserve_text`: 保留引用文本，但移除行首的 `>` 等引用符号。
    *   示例: `EMAIL_QUOTE_HANDLING=markdown`
*   `TELEGRAM_HEADER_FIELDS`: (可选) 定义在 Telegram 消息中显示的邮件头部字段，以逗号分隔。
    *   可用字段: `subject`, `from`, `to`, `cc`, `date`, `importance`, `message_id`
    *   默认值: `subject,from,date`
    *   示例: `TELEGRAM_HEADER_FIELDS=subject,from,date,to,cc,importance`
*   `TELEGRAM_IMAGE_PREVIEW`: (可选) 是否尝试将图片附件作为预览发送。
    *   可选值: `true`, `false`
    *   默认值: `false`
    *   示例: `TELEGRAM_IMAGE_PREVIEW=true`
*   `TELEGRAM_IMAGE_PREVIEW_MAX_SIZE_MB`: (可选) 图片预览的最大文件大小 (MB)。超过此大小的图片仍将作为普通文件附件发送。
    *   默认值: `5.0`
    *   示例: `TELEGRAM_IMAGE_PREVIEW_MAX_SIZE_MB=10.0`

### 邮件过滤与内容控制配置

*   `FILTER_SENDER_BLACKLIST_REGEX`: (可选) 基于正则表达式的发件人黑名单。匹配此表达式的发件人的邮件将被忽略。
    *   示例: `.*@spamdomain\.com` (忽略来自 spamdomain.com 的所有邮件)
    *   示例: `(baduser@example\.com|another@spam\.net)` (忽略特定发件人)
*   `FILTER_SENDER_WHITELIST_REGEX`: (可选) 基于正则表达式的发件人白名单。如果设置此项，则只有匹配此表达式的发件人的邮件才会被处理，此时发件人黑名单将失效。
    *   示例: `.*@importantdomain\.com` (只处理来自 importantdomain.com 的邮件)
*   `FILTER_SUBJECT_BLACKLIST_REGEX`: (可选) 基于正则表达式的主题黑名单。匹配此表达式的主题的邮件将被忽略。
    *   示例: `^\[SPAM\]` (忽略主题以 "[SPAM]" 开头的邮件)
*   `FORWARD_ATTACHMENTS`: (可选) 是否转发邮件附件。
    *   可选值: `true`, `false`
    *   默认值: `true`
    *   示例: `FORWARD_ATTACHMENTS=false` (不转发任何附件)
*   `FORWARD_BODY`: (可选) 是否转发邮件正文。
    *   可选值: `true`, `false`
    *   默认值: `true`
    *   示例: `FORWARD_BODY=false` (不转发邮件正文，可能只想要头部信息和附件通知)

## 📖 使用方法

1.  确保已按照“安装与部署”部分正确配置并启动了应用。
2.  应用启动后，会自动连接到指定的 IMAP 服务器并开始监控指定邮箱 (`IMAP_MAILBOX`) 中的新邮件。
3.  当新邮件到达时：
    *   应用会首先根据配置的过滤规则 (发件人白/黑名单, 主题黑名单) 判断是否需要处理该邮件。
    *   如果邮件通过过滤，应用会解析邮件内容。
    *   根据 `FORWARD_BODY` 和 `FORWARD_ATTACHMENTS` 配置，决定是否包含正文和附件。
    *   **HTML 邮件正文处理**：
        *   如果邮件包含 HTML 内容且 `FORWARD_BODY` 为 `true`，应用会首先尝试将 HTML 正文渲染成一张或多张图片（如果过长则自动分割）发送到 Telegram，邮件头部信息将作为图片的说明文字。
        *   如果 HTML 转图片失败，或者邮件不含 HTML 内容，应用将回退到发送文本格式的正文。此时，会根据 `EMAIL_QUOTE_HANDLING` 处理邮件引用，并根据 `TELEGRAM_HEADER_FIELDS` 格式化邮件头部信息（如果图片发送失败，头部信息会单独发送）。
    *   **附件处理**：根据 `TELEGRAM_IMAGE_PREVIEW` 尝试发送图片附件的预览。
    *   最终将格式化后的消息（图片或文本）和附件（如果配置转发）发送到指定的 `TELEGRAM_CHAT_ID`。
    *   成功转发后，邮件会在 IMAP 服务器上被标记为已读或移动到 `PROCESSED_FOLDER_NAME` (如果已配置)。
4.  监控应用日志以了解其运行状态和任何潜在问题。

## 🤝 贡献

欢迎各种形式的贡献！如果您有任何建议、发现 bug 或希望添加新功能，请随时创建 Issue 或提交 Pull Request。

## 📄 许可证

本项目当前未指定明确的开源许可证。