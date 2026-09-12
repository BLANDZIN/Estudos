# Backend da Agnes

Backend mínimo que dá à Agnes: conversa (via um modelo rodando em algum
lugar — local ou na rede, ver abaixo), memória própria (separada da LLM) e
um conjunto fechado de ferramentas que ela pode *pedir* para o app
executar — ela nunca executa nada diretamente.

## Provedor de IA: local ou remoto

`ai_provider.py` define duas formas de chegar até o modelo, escolhidas só
por configuração no `.env` (`AGNES_PROVIDER`), sem tocar em nenhum outro
arquivo:

- **`local`** — o servidor de modelo (Ollama, llama.cpp server...) roda no
  **mesmo dispositivo** que este backend. Isso cobre tanto "PC rodando
  Ollama" quanto "celular rodando llama.cpp via Termux, com este backend
  também rodando no celular". Sempre fala com `127.0.0.1` — nunca sai do
  aparelho, não existe superfície de rede a se preocupar.
- **`remote`** — o servidor de modelo está em **outro** dispositivo da rede
  (ex: você quer usar o modelo maior do PC a partir do celular). Precisa de
  `AGNES_REMOTE_HOST` configurado explicitamente.

Cada um ainda aceita um "flavor" de API (`AGNES_LLM_FLAVOR`): `ollama` (API
nativa do Ollama) ou `openai` (API compatível com OpenAI, que é o que o
`llama-server` do llama.cpp expõe, junto com LM Studio etc). Ou seja:
llama.cpp local no celular = `AGNES_PROVIDER=local` + `AGNES_LLM_FLAVOR=openai`.

## Segurança de rede — leia antes de usar `--host 0.0.0.0`

Por padrão (`uvicorn main:app`), o backend escuta só em `127.0.0.1`
(loopback) — só processos do próprio aparelho conseguem falar com ele. Esse
é o modo mais seguro e o único necessário quando o provedor é `local`.

`--host 0.0.0.0` faz o servidor escutar em **todas as interfaces de rede
disponíveis no aparelho** — não é "só a Wi-Fi de casa". Dependendo de como
o dispositivo está conectado (VPN, compartilhamento de internet, redes
corporativas, configuração incomum de roteador), isso pode ficar alcançável
por mais lugares do que você imagina. `0.0.0.0` em si **não garante** nada
sobre alcance — quem determina isso de verdade é a combinação de firewall
do sistema operacional + configuração do roteador/rede, não a flag do
uvicorn. Antes de usar `--host 0.0.0.0`:

- confirme que o firewall do seu SO está ativo e configurado como espera;
- confirme que seu roteador não tem encaminhamento de porta (port
  forwarding) pra essa porta — isso a exporia à internet de verdade;
- nunca use `ngrok`/túneis públicos apontando pra essa porta sem
  autenticação própria.

Continua valendo: a lista `AGNES_ALLOWED_ORIGINS` é a única coisa que
decide quais sites (origens) têm permissão de *chamar* o backend, mesmo que
ele esteja alcançável na rede — mantenha essa lista com só os domínios que
são seus.

## Como rodar

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edite AGNES_PROVIDER, AGNES_LLM_FLAVOR e o resto conforme seu setup

uvicorn main:app --reload --port 8787
```

Teste rápido: `curl http://127.0.0.1:8787/health` deve responder `{"ok": true, ...}`.

## Usando no celular

Tem dois caminhos bem diferentes — escolha o que faz sentido pro seu caso.

### Caminho A (recomendado): modelo rodando no próprio celular

Já que vocês rodam GGUF pequenos (0.5B/1B) via llama.cpp no Termux, este é
o caminho mais simples e sem os problemas de rede do Caminho B: backend e
modelo no mesmo aparelho, tudo em loopback.

1. No Termux, com o `llama-server` do llama.cpp rodando (ex: na porta 8080
   com um modelo GGUF pequeno carregado).
