FROM python:3.12-alpine
RUN mkdir /config
WORKDIR /app
COPY iobroker_server.py .
CMD ["python3", "iobroker_server.py"]