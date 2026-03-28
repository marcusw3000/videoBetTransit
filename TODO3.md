# TODO3.md - Regras de negocio do jogo

Especificacao inicial `v1` das regras de negocio do jogo, inspirada na referencia do concorrente, mas adaptada para um produto proprio.

Objetivo deste arquivo:
- fechar a primeira versao de round, mercados, settlement e UX
- servir como base unica para produto, engenharia, math, compliance e integracao com operador
- reduzir ambiguidade antes de implementar a camada comercial do jogo

Observacao:
- esta e uma definicao `v1` para execucao
- odds finais, margem, limites financeiros e certificados ainda dependem de validacao de math/compliance
- a primeira refletida no codigo ja entrou: rounds de `60s` e cards `Under / Range / Over / Exact` no frontend
- backend e frontend ja refletem `bet_close_at`, estados `open / closing / settling / settled` e resultado por mercado no settlement

---

## 1. Definicao do produto

Nome funcional:
- `Traffic Count Game`

Conceito:
- o jogo abre rounds curtos e repetidos
- o sistema conta quantos veiculos cruzam a `mark line`
- o jogador escolhe um mercado antes do fechamento das apostas
- no fim do round, o `final_count` e liquidado

Fonte de verdade:
- o `final_count` persistido no backend e a unica referencia valida para settlement

Diretriz visual obrigatoria:
- o cliente final ve apenas a `mark line` e as boxes de identificacao
- a `ROI` nao aparece para o jogador
- overlays operacionais, handles, textos tecnicos e modos de calibracao ficam restritos ao ambiente interno

---

## 2. Estrutura do round

### 2.1 Estados do round

- `open`
  - apostas liberadas
  - round em andamento

- `closing`
  - apostas fechadas
  - contagem segue ate o fim do round

- `settling`
  - round encerrado
  - sistema validando e liquidando

- `settled`
  - resultado final publicado
  - pagamentos/perdas consolidados

- `void`
  - round anulado
  - apostas devolvidas

### 2.2 Parametros fixados para v1

- duracao do round: `60s`
- fechamento de apostas: `10s` antes do fim
- settlement automatico: `sim`
- abertura do proximo round: `automatica`
- settlement manual: `permitido apenas para operacao/admin`

Linha do tempo:
1. `0s a 50s` -> `open`
2. `50s a 60s` -> `closing`
3. `apos 60s` -> `settling`
4. publicacao do resultado -> `settled` ou `void`

Identificadores minimos por round:
- `round_id`
- `camera_id`
- `created_at`
- `bet_close_at`
- `ends_at`
- `final_count`
- `settlement_status`

---

## 3. Mercados da versao v1

Na `v1`, o jogo tera sempre os quatro mercados abaixo:

1. `Under`
2. `Range`
3. `Over`
4. `Exact`

### 3.1 Under

Definicao:
- o jogador vence se `final_count < target_value`

Regra de empate:
- se `final_count == target_value`, perde

Uso:
- mercado simples
- risco moderado
- leitura imediata

### 3.2 Range

Definicao:
- o jogador vence se `range_min <= final_count <= range_max`

Regra:
- as faixas sao mutuamente exclusivas
- a ultima faixa pode ser aberta no topo

Uso:
- mercado principal da `v1`
- melhor equilibrio entre entendimento e distribuicao de risco

### 3.3 Over

Definicao:
- o jogador vence se `final_count > target_value`

Regra de empate:
- se `final_count == target_value`, perde

Uso:
- espelho do `Under`
- simples e direto

### 3.4 Exact

Definicao:
- o jogador vence se `final_count == exact_value`

Regra:
- valor selecionado em UI controlada
- nao usar input livre na `v1`

Uso:
- mercado de maior payout
- exposicao mais restrita

---

## 4. Parametrizacao por camera

Nem toda camera deve usar exatamente o mesmo perfil. A `v1` adota perfil por camera.

Cada camera tera:
- `under_over_target`
- `range_profile`
- `exact_max_value`
- `market_profile`

### 4.1 Perfis iniciais

Perfis:
- `low_traffic`
- `medium_traffic`
- `high_traffic`

### 4.2 Configuracao inicial recomendada

#### low_traffic
- `under_over_target = 12`
- `range = 0-6`, `7-12`, `13-18`, `19+`
- `exact_max_value = 25`

#### medium_traffic
- `under_over_target = 20`
- `range = 0-10`, `11-20`, `21-30`, `31+`
- `exact_max_value = 40`

#### high_traffic
- `under_over_target = 30`
- `range = 0-15`, `16-30`, `31-45`, `46+`
- `exact_max_value = 60`

Regra:
- camera usa um perfil base
- operador pode sobrescrever por camera

---

## 5. Estrutura comercial inicial

Hierarquia de mercado na `v1`:
1. `Range` como mercado principal
2. `Under` e `Over` como mercados simples de apoio
3. `Exact` como mercado premium

Diretrizes:
- os quatro mercados aparecem ao mesmo tempo na `v1`
- `Range` recebe mais destaque visual
- `Exact` recebe destaque por payout, mas com limite menor
- operador pode desligar mercados por camera em versoes futuras, mas na `v1` todos ficam ativos

