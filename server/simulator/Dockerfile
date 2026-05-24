FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir aiohttp
EXPOSE 3000
CMD ["python", "sim.py"]
