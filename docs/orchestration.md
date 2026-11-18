# Orchestration

This project has no scheduler. Scheduled runs come from a separate service
outside this project (a Kubernetes CronJob in another repo).

## Discord posting

Discord posting uses the Discord settings stored in Mongo (`discord_settings`):
bot token, channel, `message_template`, `max_chars`. Edit them in the Discord
section of the UI. Unset template and cap use the defaults in
`mcp_server/discord_settings.py`.

Two ways to post:

- **UI run** — turn on **Notify Discord** before starting a run. The jobs are
  posted when the run ends
- **MCP tool** — call `send_discord_message` with a `channel_id` and either
  `text` or `jobs`. `preview_discord_message` shows the same messages without
  sending
