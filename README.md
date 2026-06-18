# Kino Wien TRMNL

A [TRMNL](https://usetrmnl.com/) plugin that displays Falter.at's recommended films currently showing in Vienna. Four films are picked at random each run and shown in a 2×2 grid with poster, director, genre, and upcoming showtimes.

## How it works

- Scrapes `falter.at/kino` for recommended films in Vienna (cached daily)
- Picks 4 films at random and fetches their showtimes from the detail pages
- POSTs the result to your TRMNL webhook

## Running with Docker

The easiest way is via the provided Docker Compose file. Create a `.env` file next to it:

```
TRMNL_WEBHOOK_URL=https://usetrmnl.com/api/custom_plugins/YOUR_PLUGIN_ID
```

Then start the container:

```bash
docker compose up -d
```

The scraper runs immediately on start and then every 30 minutes. The daily film list is cached in a named Docker volume so restarts don't re-fetch unnecessarily.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `TRMNL_WEBHOOK_URL` | required | Your TRMNL private plugin webhook URL |
| `INTERVAL` | `1800` | Seconds between runs |

## TRMNL plugin setup

1. Create a new **Private Plugin** in the TRMNL dashboard
2. Copy the webhook URL into `TRMNL_WEBHOOK_URL`
3. Paste the contents of `template.html` as the plugin template
