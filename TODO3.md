# TODO3.md - Regras de negocio e UX do jogo

Planejamento da camada comercial do jogo a ser reintroduzida depois da estabilizacao do estado `9230acf`.

Premissa:
- o codigo atual nao deve assumir ainda essa camada como implementada
- este arquivo descreve a proxima trilha de produto

---

## BN1 - Estrutura do round

Objetivo:
- transformar o round em uma unidade comercial fechada, previsivel e auditavel
- deixar claro quando o jogador ainda pode apostar, quando a contagem ja esta fechada e quando o resultado virou oficial

Regra alvo `v1`:
- cada round tem duracao fixa
- formato inicial implementado: `RODADA TURBO` com `2 minutos`
- cada round nasce com `round_id`, `created_at`, `bet_close_at`, `ends_at`, `settled_at` e `status`
- a live deve ser resetada automaticamente na virada do round para tentar reduzir drift acumulado entre rounds

Linha do tempo `v1`:
- `created_at`: inicio oficial do round
- `bet_close_at`: instante em que novas apostas deixam de ser aceitas
- `ends_at`: instante em que a contagem para fins de settlement deixa de receber novos eventos
- `settled_at`: instante em que o resultado oficial foi consolidado

Regra de fechamento de aposta:
- `bet_close_at` deve acontecer antes de `ends_at`
- referencia inicial recomendada: fechar apostas `30 segundos` antes do fim
- o objetivo do fechamento antecipado e absorver latencia residual sem depender de promessas de "tempo real absoluto"

Estados do round:
- `open`: apostas abertas e contagem em andamento
- `closing`: apostas fechadas e contagem ainda em andamento ate `ends_at`
- `settling`: janela curta de consolidacao tecnica e persistencia do resultado
- `settled`: resultado oficial consolidado e pronto para historico/settlement
- `void`: round anulado por falha tecnica ou criterio operacional definido

Transicoes esperadas:
- `open -> closing`: ao atingir `bet_close_at`
- `closing -> settling`: ao atingir `ends_at`
- `settling -> settled`: quando o backend consolidar o resultado oficial
- `open|closing|settling -> void`: quando houver falha relevante que invalide o round
- `settled -> novo round open`: rollover automatico com novo `round_id`

Settlement:
- settlement automatico deve existir como fluxo padrao
- settlement manual deve existir como contingencia operacional controlada
- a fonte oficial do resultado continua sendo o backend persistido
- a UI nao deve sugerir que o video sozinho decide o resultado

Checklist de implementacao:
- [x] Fixar a duracao oficial do round `v1`
  - `RODADA TURBO`: `2 minutos`
- [x] Fixar a antecedencia oficial de `bet_close_at`
  - fechamento `30 segundos` antes do fim
- [ ] Persistir `created_at`, `bet_close_at`, `ends_at`, `settled_at` e `status`
- [ ] Garantir transicao automatica entre `open`, `closing`, `settling` e `settled`
- [ ] Garantir `void` com motivo estruturado
- [ ] Garantir settlement manual com trilha de auditoria
- [ ] Resetar automaticamente a live na virada do round
- [ ] Garantir que frontend, backend e engine usem o mesmo `round_id`

Entregavel:
- ciclo de round fechado sem ambiguidade

## BN2 - Mercados

Objetivo:
- transformar a contagem final do round em mercados simples de entender e liquidar
- manter um portfolio curto no `v1`, com boa leitura para o jogador e baixa ambiguidade operacional

Portfolio inicial `v1`:
- `Under`
- `Range`
- `Over`
- `Exact`

Definicao operacional dos mercados:
- `Under`: vence quando a contagem final fica abaixo do target definido
- `Range`: vence quando a contagem final cai dentro da faixa fechada definida
- `Over`: vence quando a contagem final supera o target definido
- `Exact`: vence quando a contagem final fecha exatamente no target definido

Regra de settlement:
- somente a contagem final oficial do backend decide o resultado
- o settlement deve marcar explicitamente quais mercados venceram e quais perderam
- o historico deve exibir payout/odds e mercado vencedor sem exigir interpretacao tecnica do jogador

Decisao inicial implementada:
- target inicial de referencia: `20`
- `Under 20`
- `Range 11-20`
- `Over 20`
- `Exact 20`

Pontos a fechar em produto:
- confirmar se a nomenclatura comercial final deve ser em ingles (`Under`, `Over`, `Exact`) ou localizada
- confirmar se `Range` continua unico no `v1` ou se vira multiplas faixas por camera
- confirmar se o target `20` sera global ou por camera

Checklist de implementacao:
- [x] Definir `Under`
- [x] Definir `Range`
- [x] Definir `Over`
- [x] Definir `Exact`
- [x] Definir portfolio inicial `v1`
- [ ] Definir nomenclatura comercial final
- [ ] Expor claramente no front a descricao comercial de cada mercado
- [ ] Validar se a mesma composicao de mercados serve para todas as cameras

Entregavel:
- quatro mercados `v1` especificados

## BN3 - UI/UX

Objetivo:
- apresentar a rodada como um produto de aposta simples, rapido e confiavel
- reduzir ao maximo qualquer leitura de "debug" ou "ferramenta interna"

