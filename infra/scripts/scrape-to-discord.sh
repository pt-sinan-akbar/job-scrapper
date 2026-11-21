#!/usr/bin/env bash
set -euo pipefail
shopt -s inherit_errexit

UI_URL="${SCRAPER_UI_URL:-}"
readonly UI_URL="${UI_URL%/}"
readonly BEARER_TOKEN="${AUTH_TOKEN:-}"
readonly SITES=(linkedin glints jobstreet indeed)
readonly REQUEST_TIMEOUT_SECONDS=30
readonly POLL_SECONDS=5
readonly SCRAPE_TIMEOUT_SECONDS=1800
readonly DISCORD_START_GRACE_SECONDS=60
readonly MAX_FAILED_POLLS=3
readonly SCRAPE_STATUS_IN_PROGRESS="running"
readonly SCRAPE_STATUS_FAILED="failed"
readonly DISCORD_STATUS_SENDING="sending"
readonly DISCORD_STATUS_SENT="sent"

main() {
    case "${1:-}" in
        -h | --help)
            print_usage
            return
            ;;
    esac
    (( $# <= 1 )) || exit_with_usage

    local keyword="${1:-}"
    [[ -n "${keyword//[[:space:]]/}" ]] || exit_with_error "No keyword, pass one like \"data analyst\""

    validate_requirements

    local scrape_id
    scrape_id="$(start_scrape "$keyword")"
    echo "Started scrape $scrape_id for \"$keyword\" on ${SITES[*]}"

    wait_for_discord_send "$scrape_id"

    local scrape_report
    scrape_report="$(read_scrape_report "$scrape_id")"
    print_scrape_outcome "$scrape_report"
    exit_unless_scraped_and_sent "$scrape_report"
}

print_usage() {
    cat <<USAGE
Usage: $(basename "$0") <keyword>

Scrape one keyword on ${SITES[*]}, then post the jobs to Discord
Every other setting comes from the job settings and Discord settings saved in Mongo
Quote a keyword that has spaces, like "data analyst"

Environment (all required):
  SCRAPER_UI_URL     scraper-ui address, like http://127.0.0.1:8090
  AUTH_TOKEN         token the scraper-ui accepts as a Bearer token, same as its AUTH_TOKEN
USAGE
}

exit_with_usage() {
    print_usage >&2
    exit 1
}

exit_with_error() {
    echo "ERROR: $*" >&2
    exit 1
}

validate_requirements() {
    command -v curl >/dev/null 2>&1 || exit_with_error "curl is not installed"
    command -v jq >/dev/null 2>&1 || exit_with_error "jq is not installed"
    [[ -n "$UI_URL" ]] || exit_with_error "No scraper-ui address, set SCRAPER_UI_URL"
    [[ -n "$BEARER_TOKEN" ]] || exit_with_error "No auth token, set AUTH_TOKEN"
}

start_scrape() {
    local keyword="$1"
    local scrape_body
    scrape_body="$(build_scrape_body "$keyword")" || return 1

    local scrape_summary
    scrape_summary="$(call_ui_api POST /api/scrapes "$scrape_body")" || return 1
    jq --raw-output '.id' <<<"$scrape_summary"
}

wait_for_discord_send() {
    local scrape_id="$1"
    local deadline=$(( SECONDS + SCRAPE_TIMEOUT_SECONDS ))
    local discord_start_deadline=0
    local failed_poll_count=0
    local last_progress=""

    while (( SECONDS < deadline )); do
        local scrape_report scrape_status discord_status
        if ! scrape_report="$(read_scrape_report "$scrape_id")"; then
            failed_poll_count=$(( failed_poll_count + 1 ))
            (( failed_poll_count < MAX_FAILED_POLLS )) \
                || exit_with_error "Reading scrape $scrape_id failed $MAX_FAILED_POLLS times in a row"
            sleep "$POLL_SECONDS"
            continue
        fi
        failed_poll_count=0
        scrape_status="$(read_summary_field "$scrape_report" status)"
        discord_status="$(read_summary_field "$scrape_report" discord_status)"

        local progress="scrape $scrape_status, discord ${discord_status:-waiting}"
        if [[ "$progress" != "$last_progress" ]]; then
            echo "[${SECONDS}s] $progress"
            last_progress="$progress"
        fi

        if is_discord_send_finished "$discord_status"; then
            return
        fi

        if [[ "$scrape_status" != "$SCRAPE_STATUS_IN_PROGRESS" && -z "$discord_status" ]]; then
            if (( discord_start_deadline == 0 )); then
                discord_start_deadline=$(( SECONDS + DISCORD_START_GRACE_SECONDS ))
            fi
            (( SECONDS < discord_start_deadline )) \
                || exit_with_error "Scrape ended as $scrape_status and the Discord send never started"
        fi

        sleep "$POLL_SECONDS"
    done

    exit_with_error "Timed out after ${SCRAPE_TIMEOUT_SECONDS}s waiting for scrape $scrape_id"
}

read_scrape_report() {
    local scrape_id="$1"
    call_ui_api GET "/api/scrapes/$scrape_id"
}

print_scrape_outcome() {
    local scrape_report="$1"
    local scrape_status job_count error_count scrape_error
    scrape_status="$(read_summary_field "$scrape_report" status)"
    job_count="$(read_summary_field "$scrape_report" job_count)"
    error_count="$(read_summary_field "$scrape_report" error_count)"
    scrape_error="$(read_summary_field "$scrape_report" error)"

    local discord_status discord_sent discord_failed discord_error
    discord_status="$(read_summary_field "$scrape_report" discord_status)"
    discord_sent="$(read_summary_field "$scrape_report" discord_sent)"
    discord_failed="$(read_summary_field "$scrape_report" discord_failed)"
    discord_error="$(read_summary_field "$scrape_report" discord_error)"

    echo "Scrape: $scrape_status, $job_count jobs, $error_count errors"
    if [[ -n "$scrape_error" ]]; then
        echo "Scrape error: $scrape_error"
    fi
    echo "Discord: $discord_status, $discord_sent jobs sent, $discord_failed failed"
    if [[ -n "$discord_error" ]]; then
        echo "Discord error: $discord_error"
    fi
}

exit_unless_scraped_and_sent() {
    local scrape_report="$1"
    local scrape_status discord_status
    scrape_status="$(read_summary_field "$scrape_report" status)"
    discord_status="$(read_summary_field "$scrape_report" discord_status)"
    [[ "$scrape_status" != "$SCRAPE_STATUS_FAILED" ]] || exit 1
    [[ "$discord_status" == "$DISCORD_STATUS_SENT" ]] || exit 1
}

build_scrape_body() {
    local keyword="$1"
    jq --null-input \
        --arg keyword "$keyword" \
        '{keywords: [$keyword], sites: $ARGS.positional, notify_discord: true}' \
        --args "${SITES[@]}"
}

read_summary_field() {
    local scrape_report="$1"
    local field_name="$2"
    jq --raw-output --arg field_name "$field_name" '.record[$field_name] // ""' <<<"$scrape_report"
}

is_discord_send_finished() {
    local discord_status="$1"
    [[ -n "$discord_status" && "$discord_status" != "$DISCORD_STATUS_SENDING" ]]
}

call_ui_api() {
    local method="$1"
    local api_path="$2"
    local request_body="${3:-}"

    local curl_args=(
        --silent --show-error
        --max-time "$REQUEST_TIMEOUT_SECONDS"
        --request "$method"
        --header @-
    )
    if [[ -n "$request_body" ]]; then
        curl_args+=(--header "Content-Type: application/json" --data-binary "$request_body")
    fi

    local response_body
    response_body="$(curl "${curl_args[@]}" "$UI_URL$api_path" <<<"Authorization: Bearer $BEARER_TOKEN")" \
        || exit_with_error "curl exit $? on $method $UI_URL$api_path, is scraper-ui up at SCRAPER_UI_URL?"

    local is_success
    is_success="$(jq --raw-output '.success' <<<"$response_body" 2>/dev/null || true)"
    [[ "$is_success" == "true" ]] \
        || exit_with_error "$method $api_path failed: $(read_api_error "$response_body")"

    jq --compact-output '.data' <<<"$response_body"
}

read_api_error() {
    local response_body="$1"
    jq --raw-output '.error | if type == "string" then . else tojson end' <<<"$response_body" 2>/dev/null \
        || echo "$response_body"
}

main "$@"
