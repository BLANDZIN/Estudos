"""
Camada de memória da Agnes — separada da LLM.

Guarda só o que é útil pra personalização: preferências, forma de tratamento
escolhida pelo usuário, matérias/objetivos mencionados, e coisas que o
usuário pediu explicitamente pra lembrar. NÃO guarda o histórico bruto da
conversa inteira, e a LLM nunca recebe o banco inteiro — só um resumo curto
relevante pro turno atual (ver `get_context_snippet`).

Armazenamento: SQLite local (arquivo `agnes_memory.db`), nunca commitado
(está no .gitignore).
"""

import sqlite3
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "agnes_memory.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,     -- 'preferencia' | 'tratamento' | 'estudo' | 'pedido_explicito'
            key TEXT,
            value TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,   -- 'user' | 'agnes'
            content TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    return conn


def remember(category: str, value: str, key: Optional[str] = None) -> None:
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO memory_facts (category, key, value, created_at) VALUES (?, ?, ?, ?)",
            (category, key, value, time.time()),
        )
    conn.close()


def forget(fact_id: int) -> None:
    conn = _connect()
    with conn:
        conn.execute("DELETE FROM memory_facts WHERE id = ?", (fact_id,))
    conn.close()


def list_facts(category: Optional[str] = None) -> list[dict]:
    conn = _connect()
    if category:
        rows = conn.execute(
            "SELECT id, category, key, value FROM memory_facts WHERE category = ? ORDER BY id DESC",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, category, key, value FROM memory_facts ORDER BY id DESC"
        ).fetchall()
    conn.close()
    return [{"id": r[0], "category": r[1], "key": r[2], "value": r[3]} for r in rows]


def log_turn(role: str, content: str) -> None:
    conn = _connect()
    with conn:
        conn.execute(
            "INSERT INTO conversation_log (role, content, created_at) VALUES (?, ?, ?)",
            (role, content[:2000], time.time()),
        )
    conn.close()


def recent_turns(limit: int = 8) -> list[dict]:
    """Últimas mensagens — usado como contexto curto de conversa (não a memória
    de longo prazo), pra Agnes lembrar do que vocês falaram há 2 minutos."""
    conn = _connect()
    rows = conn.execute(
        "SELECT role, content FROM conversation_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def get_context_snippet(max_facts: int = 12) -> str:
    """Monta um resumo curto pra injetar no prompt — NUNCA o banco inteiro.
    Prioriza forma de tratamento e preferências, que mudam pouco e importam
    sempre; o resto entra até o limite."""
    facts = list_facts()
    if not facts:
        return ""
    facts.sort(key=lambda f: 0 if f["category"] == "tratamento" else 1)
    facts = facts[:max_facts]
    lines = [f"- ({f['category']}) {f['value']}" for f in facts]
    return "O que você já sabe sobre este usuário (use com naturalidade, não recite a lista):\n" + "\n".join(lines)
