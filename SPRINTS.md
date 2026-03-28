# SPRINTS.md - Planejamento integrado de execucao

Planejamento consolidado dos arquivos [`TODO.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\TODO.md), [`TODO2.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\TODO2.md) e [`TODO3.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\TODO3.md).

Objetivo:
- transformar os tres backlogs em uma sequencia de sprints executaveis
- reduzir troca de contexto entre base tecnica, produto do jogo e integracao regulada
- deixar claro o que depende do que

Premissas:
- sprint padrao de `2 semanas`
- time pequeno e senior, com foco principal em engenharia
- compliance, operador e certificadora entram como dependencias externas nas sprints mais avancadas

Legenda:
- `T1` = [`TODO.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\TODO.md)
- `T2` = [`TODO2.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\TODO2.md)
- `T3` = [`TODO3.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\TODO3.md)

---

## Visao geral

Regra de sequencia:
1. terminar o nucleo tecnico e operacional
2. fechar a experiencia comercial do jogo
3. preparar a integracao regulada como provider

Trilhas:
- `Trilha A`: produto atual e robustez (`T1`)
- `Trilha B`: regras de negocio e UX do jogo (`T3`)
- `Trilha C`: provider regulado e integracao com bet (`T2`)

---

## Sprint 1 - Fechamento tecnico critico

Foco:
- fechar o que ainda impede considerar a base tecnica madura

Escopo principal:
- `T1 / BT3`: calibracao real com evidencias da pista
- `T1 / BT2`: medicao inicial de gargalos de MJPEG e encode
- `T1 / Fase 3`: validacao operacional completa com `start.bat`

Itens:
- coletar casos reais com `E` na janela Python
- rodar `review_calibration_cases.py`
- recalibrar `conf`, `min_hits_to_count` e `min_bbox_area`
- medir CPU, stream e responsividade com navegador conectado
- validar o fluxo ponta a ponta com `start.bat`

Entregavel:
- base tecnica calibrada e validada em ambiente real

Gate de saida:
- item `EXTREMAMENTE NECESSARIO` do `BT3` resolvido
- performance base medida

---

## Sprint 2 - Produto do jogo v1 completo

Foco:
- fechar o `T3` no nivel de produto jogavel

Escopo principal:
- `T3`: `void` com motivo
- `T3`: perfis por camera
- `T3`: nomenclatura comercial final
- `T3`: historico comercial coerente

Itens:
- implementar `void` no backend e no frontend
- persistir motivo de anulacao
- parametrizar camera em `low_traffic`, `medium_traffic`, `high_traffic`
- revisar nomes publicos dos mercados
- ajustar cards, labels e mensagens finais

Entregavel:
- jogo `v1` fechado em regra de negocio

Gate de saida:
- round, settlement, `void` e perfis por camera funcionando sem ambiguidade

---

## Sprint 3 - Performance da experiencia

Foco:
- aliviar o navegador e separar visoes de jogador e operador

Escopo principal:
- `T3 / BN6`: performance da experiencia
- `T1 / BT1`: revisao de bundle e code splitting

Itens:
- separar `player view` e `operator view`
- remover da tela do jogador: deteccoes ao vivo, health e alertas tecnicos
- reduzir rerenders secundarios
- aplicar politica de economia em background
- validar perfil `balanced` no desktop e `lite` no mobile
- revisar bundle principal do Vite

Entregavel:
- experiencia principal leve e estavel

Gate de saida:
- navegador sem degradacao perceptivel na `player view`

---

## Sprint 4 - Fechamento do TODO principal

Foco:
- encerrar o restante do `T1` que ficou pendente para producao local/operacional

Escopo principal:
- `T1 / BT1`: tipagem melhor no frontend
- `T1 / BT4`: snapshots e politica de retencao
- `T1 / BT2`: estrategia explicita de stream por camera

Itens:
- melhorar tipos/contratos no frontend
- decidir politica de snapshots e exportacoes
- definir armazenamento externo futuro
- consolidar estrategia de qualidade MJPEG e resolucao por camera

Entregavel:
- `TODO.md` pronto para ser considerado praticamente fechado

Gate de saida:
- `T1` perto de `100%`, com excecao apenas de decisoes externas ou evolucoes opcionais

---

## Sprint 5 - Descoberta regulatoria e modelo provider

Foco:
- iniciar o `T2` de forma estrategica, sem ainda entrar em integracao profunda

