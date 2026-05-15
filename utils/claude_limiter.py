import os
import time
import json
import logging
import tempfile
from pathlib import Path


PASTA_LOCKS = Path(tempfile.gettempdir()) / "sistema_triagem_locks"
PASTA_LOCKS.mkdir(exist_ok=True)

ARQUIVO_LOCK = PASTA_LOCKS / "claude_api.lock"
ARQUIVO_ESTADO = PASTA_LOCKS / "claude_api_state.json"

CLAUDE_INTERVALO_MINIMO = float(os.getenv("CLAUDE_INTERVALO_MINIMO", "5"))


def _bloquear_arquivo(file_handle):
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)


def _desbloquear_arquivo(file_handle):
    if os.name == "nt":
        import msvcrt
        file_handle.seek(0)
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


def aguardar_janela_claude():
    """
    Garante que todos os processos do sistema respeitem uma fila única
    antes de chamar a API da Anthropic.
    """
    with open(ARQUIVO_LOCK, "a+b") as lock_file:
        _bloquear_arquivo(lock_file)

        try:
            agora = time.time()

            if ARQUIVO_ESTADO.exists():
                try:
                    estado = json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
                except Exception:
                    estado = {}
            else:
                estado = {}

            ultima_chamada = float(estado.get("ultima_chamada", 0))
            decorrido = agora - ultima_chamada

            if decorrido < CLAUDE_INTERVALO_MINIMO:
                espera = CLAUDE_INTERVALO_MINIMO - decorrido
                logging.info(f"[CLAUDE] Aguardando {espera:.1f}s para respeitar limite global...")
                time.sleep(espera)

            ARQUIVO_ESTADO.write_text(
                json.dumps({"ultima_chamada": time.time()}),
                encoding="utf-8"
            )

        finally:
            _desbloquear_arquivo(lock_file)


def erro_rate_limit(e: Exception) -> bool:
    texto = str(e).lower()

    return (
        "429" in texto
        or "529" in texto
        or "too many requests" in texto
        or "rate limit" in texto
        or "overloaded" in texto
    )

