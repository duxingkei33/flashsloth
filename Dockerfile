FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY . .

# 安全：首次启动自动生成随机admin账号
# debug关闭，secret_key从环境变量读取
ENV FLASK_DEBUG=0
ENV SECRET_KEY=""
ENV FLASHSLOTH_HOST=0.0.0.0
ENV FLASHSLOTH_PORT=5000

EXPOSE 5000

# 首次启动自动生成随机账号，无debug模式
CMD python3 admin.py --host 0.0.0.0 --port 5000