Escopo principal:
- `T2 / Fase A`
- `T2 / Fase B`

Itens:
- fechar arquitetura alvo provider x operador
- definir RACI
- decidir provider-hosted vs embed
- definir trilha regulatoria e certificadora
- fechar politica de release, rollback e responsabilidades

Entregavel:
- documento de arquitetura e responsabilidade aprovado

Gate de saida:
- sem ambiguidade sobre o modelo de integracao

---

## Sprint 6 - Infra, seguranca e sessao

Foco:
- preparar o produto para integracao regulada real

Escopo principal:
- `T2 / Fase C`
- `T2 / Fase D`
- parte de `T2 / T3`

Itens:
- ambientes `dev`, `qa`, `cert`, `staging`, `prod`
- segredos e cofre seguro
- autenticacao server-to-server forte
- launch token assinado
- RBAC administrativo
- trilha de auditoria administrativa

Entregavel:
- fundacao segura e segregada por ambiente

Gate de saida:
- jogo apto para integrar com operador sem depender de `X-API-Key` simples

---

## Sprint 7 - Dados, wallet e contrato de integracao

Foco:
- fechar o contrato real com a operadora

Escopo principal:
- `T2 / Fase E`
- `T2 / Fase F`
- `T2 / T2`

Itens:
- minimizacao de PII
- data flow LGPD
- launch session
- balance, bet, settle, rollback e reconciliacao
- idempotencia e codigos de erro
- correlacao por `transaction_id`, `round_id` e `game_session_id`

Entregavel:
- contrato tecnico operator-provider pronto para homologacao

Gate de saida:
- integracao financeira e de sessao definida ponta a ponta

---

## Sprint 8 - Embed e experiencia dentro da bet

Foco:
- encaixar o jogo no ecossistema da operadora

Escopo principal:
- `T2 / Fase G`
- refinamentos finais de `T3` ligados a UX comercial

Itens:
- decidir entre rota dedicada ou `iframe`
- implementar theming por operador
- launch flow da bet para o jogo
- CSP, frame-ancestors e trusted origins
- estados de perda de sessao, manutencao e reconexao
- compatibilidade web e mobile webview

Entregavel:
- jogo embedavel em site `.bet.br`

Gate de saida:
- launch do jogo funcionando no ambiente da operadora

---

## Sprint 9 - Certificacao e homologacao

Foco:
- preparar release candidata para ambiente regulado

Escopo principal:
- `T2 / Fase H`

Itens:
- pacote de evidencias
- congelamento de versao
- testes com operador
- testes de resiliencia
- falha de wallet, rollback e reconciliacao
- pentest e remediacao

Entregavel:
- release pronta para certificacao/homologacao

Gate de saida:
- evidencias completas e validacao tecnica suficiente para submissao

---

## Sprint 10 - Operacao e rollout controlado

Foco:
- entrar em producao com risco controlado

Escopo principal:
- `T2 / Fase I`
- `T2 / Fase J`

Itens:
- dashboards por operador
- alertas e runbooks
- rollout por marca/operador
- feature flags
- hiper-care inicial
- criterio de `go/no-go`

Entregavel:
- jogo operavel em producao real

Gate de saida:
- rollout reversivel e monitorado

---

## Dependencias entre sprints

Dependencias criticas:
- `Sprint 1` antes de considerar o produto tecnicamente estavel
- `Sprint 2` antes de considerar o jogo comercialmente fechado
- `Sprint 3` antes de expandir o front para embed de operador
- `Sprint 5` antes de qualquer integracao forte de operador
- `Sprint 7` antes de homologacao real
- `Sprint 9` antes de producao regulada

Dependencias externas:
- operador
- compliance/juridico
- certificadora
- equipe de wallet/ledger da bet

---

## Macro-prioridade recomendada

Curto prazo:
1. `Sprint 1`
2. `Sprint 2`
3. `Sprint 3`

Medio prazo:
4. `Sprint 4`
5. `Sprint 5`
6. `Sprint 6`

Longo prazo:
7. `Sprint 7`
8. `Sprint 8`
9. `Sprint 9`
10. `Sprint 10`

---

## Definicao de sucesso

Sucesso tecnico:
- `T1` fechado com base robusta e validada

Sucesso de produto:
- `T3` fechado com jogo claro, leve e operavel

Sucesso regulado/comercial:
- `T2` fechado com integracao, certificacao e rollout controlado
