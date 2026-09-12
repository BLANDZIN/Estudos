"""
Camada de ferramentas da Agnes.

Regra de ouro: este arquivo NUNCA executa nada no app. Ele só descreve quais
ações existem, valida os parâmetros que a LLM pediu, e devolve uma ação
estruturada e segura. Quem executa de verdade é o frontend (React), que já
tem as funções certas (start_timer -> liga o cronômetro existente, etc.).

Isso é proposital: a LLM nunca tem acesso direto a banco de dados, sistema
de arquivos ou código arbitrário — só pode "pedir" uma dessas ações abaixo,
com parâmetros no formato certo.
"""

from dataclasses import dataclass
from typing import Any, Optional


class ToolValidationError(Exception):
    pass


@dataclass
class ToolCall:
    name: str
    args: dict


# ---------------------------------------------------------------------------
# Allowlist de ferramentas. Cada entrada define os parâmetros aceitos e uma
# função de validação simples. Se a ferramenta não estiver aqui, é rejeitada.
# ---------------------------------------------------------------------------

def _validate_start_timer(args: dict) -> dict:
    duration = args.get("duration_minutes")
    if duration is not None:
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            raise ToolValidationError("duration_minutes precisa ser um número")
        if not (1 <= duration <= 240):
            raise ToolValidationError("duration_minutes precisa estar entre 1 e 240")
    mode = args.get("mode", "pomodoro")
    if mode not in ("pomodoro", "livre", "regressiva"):
        raise ToolValidationError("mode inválido")
    subject_name = args.get("subject_name")
    return {"mode": mode, "duration_minutes": duration, "subject_name": subject_name}


def _validate_pause_timer(args: dict) -> dict:
    return {}


def _validate_stop_timer(args: dict) -> dict:
    return {}


def _validate_select_subject(args: dict) -> dict:
    subject_name = args.get("subject_name")
    if not subject_name or not isinstance(subject_name, str):
        raise ToolValidationError("subject_name é obrigatório")
    return {"subject_name": subject_name.strip()[:60]}


def _validate_open_screen(args: dict) -> dict:
    screen = args.get("screen")
    allowed = {"painel", "materias", "guia", "calendario", "cronometro", "sessoes", "questoes", "importar"}
    if screen not in allowed:
        raise ToolValidationError(f"screen precisa ser um de: {sorted(allowed)}")
    return {"screen": screen}


def _validate_get_today_schedule(args: dict) -> dict:
    return {}


def _validate_get_study_progress(args: dict) -> dict:
    subject_name = args.get("subject_name")
    return {"subject_name": subject_name.strip()[:60] if subject_name else None}


def _validate_record_study_progress(args: dict) -> dict:
    subject_name = args.get("subject_name")
    topic_name = args.get("topic_name")
    status = args.get("status")
    allowed_status = {"nao_estudado", "estudando", "revisando", "duvida", "dominado"}
    if not subject_name or not topic_name:
        raise ToolValidationError("subject_name e topic_name são obrigatórios")
    if status not in allowed_status:
        raise ToolValidationError(f"status precisa ser um de: {sorted(allowed_status)}")
    return {
        "subject_name": subject_name.strip()[:60],
        "topic_name": topic_name.strip()[:120],
        "status": status,
    }


def _validate_create_study_session(args: dict) -> dict:
    subject_name = args.get("subject_name")
    if not subject_name:
        raise ToolValidationError("subject_name é obrigatório")
    return {"subject_name": subject_name.strip()[:60]}


def _validate_finish_study_session(args: dict) -> dict:
    note = args.get("note")
    return {"note": (note or "").strip()[:200]}


def _validate_create_reminder(args: dict) -> dict:
    title = args.get("title")
    target_date = args.get("target_date")  # YYYY-MM-DD
    if not title or not target_date:
        raise ToolValidationError("title e target_date são obrigatórios")
    return {"title": str(title).strip()[:60], "target_date": str(target_date)[:10]}


TOOL_REGISTRY = {
    "start_timer": _validate_start_timer,
    "pause_timer": _validate_pause_timer,
    "stop_timer": _validate_stop_timer,
    "select_subject": _validate_select_subject,
    "open_screen": _validate_open_screen,
    "get_today_schedule": _validate_get_today_schedule,
    "get_study_progress": _validate_get_study_progress,
    "record_study_progress": _validate_record_study_progress,
    "create_study_session": _validate_create_study_session,
    "finish_study_session": _validate_finish_study_session,
    "create_reminder": _validate_create_reminder,
}


def validate_tool_call(name: str, args: Optional[dict]) -> ToolCall:
    """Valida uma chamada de ferramenta pedida pela LLM. Lança ToolValidationError
    se a ferramenta não existir na allowlist ou os parâmetros forem inválidos."""
    args = args or {}
    if name not in TOOL_REGISTRY:
        raise ToolValidationError(f"Ferramenta '{name}' não é permitida.")
    validated_args = TOOL_REGISTRY[name](args)
    return ToolCall(name=name, args=validated_args)


def tool_descriptions_for_prompt() -> str:
    """Descrição curta das ferramentas, para incluir no prompt da LLM."""
    return (
        "Ferramentas disponíveis (use SOMENTE se o usuário pedir uma ação real; "
        "para só conversar, não use nenhuma):\n"
        "- start_timer(mode, duration_minutes, subject_name)\n"
        "- pause_timer()\n"
        "- stop_timer()\n"
        "- select_subject(subject_name)\n"
        "- open_screen(screen)  # painel|materias|guia|calendario|cronometro|sessoes|questoes|importar\n"
        "- get_today_schedule()\n"
        "- get_study_progress(subject_name?)\n"
        "- record_study_progress(subject_name, topic_name, status)  # nao_estudado|estudando|revisando|duvida|dominado\n"
        "- create_study_session(subject_name)\n"
        "- finish_study_session(note?)\n"
        "- create_reminder(title, target_date)  # YYYY-MM-DD\n"
    )
