FROM python:3.12-alpine
WORKDIR /app
COPY iobroker_server.py .
EXPOSE 8080
CMD ["python3", "-u", "iobroker_server.py"]
