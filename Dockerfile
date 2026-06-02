FROM python:3.12-alpine
WORKDIR /app
COPY iobroker_server.py .
COPY states.txt /config/states.txt
CMD ["python3", "iobroker_server.py"]