---

## 6. Settlement

### 6.1 Settlement normal

- `Under` vence quando `final_count < target_value`
- `Over` vence quando `final_count > target_value`
- `Range` vence quando `range_min <= final_count <= range_max`
- `Exact` vence quando `final_count == exact_value`

### 6.2 Settlement automatico

Regra da `v1`:
- settlement automatico assim que o round termina e o `final_count` e consolidado
- status muda para `settling`
- resultado e publicado como `settled`

### 6.3 Settlement manual

Regra da `v1`:
- settlement manual nao e fluxo primario
- so entra em caso de excecao operacional
- toda intervencao manual deve gerar trilha de auditoria

### 6.4 Casos de void

O round deve ser anulado quando:
- stream cair e nao houver contagem confiavel ao fim do round
- engine falhar de forma critica antes do settlement
- backend nao conseguir consolidar o resultado com confianca operacional minima
- operador/admin invalidar o round por incidente tecnico relevante

Resultado do `void`:
- apostas devolvidas
- round marcado como `void`

### 6.5 Criterio operacional minimo de validade

Para a `v1`, round valido exige:
- stream operacional ate o fim do round
- engine com contagem final disponivel
- sem erro critico de settlement

Observacao:
- thresholds finos de confianca operacional podem ser refinados depois
- nesta fase, a regra e objetiva e simples para evitar ambiguidade

---

## 7. Math e odds da v1

### 7.1 Regra geral

As odds da `v1` sao fixas por perfil de camera e mercado, nao dinamicas durante o round.

Isso significa:
- odds publicadas no inicio do round
- odds travadas ate `bet_close_at`
- sem recotacao intra-round na `v1`

### 7.2 Estrutura comercial inicial de payout

Referencia inicial de produto:
- `Under`: `3.00x`
- `Range`: `2.25x`
- `Over`: `3.60x`
- `Exact`: `18.00x`

Observacao importante:
- estes valores sao referencia comercial inicial
- precisam ser validados com historico de contagem e math do operador

### 7.3 Regras de risco da v1

- `Range` com maior liquidez
- `Under` e `Over` com liquidez intermediaria
- `Exact` com menor limite de exposicao

---

## 8. Limites e risco

Definicao inicial da `v1`:
- cada mercado tem `min_bet` e `max_bet`
- cada round tem `max_liability`
- `Exact` tem teto menor que os demais mercados

Diretriz:
- o frontend nunca decide exposicao
- o backend/operator API valida exposicao e aceita/recusa aposta

Itens que ficam como configuracao por operador:
- aposta minima
- aposta maxima
- limite por jogador
- limite por round
- stop de venda por mercado

---

## 9. UX e front da v1

### 9.1 O que o jogador ve

Obrigatorio:
- nome da camera/local
- status do round
- tempo restante
- `round_id`
- stream ao vivo com `mark line` e boxes
- mercados disponiveis
- payout/odds
- ultimo resultado
- historico recente resumido

### 9.2 Web

Layout da `v1`:
- video ao vivo como ancora principal
- bloco lateral ou abaixo com os quatro mercados
- `Range` como card principal
- historico e regras em bloco secundario

### 9.3 Mobile

Layout da `v1`:
- topo compacto com camera, status e timer
- video logo abaixo
- mercados em lista ou grade vertical
- CTA fixo no rodape para confirmar aposta
- historico e regras em accordion

### 9.4 Estados de UI

Estados obrigatorios:
- `open`
- `closing`
- `settling`
- `settled`
- `void`
- `offline`
- `reconnecting`

Comportamento:
- em `open`, mercados editaveis
- em `closing`, mercados bloqueados para nova aposta
- em `settling`, UI aguardando resultado
- em `settled`, resultado e payout exibidos
- em `void`, mensagem de anulacao e devolucao

### 9.5 Regras visuais do stream

Permitido no stream do cliente:
- `mark line`
- boxes de identificacao

Proibido no stream do cliente:
- `ROI`
- handles de calibracao
- labels de debug
- overlays internos
- mensagens operacionais tecnicas

### 9.6 Transparencia

Obrigatorio mostrar:
- que a contagem considera a passagem pela `mark line`
- quando as apostas fecham
- `round_id`
- ultimo resultado validado
- politica simples de `void/cancelamento`

### 9.7 Performance da experiencia

Diretriz nova:
- a experiencia principal do jogador deve priorizar leveza, clareza e estabilidade antes de observabilidade detalhada

Regra de produto:
- a `player view` nao deve carregar tudo que a `operator view` mostra
- o cliente final recebe uma interface mais enxuta, com foco em video, timer, status, mercados e ultimo resultado

Elementos que devem ficar fora da `player view` padrao:
- lista detalhada de deteccoes ao vivo
- metricas operacionais
- alertas tecnicos
- historico muito profundo na mesma tela
- qualquer painel com cara de monitoramento interno

Elementos que devem permanecer na `player view`:
- stream com `mark line` e boxes
- status do round
- timer
- quatro mercados
- payout
- ultimo resultado
- historico comercial curto