Principios de UX:
- o jogador deve entender em poucos segundos qual rodada esta aberta, quanto tempo falta e quais mercados estao em jogo
- a interface deve priorizar status do round, timer, contagem atual e mercados
- o video deve funcionar como transparencia visual do evento, nao como painel tecnico

Regra visual do stream:
- o cliente final deve ver apenas:
  - `mark line`
  - boxes dos veiculos
- o cliente final nao deve ver:
  - `ROI`
  - ids tecnicos
  - centros de ancora
  - contador debug renderizado no frame
  - informacoes internas de operacao

Layout `v1`:
- hero com identificacao do produto e tipo de rodada
- badge de status comercial do round
- card de video
- card de contagem atual
- card de timer
- grade de mercados
- historico curto de resultados recentes

Direcao mobile:
- video primeiro
- status e timer logo abaixo
- mercados em pilha vertical
- historico curto no fim da pagina

Decisao inicial implementada:
- destaque de `RODADA TURBO · 2 MINUTOS`
- timer adaptado para mostrar abertura de aposta e fechamento de rodada
- reset automatico da live na virada do round
- stream do cliente reduzido para linha + boxes

Checklist de implementacao:
- [x] Definir layout web
- [ ] Definir layout mobile
- [x] Definir o que o jogador ve no stream
- [x] Garantir regra visual: somente `mark line` e boxes para o cliente final
- [x] Definir historico comercial curto na home
- [x] Definir principio de confianca da UX:
  - video como transparencia visual
  - backend como resultado oficial
  - fechamento antecipado como protecao de fairness
- [ ] Exibir naming comercial final dos mercados na home
- [ ] Validar copy final de status (`Apostas Abertas`, `Apostas Fechadas`, `Apurando`, etc.)

Entregavel:
- UX `v1` clara para jogador

## BN4 - Produto operacional

Objetivo:
- garantir que o produto seja operavel, auditavel e defensavel em disputa
- separar claramente a experiencia do jogador da camada de operacao e contingencia

Politica de `void`:
- `void` deve existir como estado oficial
- todo `void` deve ter motivo estruturado
- exemplos de motivo:
  - perda relevante da stream
  - indisponibilidade do backend oficial
  - falha de integridade da contagem
  - intervencao operacional autorizada

Perfis por camera:
- cada camera pode precisar de:
  - target comercial proprio
  - ranges proprios
  - perfil de odds proprio
  - thresholds tecnicos proprios
  - politica de operacao propria

Trilha de auditoria por round:
- `round_id`
- `camera_id`
- `created_at`
- `bet_close_at`
- `ends_at`
- `settled_at` ou `void_at`
- `status`
- `final_count`
- mercados vencedores
- eventos de contagem recebidos
- snapshots/evidencias quando aplicavel

Evidencias minimas por settlement:
- lista de `count-events`
- total final consolidado
- motivo de `void`, quando houver
- timestamps de lifecycle do round
- vinculo com a camera/perfil utilizado

Decisao operacional atual:
- curto prazo segue com HLS e transparencia controlada
- backend continua como fonte oficial do resultado
- reset automatico da live na virada do round passa a fazer parte da regra operacional

Checklist de implementacao:
- [ ] Definir `void` com motivo
- [ ] Definir perfis por camera
- [ ] Definir trilha de auditoria de round
- [ ] Definir evidencias minimas por settlement
- [x] Assumir estrategia de curto prazo com HLS:
  - nao prometer "tempo real absoluto"
  - reforcar status do round, timer e settlement oficial
  - tratar o video como referencia visual do evento
- [ ] Persistir `settled_at` e motivo de `void`
- [ ] Expor historico operacional suficiente para revisao e disputa

Entregavel:
- produto jogavel e auditavel

## BN5 - Math e risco

Objetivo:
- calibrar os mercados para que sejam comercialmente interessantes sem ficar descolados da realidade de cada camera
- transformar dados de fluxo em pricing e limites defensaveis

Camadas de decisao:
- target por camera
- ranges por camera
- odds por mercado
- limite maximo por aposta
- limite agregado por round

Direcao inicial:
- usar `20` como target de referencia do `v1`
- manter portfolio curto para aprender distribuicao real de contagem por camera
- revisar odds e faixas com historico real antes de expandir o cardapio

Perguntas de math ainda abertas:
- qual e a distribuicao real de contagem por camera em janelas de 2 minutos
- qual faixa de `Range` concentra volume sem ficar dominante demais
- `Exact` deve existir em todas as cameras ou apenas em algumas com distribuicao mais previsivel
- qual payout maximo e aceitavel para a `RODADA TURBO`

Checklist de implementacao:
- [ ] Definir targets por camera
- [ ] Definir faixas de `Range`
- [ ] Definir referencia inicial de odds
- [ ] Definir limites por mercado e round
- [ ] Validar o target `20` com historico real
- [ ] Revisar portfolio `v1` com operador/math
- [ ] Definir guardrails de exposicao por rodada turbo

Entregavel:
- camada comercial pronta para validacao com operador
