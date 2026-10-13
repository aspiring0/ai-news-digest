FROM python:3.12-slim

WORKDIR /srv

# 装依赖（先拷 requirements，利用层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷代码
COPY app/ ./app/
COPY templates/ ./templates/

# 数据目录（docker-compose 会挂载卷到这里）
VOLUME /data
ENV DB_PATH=/data/news.db
ENV TZ=Asia/Shanghai

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
