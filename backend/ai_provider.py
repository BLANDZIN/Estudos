"""
Abstração do provedor de IA. A ideia é que NADA no resto do backend (nem no
frontend) saiba os detalhes de qual modelo/servidor está sendo usado — só
conhece o contrato `AIProvider.chat(messages) -> str`.

Três formas de chegar até o modelo (`AGNES_PROVIDER` no `.env`), de propósito
desacopladas da lógica de conversa/memória/ferramentas — trocar de uma pra
outra é só configuração:

1. ONDE o servidor de inferência está (`Local` vs `Remote` vs `API`):
   - LocalLLMProvider: sempre fala com 127.0.0.1 (loopback) — o servidor de
     modelo roda no MESMO dispositivo que este backend. Cobre tanto "PC
     rodando Ollama" quanto "celular rodando llama.cpp via Termux, com este
     backend também rodando no celular". Como é loopback, nunca sai da
     máquina — não existe cenário de rede a considerar.
   - RemoteLLMProvider: fala com um host configurável (ex: o IP do PC na
     rede local), pra quando o backend/navegador estão num dispositivo e o
     modelo roda em outro (ex: celular usando o modelo maior do PC).
   - APIProvider: fala com um serviço de IA hospedado na nuvem (OpenAI,
     Anthropic, OpenRouter, Groq...), usando uma chave de API. A chave só
     existe no `.env` do backend — nunca chega no frontend nem no repositório.

2. QUE FORMATO de API o servidor de inferência fala (`flavor`):
   - "ollama"    → API nativa do Ollama (/api/chat)
   - "openai"    → API compatível com OpenAI (/v1/chat/completions) — é o
     que o servidor do llama.cpp (`llama-server`) expõe, junto com LM
     Studio, text-generation-webui (modo openai), OpenAI de verdade,
     OpenRouter, Groq, Together, etc.
   - "anthropic" → API nativa da Anthropic (/v1/messages) — só faz sentido
     com APIProvider.

Isso significa: llama.cpp local no celular = LocalLLMProvider(flavor="openai").
Ollama no PC acessado do celular = RemoteLLMProvider(flavor="ollama", host=...).
GPT/Claude/etc. na nuvem = APIProvider(flavor="openai" ou "anthropic", api_key=...).
Trocar de um pra outro é só configuração (.env) — nada no resto do backend
ou no frontend muda.
"""

import os
from abc import ABC, abstractmethod
from typing import Optional

import httpx


class AIProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict]) -> str:
        """Recebe uma lista de mensagens [{role, content}, ...] e devolve o
        texto de resposta do modelo (string única, sem streaming por ora)."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Funções de baixo nível — uma por formato de API. Não sabem nada sobre
# "local" ou "remoto", só recebem a base_url já pronta.
# ---------------------------------------------------------------------------

async def _ollama_chat(base_url: str, model: str, messages: list[dict], api_key: Optional[str] = None) -> str:
    # https://github.com/ollama/ollama/blob/main/docs/api.md#chat-request
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {"model": model, "messages": messages, "stream": False}
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "").strip()


async def _openai_compatible_chat(base_url: str, model: str, messages: list[dict], api_key: Optional[str] = None) -> str:
    # Formato usado por llama.cpp server, LM Studio, text-generation-webui (modo openai),
    # e também por serviços de API na nuvem: OpenAI, OpenRouter, Groq, Together, etc.
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    payload = {"model": model, "messages": messages}
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


async def _anthropic_chat(base_url: str, model: str, messages: list[dict], api_key: Optional[str] = None) -> str:
    # API nativa da Anthropic: system fica separado da lista de mensagens,
    # e a autenticação usa o header x-api-key (não Bearer).
    if not api_key:
        raise RuntimeError("Flavor 'anthropic' precisa de AGNES_API_KEY configurado.")
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    turns = [m for m in messages if m.get("role") in ("user", "assistant")]
    url = f"{base_url.rstrip('/')}/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 1024,
        "messages": turns,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        blocks = data.get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


_FLAVOR_HANDLERS = {
    "ollama": _ollama_chat,
    "openai": _openai_compatible_chat,
    "anthropic": _anthropic_chat,
}


def _resolve_flavor(flavor: str):
    handler = _FLAVOR_HANDLERS.get(flavor)
    if handler is None:
        raise ValueError(f"AGNES_LLM_FLAVOR inválido: '{flavor}'. Use 'ollama' ou 'openai'.")
    return handler


# ---------------------------------------------------------------------------
# Providers concretos
# ---------------------------------------------------------------------------

def _friendly_http_error(e: "httpx.HTTPStatusError", base_url: str, flavor: str, model: str) -> RuntimeError:
    status = e.response.status_code
    if status == 404:
        # Ollama (e outros) respondem 404 quando o "model" pedido não existe no servidor —
        # é o erro mais comum aqui, então vale uma mensagem específica em vez de genérica.
        return RuntimeError(
            f"O servidor de modelo respondeu 404 em {base_url} (flavor={flavor}) — o mais comum é o "
            f"nome do modelo estar errado. Você pediu model='{model}'. Confira o nome exato disponível "
            f"(ex: 'ollama list' ou 'curl {base_url}/api/tags') e ajuste AGNES_LLM_MODEL no .env."
        )
    return RuntimeError(
        f"O servidor de modelo respondeu {status} em {base_url} (flavor={flavor}). "
        f"Detalhe: {e.response.text[:200]}"
    )


class LocalLLMProvider(AIProvider):
    """Servidor de modelo rodando no MESMO dispositivo que este backend
    (loopback only — nunca sai da máquina). Cobre tanto um PC rodando
    Ollama quanto um celular rodando llama.cpp via Termux."""

    def __init__(self, port: Optional[int] = None, model: Optional[str] = None, flavor: Optional[str] = None):
        self.port = port or int(os.getenv("AGNES_LOCAL_LLM_PORT", "11434"))
        self.model = model or os.getenv("AGNES_LLM_MODEL", "llama3.1")
        self.flavor = flavor or os.getenv("AGNES_LLM_FLAVOR", "ollama")
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._handler = _resolve_flavor(self.flavor)

    async def chat(self, messages: list[dict]) -> str:
        try:
            return await self._handler(self.base_url, self.model, messages)
        except httpx.ConnectError as e:
            raise RuntimeError(
                f"Não consegui falar com o modelo local em {self.base_url} "
                f"(flavor={self.flavor}). Ele está rodando neste dispositivo?"
            ) from e
        except httpx.HTTPStatusError as e:
            raise _friendly_http_error(e, self.base_url, self.flavor, self.model) from e


class RemoteLLMProvider(AIProvider):
    """Servidor de modelo rodando em OUTRO dispositivo da rede (ex: backend
    e navegador no celular, modelo rodando no PC). Requer host configurado
    explicitamente — nunca adivinha um IP."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None,
                 model: Optional[str] = None, flavor: Optional[str] = None, use_https: Optional[bool] = None):
        self.host = host or os.getenv("AGNES_REMOTE_HOST")
        if not self.host:
            raise RuntimeError(
                "AGNES_REMOTE_HOST não configurado. Defina no .env o IP/host da "
                "máquina onde o modelo está rodando (ex: 192.168.0.42)."
            )
        self.port = port or int(os.getenv("AGNES_REMOTE_PORT", "11434"))
        self.model = model or os.getenv("AGNES_LLM_MODEL", "llama3.1")
        self.flavor = flavor or os.getenv("AGNES_LLM_FLAVOR", "ollama")
        https = use_https if use_https is not None else os.getenv("AGNES_REMOTE_HTTPS", "false").lower() == "true"
        scheme = "https" if https else "http"
        self.base_url = f"{scheme}://{self.host}:{self.port}"
        self._handler = _resolve_flavor(self.flavor)

    async def chat(self, messages: list[dict]) -> str:
        try:
            return await self._handler(self.base_url, self.model, messages)
        except httpx.ConnectError as e:
            raise RuntimeError(
                f"Não consegui alcançar {self.base_url} (flavor={self.flavor}). "
                f"Confira se o servidor remoto está rodando e acessível pela rede."
            ) from e
        except httpx.HTTPStatusError as e:
            raise _friendly_http_error(e, self.base_url, self.flavor, self.model) from e


class APIProvider(AIProvider):
    """Modelo hospedado por um serviço externo via API (OpenAI, Anthropic,
    OpenRouter, Groq, Together, etc.). Precisa de uma chave de API — que
    NUNCA fica no frontend nem no repositório, só no `.env` local
    (git-ignorado). O backend é quem anexa a chave na requisição; o
    frontend nunca vê nem manda essa chave."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None,
                 flavor: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = base_url or os.getenv("AGNES_API_BASE_URL", "https://api.openai.com")
        self.model = model or os.getenv("AGNES_LLM_MODEL", "gpt-4o-mini")
        self.flavor = flavor or os.getenv("AGNES_LLM_FLAVOR", "openai")
        self.api_key = api_key or os.getenv("AGNES_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "AGNES_API_KEY não configurado no .env — obrigatório quando AGNES_PROVIDER=api."
            )
        self._handler = _resolve_flavor(self.flavor)

    async def chat(self, messages: list[dict]) -> str:
        try:
            return await self._handler(self.base_url, self.model, messages, api_key=self.api_key)
        except httpx.HTTPStatusError as e:
            raise _friendly_http_error(e, self.base_url, self.flavor, self.model) from e
        except httpx.ConnectError as e:
            raise RuntimeError(f"Não consegui alcançar {self.base_url}.") from e


def get_provider() -> AIProvider:
    """Ponto único de escolha do provedor, controlado por AGNES_PROVIDER no
    .env ('local', 'remote' ou 'api'). Nada mais no backend precisa saber
    qual foi escolhido — só chama provider.chat(messages)."""
    kind = os.getenv("AGNES_PROVIDER", "local").strip().lower()
    if kind == "local":
        return LocalLLMProvider()
    if kind == "remote":
        return RemoteLLMProvider()
    if kind == "api":
        return APIProvider()
    raise RuntimeError(f"AGNES_PROVIDER inválido: '{kind}'. Use 'local', 'remote' ou 'api'.")
