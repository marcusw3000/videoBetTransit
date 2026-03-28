# TODO3.md - Regras de negocio e UX do jogo

Planejamento da camada comercial do jogo a ser reintroduzida depois da estabilizacao do estado `9230acf`.

Premissa:
- o codigo atual nao deve assumir ainda essa camada como implementada
- este arquivo descreve a proxima trilha de produto

---

## BN1 - Estrutura do round

- [ ] Definir round `v1` com duracao fixa
- [ ] Definir `bet_close_at`
- [ ] Definir estados: `open`, `closing`, `settling`, `settled`, `void`
- [ ] Definir settlement automatico e manual

Entregavel:
- ciclo de round fechado sem ambiguidade

## BN2 - Mercados

- [ ] Definir `Under`
- [ ] Definir `Range`
- [ ] Definir `Over`
- [ ] Definir `Exact`
- [ ] Definir nomenclatura comercial final

Entregavel:
- quatro mercados `v1` especificados

## BN3 - UI/UX

- [ ] Definir layout web
- [ ] Definir layout mobile
- [ ] Definir o que o jogador ve no stream
- [ ] Garantir regra visual: somente `mark line` e boxes para o cliente final
- [ ] Definir historico comercial curto na home
- [x] Definir principio de confianca da UX:
  - video como transparencia visual
  - backend como resultado oficial
  - fechamento antecipado como protecao de fairness

Entregavel:
- UX `v1` clara para jogador

## BN4 - Produto operacional

- [ ] Definir `void` com motivo
- [ ] Definir perfis por camera
- [ ] Definir trilha de auditoria de round
- [ ] Definir evidencias minimas por settlement
- [x] Assumir estrategia de curto prazo com HLS:
  - nao prometer "tempo real absoluto"
  - reforcar status do round, timer e settlement oficial
  - tratar o video como referencia visual do evento

Entregavel:
- produto jogavel e auditavel

## BN5 - Math e risco

- [ ] Definir targets por camera
- [ ] Definir faixas de `Range`
- [ ] Definir referencia inicial de odds
- [ ] Definir limites por mercado e round

Entregavel:
- camada comercial pronta para validacao com operador
