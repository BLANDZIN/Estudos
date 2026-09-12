"""
Backend mínimo da Agnes.

Não guarda segredos no código, e nunca deixa a LLM executar nada
diretamente — ela só pode "pedir" uma ferramenta da allowlist (tools.py),
que o FRONTEND é quem de fato executa depois de receber a resposta validada.

O servidor de modelo (Ollama, llama.cpp server, etc.) pode estar no mesmo
dispositivo (AGNES_PROVIDER=local) ou em outro na rede (AGNES_PROVIDER=remote)
— ver ai_provider.py e .env.example. Este arquivo (main.py) não muda
dependendo de qual provedor está ativo.

Rodar (só nesta máquina, padrão mais seguro):
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8787

Rodar aceitando conexões de outros dispositivos da rede — leia a seção
"Segurança de rede" no README.md ANTES de usar --host 0.0.0.0:
    uvicorn main:app --host 0.0.0.0 --port 8787
"""

import os
import re
import json

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import memory
import tools
from agnes_persona import build_system_prompt
from ai_provider import get_provider

app = FastAPI(title="Agnes backend", version="0.1.0")

_default_origins = "http://localhost:5500,http://127.0.0.1:5500,http://localhost:8080,http://127.0.0.1:8080"
allowed_origins = os.getenv("AGNES_ALLOWED_ORIGINS", _default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _print_startup_hint():
    provider_kind = os.getenv("AGNES_PROVIDER", "local")
    print(f"\n[Agnes] Backend no ar. Provedor de IA configurado: {provider_kind}.")
    print("[Agnes] Rodando neste dispositivo? Configure a Agnes (⚙ no app) com http://127.0.0.1:<porta>.")
    print("[Agnes] Acessando de outro aparelho da rede? Veja a seção 'Segurança de rede' e 'Usando de outro")
    print("[Agnes] dispositivo' no README.md antes de expor esta porta — 0.0.0.0 NÃO é garantia de segurança.\n")

provider = get_provider()

TOOL_JSON_RE = re.compile(r"\{[^{}]*\"tool\"\s*:\s*\"[a-z_]+\"[^{}]*\}", re.DOTALL)


class ChatRequest(BaseModel):
    message: str
    app_context: dict | None = None


class ChatResponse(BaseModel):
    reply: str
    action: dict | None = None
    action_error: str | None = None


class RememberRequest(BaseModel):
    category: str
    value: str
    key: str | None = None


def _extract_tool_call(raw_text: str):
    """Procura um bloco {"tool": "...", "args": {...}} na resposta da LLM.
    Devolve (texto_limpo, tool_dict_ou_None)."""
    match = TOOL_JSON_RE.search(raw_text)
    if not match:
        return raw_text.strip(), None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return raw_text.strip(), None
    cleaned = (raw_text[: match.start()] + raw_text[match.end() :]).strip()
    return cleaned, parsed


def _app_context_note(app_context: dict | None) -> str | None:
    if not app_context:
        return None
    parts = []
    if app_context.get("current_subject"):
        parts.append(f"Matéria selecionada agora: {app_context['current_subject']}")
    if app_context.get("timer_running") is not None:
        parts.append("Cronômetro rodando agora." if app_context["timer_running"] else "Cronômetro parado agora.")
    if app_context.get("today_label"):
        parts.append(f"Hoje é {app_context['today_label']}.")
    if not parts:
        return None
    return "Contexto atual do app (só pra você usar se for relevante, não precisa comentar):\n" + "\n".join(parts)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message or not req.message.strip():
        raise HTTPException(400, "message vazia")

    memory.log_turn("user", req.message)

    system_prompt = build_system_prompt(memory.get_context_snippet())
    system_prompt += "\n\n" + tools.tool_descriptions_for_prompt()

    messages = [{"role": "system", "content": system_prompt}]

    context_note = _app_context_note(req.app_context)
    if context_note:
        messages.append({"role": "system", "content": context_note})

    messages.extend({"role": t["role"], "content": t["content"]} for t in memory.recent_turns(limit=8))
    messages.append({"role": "user", "content": req.message})

    try:
        raw_reply = await provider.chat(messages)
    except RuntimeError as e:
        # servidor local fora do ar — devolve mensagem amigável em vez de 500 genérico
        raise HTTPException(503, str(e))

    cleaned_reply, tool_json = _extract_tool_call(raw_reply)

    action = None
    action_error = None
    if tool_json:
        try:
            call = tools.validate_tool_call(tool_json.get("tool"), tool_json.get("args"))
            action = {"name": call.name, "args": call.args}
        except tools.ToolValidationError as e:
            action_error = str(e)

    memory.log_turn("agnes", cleaned_reply or raw_reply)

    return ChatResponse(reply=cleaned_reply or raw_reply, action=action, action_error=action_error)


@app.get("/memory")
def get_memory(category: str | None = None):
    return memory.list_facts(category)


@app.post("/memory")
def add_memory(req: RememberRequest):
    memory.remember(req.category, req.value, req.key)
    return {"ok": True}


@app.delete("/memory/{fact_id}")
def delete_memory(fact_id: int):
    memory.forget(fact_id)
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True, "provider": type(provider).__name__}
