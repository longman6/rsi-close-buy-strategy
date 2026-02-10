#!/bin/bash
################################################################################
# Trading Bot Launcher
#
# 자동 매매 봇 실행 및 관리 스크립트
# Usage: ./run.sh [start|stop|restart|status|logs]
################################################################################

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 설정
BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$BOT_DIR/.venv"
BOT_SCRIPT="$BOT_DIR/main.py"
LOG_FILE="$BOT_DIR/logs/bot.log"
PID_FILE="$BOT_DIR/logs/bot.pid"

# 로그 디렉토리 생성
mkdir -p "$BOT_DIR/logs"

################################################################################
# 함수 정의
################################################################################

print_header() {
    echo -e "${BLUE}"
    echo "================================================================================"
    echo "  KIS 자동 매매 봇 (Momentum + Vol-Targeting)"
    echo "================================================================================"
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

check_requirements() {
    # 가상환경 확인
    if [ ! -d "$VENV_PATH" ]; then
        print_error "가상환경이 없습니다. 먼저 가상환경을 생성하세요:"
        echo "  python3 -m venv .venv"
        echo "  source .venv/bin/activate"
        echo "  pip install -r requirements.txt"
        exit 1
    fi

    # .env 파일 확인
    if [ ! -f "$BOT_DIR/.env" ]; then
        print_error ".env 파일이 없습니다. .env.example을 복사하여 설정하세요:"
        echo "  cp .env.example .env"
        echo "  nano .env"
        exit 1
    fi

    # 설정 파일 확인
    if [ ! -f "$BOT_DIR/config.py" ]; then
        print_error "설정 파일(config.py)이 없습니다."
        exit 1
    fi

    print_success "모든 요구사항 확인 완료"
}

is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0
        else
            rm -f "$PID_FILE"
            return 1
        fi
    fi
    return 1
}

start_bot() {
    print_header

    echo "봇 시작 중..."

    # 요구사항 확인
    check_requirements

    # 이미 실행 중인지 확인
    if is_running; then
        print_warning "봇이 이미 실행 중입니다 (PID: $(cat $PID_FILE))"
        exit 1
    fi

    # 가상환경 활성화 및 봇 실행
    cd "$BOT_DIR"

    print_info "PYTHONPATH 설정 중..."
    export PYTHONPATH=$BOT_DIR

    print_info "봇 시작 중..."
    # 가상환경의 python을 직접 호출하여 실행
    nohup "$VENV_PATH/bin/python" "$BOT_SCRIPT" > "$LOG_FILE" 2>&1 &
    BOT_PID=$!

    # PID 저장
    echo "$BOT_PID" > "$PID_FILE"

    # 시작 확인
    sleep 3
    if is_running; then
        print_success "봇이 시작되었습니다 (PID: $BOT_PID)"
        echo ""
        print_info "로그 확인: tail -f $LOG_FILE"
        print_info "상태 확인: $0 status"
        print_info "중지: $0 stop"
        echo ""
        print_info "실시간 로그 출력 중... (Ctrl+C로 종료)"
        echo "----------------------------------------"
        tail -f "$LOG_FILE"
    else
        print_error "봇 시작에 실패했습니다"
        print_info "로그를 확인하세요: cat $LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop_bot() {
    print_header

    echo "봇 중지 중..."

    if ! is_running; then
        print_warning "실행 중인 봇이 없습니다"
        exit 1
    fi

    PID=$(cat "$PID_FILE")
    print_info "봇 프로세스 종료 중 (PID: $PID)..."

    # SIGTERM 시그널 전송 (graceful shutdown)
    kill "$PID" 2>/dev/null

    # 종료 대기 (최대 30초)
    for i in {1..30}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            print_success "봇이 정상적으로 종료되었습니다"
            rm -f "$PID_FILE"
            exit 0
        fi
        sleep 1
        echo -n "."
    done

    echo ""
    print_warning "봇이 응답하지 않습니다. 강제 종료합니다..."
    kill -9 "$PID" 2>/dev/null
    rm -f "$PID_FILE"
    print_success "봇이 강제 종료되었습니다"
}

restart_bot() {
    print_header
    echo "봇 재시작 중..."
    echo ""

    if is_running; then
        stop_bot
        echo ""
        sleep 2
    fi

    start_bot
}

show_status() {
    print_header

    echo "봇 상태 확인 중..."
    echo ""

    if is_running; then
        PID=$(cat "$PID_FILE")
        print_success "봇이 실행 중입니다"
        echo ""
        echo "  PID: $PID"
        echo "  실행 시간: $(ps -p $PID -o etime= | xargs)"
        echo "  메모리 사용: $(ps -p $PID -o rss= | awk '{printf "%.1f MB", $1/1024}')"
        echo "  CPU 사용: $(ps -p $PID -o %cpu= | xargs)%"
        echo ""

        # 최근 로그 출력
        if [ -f "$LOG_FILE" ]; then
            echo "최근 로그 (마지막 15줄):"
            echo "----------------------------------------"
            tail -15 "$LOG_FILE"
            echo "----------------------------------------"
        fi
    else
        print_warning "봇이 실행 중이 아닙니다"
    fi
}

show_logs() {
    print_header

    if [ ! -f "$LOG_FILE" ]; then
        print_error "로그 파일이 없습니다"
        exit 1
    fi

    if [ "$1" == "-f" ] || [ "$1" == "--follow" ]; then
        print_info "실시간 로그 (Ctrl+C로 종료)"
        echo ""
        tail -f "$LOG_FILE"
    else
        print_info "로그 출력 (마지막 50줄)"
        echo ""
        tail -50 "$LOG_FILE"
    fi
}

show_help() {
    print_header

    echo "사용법: $0 [명령어]"
    echo ""
    echo "명령어:"
    echo "  start       봇 시작"
    echo "  stop        봇 중지"
    echo "  restart     봇 재시작"
    echo "  status      봇 상태 확인"
    echo "  logs        로그 출력"
    echo "  logs -f     실시간 로그"
    echo "  help        도움말"
    echo ""
    echo "예제:"
    echo "  $0 start           # 봇 시작"
    echo "  $0 logs -f         # 실시간 로그 확인"
    echo ""
}

################################################################################
# 메인 실행
################################################################################

case "$1" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        restart_bot
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "$2"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "알 수 없는 명령어: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
