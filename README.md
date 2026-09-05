# Estudos — app de estudos (PWA)

App pessoal de estudos: plano semanal, cronômetro, banco de questões (com importador de PDF), guia de
estudos com progresso por matéria, metas de calendário, sincronização entre aparelhos por QR/código, e
personalização visual (tema, papel de parede, fonte, estilo dos cartões).

## Como publicar no GitHub Pages (grátis)

1. Crie um repositório novo no GitHub (pode ser público), por exemplo `estudos-app`.
2. Envie **todos os arquivos desta pasta** para a raiz do repositório (Add file → Upload files),
   mantendo os nomes exatamente como estão — sem colocar em subpasta.
3. Vá em **Settings → Pages**. Em "Source", escolha a branch `main` e a pasta `/ (root)`. Salve.
4. Espere cerca de 1 minuto. O link fica assim:
   `https://SEU-USUARIO.github.io/estudos-app/`
5. Abra esse link no Chrome do celular → menu (⋮) → **"Adicionar à tela inicial"**.
   Isso instala o app com ícone próprio, tela cheia e funcionamento offline básico.

## Arquivos

- `index.html` — o app inteiro (single-file, React + Babel via CDN)
- `manifest.json` — metadados do PWA (nome, ícone, cores)
- `sw.js` — service worker (cache offline do app shell)
- `icon-192.png`, `icon-512.png`, `icon-512-maskable.png` — ícones do app

## Coisas importantes de saber

- **Precisa ser https** (GitHub Pages já entrega assim automaticamente). Abrir o `index.html` direto do
  computador (`file://`) não ativa o PWA nem o service worker.
- **Sincronização entre aparelhos** (botão "Sincronizar com outro aparelho") depende de três bibliotecas
  externas carregadas por CDN (PeerJS, QRCode, jsQR) e de um serviço público gratuito de sinalização —
  funciona com internet nos dois aparelhos, mas é a parte mais experimental do app.
- **Backup**: mesmo com tudo funcionando, use "Exportar backup" de vez em quando (aba Matérias & Plano) —
  é o jeito mais confiável de nunca perder dados, independente de sincronização.
- Sem servidor próprio: os dados ficam no navegador de cada aparelho (mais o que for trocado via
  sincronização ou backup manual). Não há conta, login nem armazenamento central.

## Atualizando o app depois

Sempre que quiser uma nova versão, basta subir o `index.html` atualizado substituindo o antigo no mesmo
repositório (Add file → Upload files novamente, com o mesmo nome) — o GitHub Pages atualiza sozinho.
