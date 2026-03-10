import subprocess
import threading
import sys
import os
import time

def run_backend():
    print("🚀 Starting Backend (FastAPI)...")
    # backend 폴더로 이동하여 실행
    backend_dir = os.path.join(os.getcwd(), "backend")
    # venv 경로 설정 (Windows/Linux 대응)
    venv_python = os.path.join(backend_dir, ".venv", "bin", "python") if os.name != "nt" else os.path.join(backend_dir, ".venv", "Scripts", "python.exe")
    
    if not os.path.exists(venv_python):
        # 가상환경이 없을 경우 시스템 파이썬 사용
        venv_python = sys.executable

    subprocess.run([venv_python, "-m", "uvicorn", "main:app", "--reload", "--port", "8000"], cwd=backend_dir)

def run_frontend():
    print("🎨 Starting Frontend (Next.js)...")
    frontend_dir = os.path.join(os.getcwd(), "frontend")
    # npm은 시스템 경로에 있다고 가정 (shell=True 필요)
    if os.name == "nt": # Windows
        subprocess.run(["npm.cmd", "run", "dev"], cwd=frontend_dir, shell=True)
    else: # Linux/macOS
        subprocess.run(["npm", "run", "dev"], cwd=frontend_dir)

if __name__ == "__main__":
    try:
        # 1. 백엔드 스레드 시작
        backend_thread = threading.Thread(target=run_backend, daemon=True)
        backend_thread.start()

        # 백엔드가 포트를 점유할 시간을 잠시 줌
        time.sleep(2)

        # 2. 프론트엔드 스레드 시작
        frontend_thread = threading.Thread(target=run_frontend, daemon=True)
        frontend_thread.start()

        # 메인 스레드 유지
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Stopping all servers...")
        sys.exit(0)