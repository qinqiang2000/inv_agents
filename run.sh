#!/bin/bash

# Invoice Field Recommender Agent - Process Management Script
# Usage: ./run.sh [start|stop|restart]
# Default: restart

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
LOG_DIR="$SCRIPT_DIR/log"
PID_FILE="$LOG_DIR/app.pid"
APP_MODULE="app:app"

# Load environment variables from .env.prod if it exists
if [ -f "$SCRIPT_DIR/.env.prod" ]; then
    set -a  # Automatically export all variables
    source "$SCRIPT_DIR/.env.prod"
    set +a
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored message
print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if process is running
is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

# Stop the service
stop_service() {
    print_info "Stopping Invoice Field Recommender Agent..."

    if [ ! -f "$PID_FILE" ]; then
        print_warning "PID file not found. Service may not be running."
        return 0
    fi

    local pid=$(cat "$PID_FILE")

    if ! ps -p "$pid" > /dev/null 2>&1; then
        print_warning "Process $pid is not running. Cleaning up PID file."
        rm -f "$PID_FILE"
        return 0
    fi

    print_info "Sending SIGTERM to process $pid..."
    kill -TERM "$pid" 2>/dev/null || true

    # Wait for graceful shutdown (max 10 seconds)
    local wait_time=0
    while ps -p "$pid" > /dev/null 2>&1 && [ $wait_time -lt 10 ]; do
        sleep 1
        wait_time=$((wait_time + 1))
        echo -n "."
    done
    echo ""

    # Force kill if still running
    if ps -p "$pid" > /dev/null 2>&1; then
        print_warning "Process did not stop gracefully. Sending SIGKILL..."
        kill -KILL "$pid" 2>/dev/null || true
        sleep 1
    fi

    # Clean up PID file
    rm -f "$PID_FILE"
    print_success "Service stopped successfully"
}

# Start the service
start_service() {
    print_info "Starting Invoice Field Recommender Agent..."

    # Check if already running
    if is_running; then
        local pid=$(cat "$PID_FILE")
        print_error "Service is already running (PID: $pid)"
        print_info "Use './run.sh restart' to restart the service"
        exit 1
    fi

    # Change to script directory
    cd "$SCRIPT_DIR"

    # Check virtual environment
    if [ ! -f "$VENV_DIR/bin/activate" ]; then
        print_error "Virtual environment not found at $VENV_DIR"
        print_info "Please create a virtual environment first:"
        print_info "  python3 -m venv .venv"
        print_info "  source .venv/bin/activate"
        print_info "  pip install -r requirements.txt"
        exit 1
    fi

    # Activate virtual environment
    source "$VENV_DIR/bin/activate"

    # Check if dependencies are installed
    if ! python -c "import fastapi" 2>/dev/null; then
        print_warning "Dependencies not installed. Installing now..."
        pip install -r requirements.txt
    fi

    # Create log directory
    mkdir -p "$LOG_DIR"

    # Rotate old log file if exists
    if [ -f "$LOG_DIR/app.log" ]; then
        OLD_TIMESTAMP=$(date -r "$LOG_DIR/app.log" +%Y%m%d-%H%M%S)
        mv "$LOG_DIR/app.log" "$LOG_DIR/app-$OLD_TIMESTAMP.log"
        print_info "Rotated old log to: app-$OLD_TIMESTAMP.log"
    fi

    # Use fixed log file name
    LOG_FILE="$LOG_DIR/app.log"

    # Start the service in background
    print_info "Starting uvicorn server..."
    nohup uvicorn "$APP_MODULE" \
        --host "$HOST" \
        --port "$PORT" \
        --reload \
        > "$LOG_FILE" 2>&1 &

    local pid=$!
    echo "$pid" > "$PID_FILE"

    # Wait a moment and check if process started successfully
    sleep 2
    if ps -p "$pid" > /dev/null 2>&1; then
        print_success "Service started successfully (PID: $pid)"
        echo ""
        echo "=========================================="
        echo "Invoice Field Recommender Agent"
        echo "=========================================="
        echo "PID: $pid"
        echo "Log file: $LOG_FILE"
        echo "API: http://localhost:$PORT"
        echo "Chat UI: http://localhost:$PORT"
        echo "API Docs: http://localhost:$PORT/docs"
        echo "=========================================="
        echo ""
        print_info "Viewing logs (Press Ctrl+C to stop, service will continue running)..."
        echo ""

        # Automatically tail the log file
        tail -f "$LOG_FILE"
    else
        print_error "Failed to start service"
        rm -f "$PID_FILE"
        print_info "Check log file: $LOG_FILE"
        exit 1
    fi
}

# Show usage
show_usage() {
    echo "Usage: $0 [start|stop|restart]"
    echo ""
    echo "Commands:"
    echo "  start    - Start the service (fails if already running)"
    echo "  stop     - Stop the service"
    echo "  restart  - Restart the service (default)"
    echo ""
    echo "Examples:"
    echo "  $0              # Restart (default)"
    echo "  $0 start        # Start if not running"
    echo "  $0 stop         # Stop the service"
    echo "  $0 restart      # Stop and start"
}

# Main script logic
main() {
    local command="${1:-restart}"

    case "$command" in
        start)
            start_service
            ;;
        stop)
            stop_service
            ;;
        restart)
            if is_running; then
                stop_service
                echo ""
            fi
            start_service
            ;;
        -h|--help|help)
            show_usage
            ;;
        *)
            print_error "Unknown command: $command"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
