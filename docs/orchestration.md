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
  `text` or `jobs`. `preview_discord_message` builds the same message without
  sending

### What a job send posts

A job send posts one Discord message with one attached file:

```
**Job digest — Saturday, 21 November 2026**

*Scraped 12 jobs across 2 keyword(s) and 3 site(s). Errors: 1.*
```

- The date is today in Asia/Jakarta
- The attached file is `jobs-YYYY-MM-DD.md`, with the same Jakarta date. It
  holds every job filled into `message_template`, jobs split by a `---` line.
  No job is cut or dropped. The file must stay under 10,000,000 bytes
- `max_chars` does not apply to job sends. It is kept for older setups
- `send_discord_message` and `preview_discord_message` take optional
  `keyword_count`, `site_count` and `error_count` for the italic line. Left out,
  they default to the distinct `matched_keyword` values, the distinct `site`
  values, and 0
- `preview_discord_message` returns `{ok, messages, files}`. `files` is
  `[{file_name, file_text}]`, empty for a text message
- With mention on and a `mention_user_id` saved, the message starts with a
  mention of that user. A mention inside job text never pings anyone

A UI run passes its own counts: the keywords and sites it searched and its
error count. `discord_sent` and `discord_failed` on the run record count jobs.

Free text is unchanged: one text message, up to 2000 characters with the
mention. A UI run that found 0 jobs or failed posts one text message instead of
a digest, for example `python on glints found 0 jobs`.
