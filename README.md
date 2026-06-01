# ioBroker Dashboard

A minimal Python web server that fetches live values from an ioBroker
simple-api instance and serves a self-contained HTML dashboard.

## Configuration

Edit the environment variables in `docker-compose.yml`:

| Variable          | Description                          | Default                        |
|-------------------|--------------------------------------|--------------------------------|
| `IOBROKER_HOST`   | URL of ioBroker simple-api           | http://192.168.178.53:8087     |
| `IOBROKER_STATES` | Comma-separated list of state IDs    | (three zigbee example states)  |
| `LISTEN_PORT`     | Port the server listens on           | 8080                           |
| `FETCH_TIMEOUT`   | Seconds before ioBroker request dies | 5                              |

## Deploy via Portainer

1. Push this repo to GitHub (or any Git host)
2. In Portainer → Stacks → Add stack → Git repository
3. Enter the repo URL
4. Set the compose file path to `docker-compose.yml`
5. Deploy — Portainer will build the image from the Dockerfile

## Run locally

```bash
docker compose up -d
```

Open http://localhost:8080