2. Neste `backend/`, configure no `.env`:
   ```
   AGNES_PROVIDER=local
   AGNES_LLM_FLAVOR=openai
   AGNES_LOCAL_LLM_PORT=8080
   ```
3. Rode o backend (`uvicorn main:app --port 8787`) — também no Termux, no
   mesmo celular.
4. No navegador do celular, abra o app → bolha ✨ → ⚙ → `http://127.0.0.1:8787`.

Como tudo roda no mesmo aparelho (loopback), **não existe o problema de
"conteúdo misto" do navegador** — `http://127.0.0.1` é uma exceção conhecida
das proteções de HTTPS, funciona mesmo com o app servido por `https://`
(GitHub Pages). Nenhum ajuste de navegador necessário.

### Caminho B: celular usando o modelo do PC pela rede

Pra quando você quer o modelo maior do PC, não o pequeno rodando no
celular.

1. Descubra o IP do PC na rede local: `python find_lan_ip.py`.
2. No PC, rode o backend aceitando conexões externas — e leia a seção de
   segurança de rede acima antes:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8787
   ```
3. No `.env` do PC, configure `AGNES_PROVIDER=remote` só se o *modelo*
   também estiver em outra máquina — se o modelo está no próprio PC junto
   com este backend, deixe `AGNES_PROVIDER=local` mesmo (o backend é local
   em relação ao modelo; é o *celular* que está remoto em relação ao
   *backend*, o que é outra coisa — ver `AGNES_ALLOWED_ORIGINS`).
4. Inclua a URL do seu GitHub Pages em `AGNES_ALLOWED_ORIGINS` e reinicie.
5. No celular: bolha ✨ → ⚙ → `http://<IP-DO-PC>:8787`.

**O problema chato deste caminho:** GitHub Pages serve o app por `https://`,
e navegadores bloqueiam uma página `https` chamando um endereço `http`
comum que não seja loopback ("conteúdo misto"). Isso não é uma proteção pra
desativar de vez — trate como um sinal de que, pra uso além de testes
rápidos, vale configurar HTTPS de verdade na frente do backend:

- **Testes rápidos, sem pressa de fazer certo**: permita "conteúdo
  inseguro" pra esse site nas configurações do site no Chrome do celular.
  Funciona, mas é por-navegador e some se limpar dados do site.
- **Caminho mais sólido pra manter funcionando**: coloque um reverse proxy
  com HTTPS de verdade na frente do backend (ex: [Caddy](https://caddyserver.com/),
  que gera certificado automaticamente até pra nomes locais com pouquíssima
  configuração) ou use uma ferramenta de malha de rede com HTTPS embutido
  (ex: [Tailscale](https://tailscale.com/kb/1153/enabling-https) com
  `tailscale serve`). Isso fica como próximo passo natural quando quiserem
  deixar o Caminho B estável — não implementei agora pra não adicionar peça
  nova sem necessidade imediata, mas a arquitetura (backend separado, sem
  segredo no frontend) já está pronta pra receber isso na frente.

## Endpoints

- `POST /chat` — `{ message, app_context? }` → `{ reply, action?, action_error? }`
- `GET /memory` — lista o que a Agnes guardou
- `POST /memory` — adiciona um fato manualmente (`{ category, value, key? }`)
- `DELETE /memory/{id}` — apaga um fato
- `GET /health` — checagem simples (mostra qual provedor está ativo)

## Segurança

- Nenhum segredo vive no código. Configuração sensível vai no `.env`
  (nunca commitado — está no `.gitignore`, junto com `agnes_memory.db` e
  qualquer `*.pem` de certificado).
- A LLM nunca recebe acesso a banco de dados, sistema de arquivos ou
  execução de código. Ela só pode pedir uma das ferramentas listadas em
  `tools.py`, validadas aqui e executadas pelo frontend.
- Trocar de provedor (local/remoto, Ollama/llama.cpp) é configuração em
  `ai_provider.py`/`.env` — a lógica de conversa, memória e ferramentas
  (`main.py`, `tools.py`, `memory.py`, `agnes_persona.py`) não muda.
