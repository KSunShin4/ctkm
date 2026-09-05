#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# start.sh — Khởi động CTKM Pipeline (Backend + Frontend)
# Chạy lần đầu: bash start.sh --setup
# Chạy bình thường: bash start.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"
info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ── Kiểm tra .env ─────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  warn ".env chưa tồn tại — đã tạo từ .env.example"
  warn "Hãy đổi ADMIN_PASSWORD và ADMIN_SESSION_SECRET trước khi dùng công cụ quản trị."
  warn "GEMINI_API_KEY chỉ cần khi file không nhận diện được bằng mapping chuẩn/đã lưu."
fi

# ── Setup (chạy lần đầu) ──────────────────────────────────────────────────────
if [ "$1" = "--setup" ]; then
  echo ""
  echo "=== Cài đặt CTKM Pipeline ==="
  echo ""

  # Python deps
  info "Cài Python dependencies…"
  pip install -r "$ROOT/backend/requirements_backend.txt" --break-system-packages -q \
    || pip install -r "$ROOT/backend/requirements_backend.txt" -q \
    || error "Không cài được Python deps. Hãy thử: pip install -r backend/requirements_backend.txt"

  # Node deps
  if ! command -v node &>/dev/null; then
    error "Node.js chưa được cài. Tải tại https://nodejs.org"
  fi
  info "Cài Node dependencies (React + Vite)…"
  cd "$ROOT/frontend" && npm install --silent
  cd "$ROOT"

  info "Setup hoàn tất! Chạy: bash start.sh"
  exit 0
fi

# ── Kiểm tra deps đã cài chưa ─────────────────────────────────────────────────
PYTHON=""
if command -v python3 &>/dev/null; then PYTHON="python3"
elif command -v python  &>/dev/null; then PYTHON="python"
else error "Python chưa được cài."
fi

if ! $PYTHON -c "import fastapi" 2>/dev/null; then
  error "fastapi chưa được cài. Chạy: bash start.sh --setup"
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  error "node_modules chưa tồn tại. Chạy: bash start.sh --setup"
fi

# ── Khởi động ─────────────────────────────────────────────────────────────────
echo ""
echo "=== Khởi động CTKM Pipeline ==="
info "Backend  → http://localhost:8000"
info "Frontend → http://localhost:5173"
info "API docs → http://localhost:8000/docs"
echo ""

# Chạy backend (background)
cd "$ROOT"
$PYTHON -m uvicorn backend.main_api:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Chờ backend ready
sleep 2

# Chạy frontend
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

# Trap Ctrl+C để dừng cả 2
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
