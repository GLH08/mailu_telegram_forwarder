# 使用官方 Python 运行时作为父镜像
FROM python:3.9-slim

# 设置工作目录，我们的应用程序包将位于此目录下
WORKDIR /usr/src/project

# 复制 requirements.txt 到工作目录
COPY requirements.txt .

# 安装 requirements.txt 中指定的任何所需包
RUN pip install --no-cache-dir -r requirements.txt

# 将你的本地 'app' 目录 (作为 Python 包) 复制到容器的 WORKDIR 下
# 这将在容器内创建 /usr/src/project/app
COPY ./app ./app

# 定义环境变量
ENV PYTHONUNBUFFERED 1

# 将工作目录添加到 PYTHONPATH，确保 Python 能找到 app 包
# 当使用 -m 时，Python 通常会自动处理当前工作目录的路径，
# 但显式添加 PYTHONPATH 可以为某些边缘情况提供更强的保障。
ENV PYTHONPATH "${PYTHONPATH}:/usr/src/project"

# 将 'app' 包中的 'main' 模块作为脚本运行
CMD ["python", "-m", "app.main"]
