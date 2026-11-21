#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly NETWORK_NAME="job-net"
readonly MONGO_VOLUME_NAME="job-scrapper_mongo-data"
readonly COMPOSE_FILES=(
    infra/compose/docker-compose.yml
    infra/compose/docker-compose.dev.yml
)
readonly ENV_FILE=".env"
readonly FRONTEND_DIR="frontend"
readonly VITE_URL="http://localhost:5174"

main() {
    (( $# <= 1 )) || exit_with_usage

    local action="${1:-}"
    case "$action" in
        -h | --help)
            print_usage
            return
            ;;
        "" | start | stop | restart) ;;
        *) exit_with_usage ;;
    esac

    validate_requirements

    if [[ -z "$action" ]]; then
        action="$(choose_action)"
    fi

    "$action"
}

start() {
    ensure_network
    ensure_mongo_volume
    run_compose up -d --build
    start_vite
}

stop() {
    run_compose down
}

restart() {
    stop
    start
}

print_usage() {
    cat <<USAGE
Usage: $(basename "$0") [start|stop|restart|--help]

Run with no argument to choose a command from a menu
The dev stack is mongo, scraper-mcp (:8080), scraper-ui (:8090) and Vite ($VITE_URL)

Commands:
  start    Build and start the containers, then run Vite in the foreground
  stop     Stop and remove the containers, data volumes are kept
  restart  Stop, then start
  --help   Show this help
USAGE
}

exit_with_usage() {
    print_usage >&2
    exit 1
}

choose_action() {
    [[ -t 0 ]] || exit_with_usage

    local choice
    PS3="Choose a command: "
    select choice in start restart stop; do
        if [[ -n "$choice" ]]; then
            echo "$choice"
            return
        fi
        echo "Invalid choice" >&2
    done
    exit 1
}

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

validate_requirements() {
    command -v docker >/dev/null 2>&1 || fail "docker is not installed"
    docker info >/dev/null 2>&1 || fail "Docker daemon is not running"
    docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is missing (docker compose)"
    command -v bun >/dev/null 2>&1 || fail "bun is not installed, Vite needs it"

    [[ -f "$PROJECT_ROOT/$ENV_FILE" ]] \
        || fail "$ENV_FILE not found, create it with: cp .env.example .env"

    local compose_file
    for compose_file in "${COMPOSE_FILES[@]}"; do
        [[ -f "$PROJECT_ROOT/$compose_file" ]] || fail "$compose_file not found"
    done
}

run_compose() {
    local compose_args=() compose_file
    for compose_file in "${COMPOSE_FILES[@]}"; do
        compose_args+=(-f "$PROJECT_ROOT/$compose_file")
    done
    docker compose "${compose_args[@]}" \
        --project-directory "$PROJECT_ROOT" \
        --env-file "$PROJECT_ROOT/$ENV_FILE" \
        "$@"
}

ensure_network() {
    docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 && return
    docker network create "$NETWORK_NAME" >/dev/null
    echo "Created Docker network $NETWORK_NAME"
}

ensure_mongo_volume() {
    docker volume inspect "$MONGO_VOLUME_NAME" >/dev/null 2>&1 && return
    docker volume create "$MONGO_VOLUME_NAME" >/dev/null
    echo "Created Docker volume $MONGO_VOLUME_NAME"
}

start_vite() {
    cd "$PROJECT_ROOT/$FRONTEND_DIR"
    [[ -d node_modules ]] || bun install --frozen-lockfile
    echo "Starting Vite at $VITE_URL, Ctrl+C stops Vite only, containers keep running"
    exec bun run dev
}

main "$@"
