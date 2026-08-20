# -*- coding: utf-8 -*-
"""
watchdog.py — 前后端服务守护进程（解决 DSH 环境后台任务偶发回收导致服务掉线）
=================================================================================
作用:
    每 10 秒检查一次 8000(后端) / 5500(前端) 端口，发现服务挂掉立即自动拉起，
    并把服务进程尽量脱离当前作业会话（DETACHED + BREAKAWAY），降低被环境回收的概率。

用法:
    python scripts/watchdog.py            # 前台运行（或交给 start-services.ps1 托管）

日志:
    scripts/services.log                  # 守护自身与服务启停记录
    scripts/backend.log / frontend.log    # 服务 stdout/stderr
PID 文件:
    scripts/backend.pid / frontend.pid    # 记录服务进程号，避免重复拉起
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
LOG_FILE = os.path.join(SCRIPTS_DIR, "services.log")

VENV_PY = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
if not os.path.exists(VENV_PY):
    VENV_PY = sys.executable

BACKEND_CMD = [VENV_PY, "main.py", "--api", "--port", "8000", "--no-reload"]
FRONTEND_CMD = [VENV_PY, "frontend/server.py", "--port", "5500"]

CHECK_INTERVAL = 10          # 健康检查间隔（秒）
STARTUP_GRACE = 90           # 服务启动宽限期（秒）：宽限期内端口未开不重复拉起
BACKEND_STARTUP = 30         # 后端冷启动（加载嵌入模型）额外等待（秒）


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("watchdog")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid(name: str) -> int:
    try:
        with open(os.path.join(SCRIPTS_DIR, f"{name}.pid"), "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return -1


def write_pid(name: str, pid: int) -> None:
    with open(os.path.join(SCRIPTS_DIR, f"{name}.pid"), "w", encoding="utf-8") as f:
        f.write(str(pid))


def clear_pid(name: str) -> None:
    try:
        os.remove(os.path.join(SCRIPTS_DIR, f"{name}.pid"))
    except OSError:
        pass


def start_service(logger: logging.Logger, name: str, cmd: list, port: int) -> None:
    """启动服务；尽量脱离当前作业会话，返回进程对象。"""
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    try:
        if hasattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB"):
            flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
    except AttributeError:
        pass

    log_path = os.path.join(SCRIPTS_DIR, f"{name}.log")
    with open(log_path, "ab") as out:
        proc = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=out,
            creationflags=flags,
        )
    write_pid(name, proc.pid)
    logger.info("已拉起 %s (pid=%d, port=%d)", name, proc.pid, port)


def ensure_service(logger: logging.Logger, name: str, cmd: list, port: int,
                   start_time: float, last_start: float) -> float:
    """确保服务在线。返回本服务的 last_start 时间戳。"""
    pid = read_pid(name)
    if pid_alive(pid):
        return last_start  # 进程活着（可能还在启动中），不干预

    if port_open(port):
        clear_pid(name)
        return last_start  # 端口已通但 pid 文件失效，仅清理

    # 进程不在、端口不通 → 需要拉起；宽限期内不重复拉起
    if last_start and time.time() - last_start < STARTUP_GRACE:
        return last_start

    logger.warning("%s 掉线（pid=%s, port=%d 不通），自动重启", name, pid, port)
    start_service(logger, name, cmd, port)
    return time.time()


def main() -> None:
    logger = setup_logger()
    logger.info("watchdog 启动: 监控 8000(后端)/5500(前端)，每 %ds 检查一次", CHECK_INTERVAL)
    start_time = time.time()
    backend_last_start = 0.0
    frontend_last_start = 0.0
    # 首次启动直接拉起两个服务
    if not port_open(8000) and not pid_alive(read_pid("backend")):
        start_service(logger, "backend", BACKEND_CMD, 8000)
        backend_last_start = time.time()
        logger.info("后端冷启动，等待 %ds 加载模型...", BACKEND_STARTUP)
        time.sleep(BACKEND_STARTUP)
    if not port_open(5500) and not pid_alive(read_pid("frontend")):
        start_service(logger, "frontend", FRONTEND_CMD, 5500)
        frontend_last_start = time.time()

    while True:
        backend_last_start = ensure_service(
            logger, "backend", BACKEND_CMD, 8000, start_time, backend_last_start
        )
        frontend_last_start = ensure_service(
            logger, "frontend", FRONTEND_CMD, 5500, start_time, frontend_last_start
        )
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