Metas recomendadas para a `v1`:
- tempo de abertura percebido da tela principal: `<= 2s` em ambiente normal
- sem travamento perceptivel ao trocar entre `open`, `closing` e `settled`
- mobile deve operar em modo visual mais leve por padrao
- abas em segundo plano devem reduzir consumo de rede e processamento

Plano de performance priorizado:

1. Separar `player view` de `operator view`
- `player view` fica minimalista
- `operator view` concentra deteccoes, health, alertas e diagnostico

2. Reduzir atualizacoes nao essenciais na tela do jogador
- timer e status seguem em tempo real
- historico e dados secundarios atualizam em cadencia menor
- eventos tecnicos nao devem disparar rerender desnecessario da tela principal

3. Criar perfis de stream para entrega
- `high`
- `balanced`
- `lite`

Recomendacao inicial:
- desktop: `balanced`
- mobile: `lite`

4. Definir limites de densidade visual
- historico curto na home
- cards sem animacoes excessivas
- uma unica area principal de video
- sem blocos operacionais pesados na experiencia do jogador

5. Adotar modo de economia em background
- reduzir polling quando a aba nao esta visivel
- reduzir atualizacoes de paineis secundarios
- evitar custo desnecessario de render com a pagina em segundo plano

---

## 10. Auditoria, disputa e evidencias

Cada round da `v1` precisa ser auditavel com:
- `round_id`
- `camera_id`
- `count-events`
- `final_count`
- status final
- motivo de `void`, se houver

Evidencias desejadas:
- logs de round
- eventos de contagem
- snapshots, quando houver
- casos de calibracao, quando aplicavel

Regra:
- settlement manual ou `void` exige motivo registrado

---

## 11. Decisoes fechadas na v1

- [x] O jogo tera sempre quatro mercados na `v1`.
- [x] `Under` e `Over` usam o mesmo alvo por camera.
- [x] `Range` sera o mercado principal da `v1`.
- [x] `Exact` sera sempre disponivel na `v1`, com risco mais restrito.
- [x] O round dura `60s`.
- [x] As apostas fecham `10s` antes do fim.
- [x] Empate no alvo de `Under/Over` perde.
- [x] O cliente ve apenas `mark line` e boxes.
- [x] `void` devolve as apostas.

---

## 12. Backlog residual de negocio

### BN1 - Mercados
- [x] Fechar especificacao final de `Under`.
- [x] Fechar especificacao final de `Range`.
- [x] Fechar especificacao final de `Over`.
- [x] Fechar especificacao final de `Exact`.

### BN2 - Settlement
- [x] Fechar estados finais do round.
- [x] Fechar politica de anulacao/refund.
- [x] Fechar politica de revisao manual.

### BN3 - Math e risco
- [x] Definir targets por camera.
- [x] Definir faixas por camera.
- [ ] Validar odds alvo e margem com historico real.
- [ ] Definir limites e exposicao maxima por operador.

### BN4 - UX e apresentacao
- [ ] Definir nomenclatura comercial final dos mercados.
- [x] Definir cards e layout base dos mercados.
- [x] Definir como mostrar payout e regras.
- [x] Definir historico comercial relevante ao jogador.
- [x] Definir UI/UX base para web.
- [x] Definir UI/UX base para mobile.
- [x] Definir regra visual do stream para cliente final: somente `mark line` e boxes.

### BN5 - Compliance operacional
- [x] Definir criterio base de round valido.
- [x] Definir evidencias minimas de settlement.
- [x] Definir politica base de disputa e anulacao.
- [ ] Definir trilha de auditoria visivel ao operador em nivel de produto/backoffice.

### BN6 - Performance da experiencia
- [x] Definir a diretriz de separar `player view` e `operator view`.
- [x] Definir quais blocos nao devem ficar na tela principal do jogador.
- [x] Definir perfis de stream `high`, `balanced` e `lite`.
- [ ] Implementar uma `player view` realmente enxuta.
- [ ] Mover observabilidade detalhada para `operator view`.
- [ ] Reduzir atualizacoes e rerenders secundarios na tela principal.
- [ ] Aplicar politica de economia quando a aba estiver em background.
- [ ] Validar experiencia em mobile com perfil `lite`.

---

## 13. Ordem de execucao recomendada

1. implementar round `60s` com `bet_close_at = ends_at - 10s`
2. implementar os quatro mercados com settlement fechado
3. implementar `void` e trilha de motivo
4. parametrizar perfis de camera
5. separar `player view` e `operator view` para aliviar o navegador
6. implementar UI `v1` de web e mobile
7. validar odds e limites com dados reais

---

## 14. Definicao de pronto da v1

- round, fechamento e settlement estao implementados como especificado
- os quatro mercados funcionam sem ambiguidade
- `void` e settlement manual estao controlados
- o front mostra apenas `mark line` e boxes no stream do cliente
- a `player view` esta enxuta e nao carrega blocos operacionais desnecessarios
- perfil por camera existe
- resultado e auditavel
- odds e limites comerciais ja passaram por validacao de operador/math
