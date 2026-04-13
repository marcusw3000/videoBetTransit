# Plano de Execucao - videoBetTransit Provider

Este documento transforma os pontos consolidados de [`TODO.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\TODO.md), [`TODO2.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\TODO2.md) e [`TODO3.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\TODO3.md) em um plano de execucao unico, orientado a entrega.

Objetivo:

- levar o projeto do estado atual para um produto `provider-ready`
- organizar a evolucao por fases executaveis
- definir dependencias, entregaveis, validacoes e criterios de aceite
- reduzir ambiguidade entre backlog tecnico, produto, operacao e compliance

## 1. Resultado Final Esperado

Ao final da execucao, o projeto deve operar como um provider de jogo live com:

- `vision-worker` como motor operacional de captura, deteccao e anotacao
- `round engine` como fonte oficial do resultado
- `provider API` para integracao com operadoras
- `ops API` e backoffice para calibracao, suporte e auditoria
- persistencia de rounds, eventos, evidencias e configuracoes
- trilha de auditoria, `void`, reprocessamento e reconciliacao
- readiness para rollout regulado e certificacao

## 2. Premissas de Execucao

Premissas assumidas para este plano:

- o `vision-worker` e o entrypoint oficial do worker Python
- a esteira de streams com ROI e mark line por perfil ja existe no fluxo atual
- Supabase pode ser usado como camada operacional e administrativa
- o backend persistido deve ser a fonte oficial do resultado
- o video e evidencia operacional e UX, nao soberania de settlement

Principios que guiam todas as fases:

- congelar configuracao por round
- fechar apostas antes do fim do round
- tratar `void` como fluxo formal
- manter trilha de auditoria forte
- separar operacao interna de contrato com operadora

## 3. Frentes de Trabalho

O plano esta organizado em seis frentes paralelas, mas com ordem de dependencia clara:

### 3.1 Core de jogo

- `vision-worker`
- `round engine`
- persistencia de rounds e eventos
- consolidacao de resultado

### 3.2 Integracao com operador

- `provider API`
- webhooks
- wallet contract
- reconciliacao

### 3.3 Produto e UX

- lifecycle comercial do round
- mercados `Under`, `Range`, `Over`, `Exact`
- interface embedada e experiencia do jogador

### 3.4 Operacao e suporte

- esteira de streams
- calibracao por camera
- incidentes
- replay e evidencias

### 3.5 Seguranca e compliance

- autenticacao server-to-server
- RBAC
- trilha administrativa
- LGPD
- pacote para certificacao

### 3.6 Plataforma e rollout

- ambientes
- monitoracao
- alertas
- release e rollback
- rollout por operador e camera

## 4. Ordem de Execucao Recomendada

Executar nesta ordem:

1. consolidar a base operacional atual
2. formalizar o `round engine`
3. persistir eventos e evidencias
4. expor `provider API` e webhooks
5. fechar contrato financeiro e reconciliacao
6. construir backoffice operacional
7. implementar seguranca, auditoria e compliance
8. preparar rollout regulado e escala

## 5. Fase 0 - Consolidacao da Base Atual

### Objetivo

Transformar o estado atual em uma base unica e estavel para evolucao como provider.

### Escopo

- consolidar `vision-worker` como fluxo principal
- manter a esteira de streams no worker oficial
- garantir persistencia local e sincronizacao operacional
- validar startup, health e operacao basica
- remover ambiguidades entre entrypoints e configs

### Entregaveis

- `vision-worker` definido como entrypoint oficial
- `config.json` do worker contendo stream profiles e integracao operacional
- esteira funcionando com `Carregar`, `Salvar na Esteira` e reaplicacao de ROI/line
- health operacional cobrindo stream, backend e pipeline
- documentacao curta da arquitetura atual

### Dependencias

- nenhuma

### Riscos

- split-brain entre app raiz e worker
- configuracoes espalhadas em mais de um arquivo
- regressao na troca de stream em runtime

### Validacao

- subir pelo `start.bat`
- confirmar abertura do worker correto
- carregar stream salva
- trocar perfil e validar reaplicacao de ROI/line
- validar `/health`

### Definicao de pronto

- existe um unico fluxo Python oficial
- a esteira funciona no entrypoint real
- configuracao operacional relevante esta consolidada

## 6. Fase 1 - Provider Core

### Objetivo

Criar o nucleo soberano do jogo, separando captura visual de resultado oficial.

### Escopo

- extrair e formalizar `round engine`
- definir lifecycle oficial do round
- persistir `rounds`, `crossing_events` e `round_events`
- consolidar timestamps do round
- preparar settlement automatico e manual

### Entregaveis

- modulo de `round engine`
- tabela `rounds`
- tabela `crossing_events`
- tabela `round_events`
- transicoes automaticas `open`, `closing`, `settling`, `settled`, `void`
- persistencia de `created_at`, `bet_close_at`, `ends_at`, `settled_at`

### Dependencias

- Fase 0 concluida

### Riscos

- misturar logica de UI com logica oficial de settlement
- divergencia de `round_id` entre worker, backend e front
- transicoes de estado inconsistentes

### Validacao

- testes de integracao do backend cobrindo lifecycle
- simulacao de round completo
- simulacao de `void`
- verificacao de consistencia de `round_id`

### Definicao de pronto

- o backend decide o resultado oficial
- todo round tem lifecycle fechado e persistido
- `void` ja existe como estado formal

## 7. Fase 2 - Regras de Jogo e Mercados

### Objetivo

Transformar a contagem tecnica em um produto comercial jogavel e auditavel.

### Escopo

- separar `round normal` de `rodada turbo`
- decidir `rodada turbo` por regra oficial do backend
- manter `bet_close_at` antes de `ends_at`
- formalizar mercados `Under`, `Range`, `Over`, `Exact`
- parametrizar target, ranges e odds por modo de round
- congelar configuracao por round

### Entregaveis

- especificacao de round `v1`
- composicao inicial de mercados `v1` por `round_mode`
- regra de elegibilidade e sorteio da `rodada turbo`
- modelo de configuracao comercial global `v1`
- regra de `config freeze`
- resultado final contendo mercados vencedores

### Dependencias

- Fase 1 concluida

### Riscos

- mercados mal definidos para a distribuicao real da camera
- alteracao operacional durante round aberto
- settlement sem explicabilidade suficiente

### Validacao

- simular rounds com contagens diferentes
- validar vencedor por mercado
- validar carencia de `turbo` apos troca de `stream profile`
- validar sorteio de `turbo` somente quando elegivel
- validar bloqueio de alteracao de perfil/ROI/line durante round
- revisar configuracao comercial por modo de round

### Definicao de pronto

- existe round comercial fechado
- os mercados podem ser liquidados com base no resultado oficial
- nenhuma configuracao critica muda em round aberto

Estado atual da Fase 2:

- `roundMode` ja existe no backend e na API como `normal` ou `turbo`
- a `rodada turbo` ja e decidida pelo backend com carencia de 5 rounds apos troca de `stream profile`
- o worker ja notifica o backend quando o `stream profile` ativo muda
- os mercados ja nascem congelados no round conforme o modo selecionado
- frontend, historico e admin ja exibem `roundMode` e nome comercial do round
- as pendencias principais agora sao refinamento comercial, calibracao dos mercados e freeze operacional completo

## 8. Fase 3 - Contrato com Operadora

### Objetivo

Permitir integracao real entre provider e operadora com contrato tecnico versionado.

### Escopo

- definir `provider API`
- implementar webhooks
- definir chaves tecnicas e idempotencia
- padronizar erros e timeouts
- preparar contrato para homologacao

### Entregaveis

- contrato de API versionado
- endpoints de round, sessao, consulta e reconciliacao
- assinatura HMAC de webhooks
- politica de retry e DLQ
- tabela `webhook_deliveries`
- documentacao de payloads

### Dependencias

- Fase 1 concluida
- Fase 2 suficientemente definida

### Riscos

- payloads sem versionamento
- duplicidade por ausencia de idempotencia
- falha silenciosa em webhook

### Validacao

- testes de integracao por endpoint
- teste de replay de webhook
- teste de retry com falha artificial
- teste de idempotencia com mesma requisicao repetida

### Definicao de pronto

- operadora consegue consumir round e resultado por contrato formal
- webhooks sao rastreaveis e reprocessaveis
- erros e codigos de negocio estao padronizados

## 9. Fase 4 - Wallet, Settlement e Reconciliacao

### Objetivo

Fechar o fluxo financeiro entre jogo e operadora.

### Escopo

- consolidar `bet ledger` interno do provider
- definir `balance`, `settle`, `rollback`
- suportar `seamless wallet` e preparar `transfer wallet`
- gerar reconciliacao diaria
- garantir consistencia entre round, transacao e settlement

### Entregaveis

- tabela `bets` soberana no backend com snapshot congelado do mercado comprado
- contrato financeiro provider-operadora
- suporte a `transaction_id`, `round_id`, `game_session_id`
- relatorio de reconciliacao diaria
- codigos de erro financeiros
- rollback de settlement quando necessario

### Dependencias

- Fase 3 concluida

### Riscos

- settlement duplicado
- divergencia entre resultado do round e settlement financeiro
- falta de trilha para suporte e disputa

### Validacao

- criacao idempotente de aposta por `transaction_id`
- fluxo completo de aposta e settlement em ambiente de homologacao
- teste de rollback
- comparacao entre reconciliacao e eventos do dia

### Definicao de pronto

- `bet ledger` existe e reconstrui a aposta sem depender de config viva
- o contrato financeiro esta homologavel
- settlement e rollback sao auditaveis
- reconciliacao diaria fecha com os eventos persistidos

## 10. Fase 5 - Operacao, Backoffice e Evidencias

### Objetivo

Dar capacidade de operar, investigar e defender o produto em producao.

### Escopo

- criar backoffice do provider
- exibir timeline do round
- suportar replay e export de evidencias
- tratar incidentes e `void` manual controlado
- preparar reprocessamento de round

### Entregaveis

- tela de timeline por round
- visualizacao de eventos, snapshots e stream profile
- replay operacional
- export de evidencias
- fluxo de incidente
- runbooks operacionais

### Dependencias

- Fase 1 concluida
- Fase 3 concluida

### Riscos

- depender de acesso ao banco para suporte manual
- falta de evidencia em disputa
- operacao sem meios para reenvio e contingencia

### Validacao

- abrir round antigo e revisar timeline
- exportar evidencias de settlement
- reprocessar round em ambiente de teste
- reenviar webhook manualmente

### Definicao de pronto

- suporte consegue investigar round sem acesso tecnico direto ao banco
- existe evidencia minima por round
- `void` manual e reenvio de webhook sao controlados

## 11. Fase 6 - Seguranca, Auditoria e Compliance

### Objetivo

Preparar o produto para operar com controles compativeis com ambiente regulado.

### Escopo

- launch token assinado
- autenticacao server-to-server
- RBAC administrativo
- trilha de auditoria administrativa
- LGPD e retencao
- pacote inicial de certificacao

### Entregaveis

- modelo de autenticacao entre operadora e provider
- RBAC com perfis `ops_viewer`, `ops_admin`, `risk_admin`, `support_readonly`
- auditoria de alteracao de stream, ROI, line, `void` e override
- politica de retencao
- pacote de evidencias por round
- estrategia de hash chain

### Dependencias

- Fases 1 a 5 suficientemente estaveis

### Riscos

- segredos mal segregados por ambiente
- alteracao administrativa sem rastreabilidade
- falta de pacote defensavel para auditoria

### Validacao

- revisar logs administrativos
- validar segregacao por ambiente
- validar acesso por perfil
- montar pacote de evidencia completo de um round

### Definicao de pronto

- toda acao sensivel fica auditada
- existe segregacao de acesso e ambiente
- o produto tem base documental para certificacao

## 12. Fase 7 - Embed, Rollout e Escala

### Objetivo

Colocar o produto em rota de entrada controlada em operadoras reais.

### Escopo

- definir experiencia embedada
- aplicar `trusted origins`, CSP e frame policy
- preparar rollout por operador, camera e ambiente
- implementar monitoracao e alertas por camada
- adicionar guardrails de risco e exposicao

### Entregaveis

- estrategia de embed
- politica de rollout
- feature flags por operador e camera
- health por camada
- paineis e alertas operacionais
- checklist de go-live

### Dependencias

- Fases 1 a 6 em nivel estavel

### Riscos

- rollout sem observabilidade suficiente
- comportamento diferente por operador sem isolamento

## 12.1 Security Review Atual

Data de referencia desta revisao:

- `2026-04-12`

Escopo revisado:

- `frontend/src/App.jsx`
- `frontend/src/embed.js`
- `frontend/src/services/betApi.js`
- `backend/TrafficCounter.Api/Controllers/BetsController.cs`
- `backend/TrafficCounter.Api/Controllers/InternalController.cs`
- `backend/TrafficCounter.Api/Services/BetService.cs`
- `backend/TrafficCounter.Api/Security/RequireApiKeyAttribute.cs`
- `backend/TrafficCounter.Api/appsettings.json`

Resumo executivo:

- o frontend nao parece conseguir alterar o resultado oficial do round nem as odds soberanas do settlement
- o backend recalcula `market`, `odds` e `potential_payout` a partir do round oficial
- porem a superficie publica de aposta ainda confia demais no browser para identidade, contexto e valor de stake
- no estado atual, o produto nao deve ser tratado como pronto para integracao real com operadora sem endurecimento de autenticacao e contrato financeiro

Achados principais:

1. `Alta` - o payload de aposta pode ser adulterado via DevTools ou chamada direta da API publica

- hoje `stakeAmount`, `playerRef`, `operatorRef` e `metadataJson` saem do browser
- a rota publica `POST /bets` aceita chamada direta sem autenticacao de operadora
- isso permite forjar identidade logica, enviar stake arbitrario e ignorar o fluxo esperado da UI

2. `Alta` - falta vinculo criptografico entre sessao embedada e contexto do jogador

- `gameSessionId`, `playerRef`, `operatorRef`, `currency` e parte do contexto comercial chegam por query string ou config global do embed
- esses campos sao uteis para UX e correlacao, mas nao devem ser tratados como fonte soberana
- sem launch token assinado ou sessao emitida pelo backend, o provider nao consegue confiar na origem do jogador

3. `Alta` - endpoints internos dependem de `X-API-Key`, mas a protecao pode ficar efetivamente desligada se a chave estiver vazia

- o atributo `RequireApiKey` libera a requisicao quando `Security:BackendApiKey` estiver em branco
- isso e aceitavel apenas para desenvolvimento local controlado
- em ambiente real, startup deve falhar se a chave obrigatoria nao existir

4. `Media` - o backend valida janela do round e mercado oficial, mas ainda nao aplica limites de risco suficientes

- existe validacao de `round open`, `betCloseAt` e pertencimento do `marketId` ao round
- isso protege odds e settlement contra manipulacao simples do front
- porem ainda faltam limite de stake, validacao de moeda por operadora, checagem de saldo e contrato de wallet server-to-server

5. `Media` - integracao de embed ainda esta frouxa para ambiente multioperadora

- o embed usa `postMessage` com target `*`
- a estrategia atual ainda nao fixa `trusted origins`, CSP e `frame-ancestors`
- isso nao muda settlement por si so, mas amplia risco de integracao insegura e vazamento de eventos

6. `Media` - trilha de integridade ainda nao esta endurecida

- `EnforceHashChain` esta desabilitado no estado atual
- isso reduz a capacidade de provar imutabilidade forte de eventos e resultado em disputa ou auditoria

7. `Baixa` - existe risco de vazamento acidental de contexto operacional em logs e metadados

- `metadataJson` e campos opcionais do cliente sao persistidos
- sem contrato estrito de schema e minimizacao de PII, ha espaco para gravar dados alem do necessario

Conclusao pratica:

- o sistema ja separa razoavelmente bem `frontend` de `resultado oficial`
- o principal risco atual nao e o jogador mudar o settlement pelo console
- o principal risco atual e aceitar entrada de aposta, identidade e contexto demais a partir de um cliente nao confiavel
- para entrar em bet real, a aposta precisa sair de um contrato autenticado entre operadora e provider, nao de um payload livre do browser

Hardening minimo antes de operadora:

- remover a confianca em `playerRef`, `operatorRef`, `currency` e `gameSessionId` enviados pelo browser sem assinatura
- introduzir `launch token` assinado e de curta duracao para abrir o jogo embedado
- trocar a aceitacao publica de aposta por fluxo `server-to-server` ou por token de sessao assinado emitido pelo provider
- falhar startup se `BackendApiKey` estiver vazio fora de ambiente local
- aplicar `trusted origins`, `frame-ancestors`, CSP e validacao de origem no `postMessage`
- implementar limites de stake, validacao por operadora e contrato de wallet
- ativar e verificar `hash chain` para eventos e resultado oficial

Decisao recomendada:

- tratar o frontend como canal de apresentacao e captura de intencao
- tratar o backend do provider como unica fonte soberana de round, mercado, aceite, wallet e settlement
- nao liberar homologacao com operadora antes de concluir o endurecimento de `EP13`, `EP14` e `EP15`
- exposicao comercial mal calibrada

### Validacao

- go-live controlado em ambiente de staging
- smoke test por operador
- simulacao de incidente de stream e indisponibilidade parcial

### Definicao de pronto

- o produto pode entrar em producao por rollout controlado
- alertas e rollback operacional existem
- cada operador pode ser habilitado de forma isolada

## 13. Dependencias Criticas Entre Fases

As principais dependencias do plano sao:

- Fase 0 antes de qualquer expansao estrutural
- Fase 1 antes de contrato serio com operadora
- Fase 2 antes de UX final e settlement comercial
- Fase 3 antes de homologacao externa
- Fase 4 antes de operacao com dinheiro real
- Fase 5 antes de escala operacional
- Fase 6 antes de certificacao e go-live regulado
- Fase 7 somente com monitoracao e governanca minimamente maduras

## 14. Modelo de Dados Prioritario

As primeiras entidades que precisam existir no plano de execucao sao:

- `stream_profiles`
- `game_sessions`
- `rounds`
- `markets`
- `crossing_events`
- `round_events`
- `webhook_deliveries`
- `incidents`
- `operators`
- `operator_brands`

Ordem recomendada de implementacao:

1. `rounds`
2. `crossing_events`
3. `round_events`
4. `markets`
5. `webhook_deliveries`
6. `incidents`
7. `operators` e `operator_brands`

## 15. Plano Tecnico Imediato

Se o objetivo for executar o plano no codigo atual, a sequencia imediata recomendada e:

1. consolidar definitivamente o `vision-worker` e suas configs
2. modelar tabelas de `rounds`, `crossing_events` e `round_events`
3. extrair `round engine` do backend atual
4. garantir `round_id` consistente entre worker, backend e front
5. implementar `void` estruturado
6. criar `provider API`
7. criar `webhook_deliveries`
8. montar backoffice minimo de timeline e evidencias
9. adicionar autenticacao, auditoria e RBAC
10. fechar reconciliacao, rollout e pacote regulatorio

## 16. Leitura do Estado Atual do Repositorio

Analisando a estrutura atual do codigo, o projeto ja avancou materialmente pela Fase 1 e abriu a base da Fase 5:

- `vision-worker\app.py` esta tratado como entrypoint operacional efetivo, com a raiz preservada como shim legado
- ja existem `rounds`, `round_markets`, `crossing_events` e `round_events` persistidos no backend
- o lifecycle oficial do round ja cobre `open`, `closing`, `settling`, `settled` e `void`
- o worker ja envia `round_id`, `camera_id`, `stream_profile_id`, `count_before`, `count_after` e `event_hash`
- o backend ja trata `round-count-event` com idempotencia e vinculo auditavel ao round oficial
- os endpoints `GET /rounds/{roundId}/count-events` e `GET /rounds/{roundId}/timeline` ja respondem leitura real persistida
- o frontend de mercado ja consome o lifecycle oficial do backend
- o admin ja tem base de backoffice com resumo oficial, timeline, crossings e busca de rounds
- o stream atual continua precisando ser preservado como baseline operacional congelado

Conclusao pratica:

- a Fase 0 ainda tem pendencias operacionais, mas deixou de ser o gargalo principal de arquitetura
- a Fase 1 esta funcionalmente estabelecida no backend e integrada ao worker
- a Fase 5 foi iniciada antes de concluir freeze operacional, incidentes e evidencias exportaveis
- o maior risco imediato deixou de ser "falta de round engine" e passou a ser "permitir contaminacao operacional do round ou operar sem guardrails suficientes"

## 17. Proximo Passo Recomendado Agora

O proximo passo deve ser endurecer a operacao do round oficial, sem reabrir a frente do stream como eixo principal.

### Objetivo imediato

Impedir que alteracoes operacionais contaminem rounds em andamento e preparar a operacao para resposta a incidente.

### Escopo do proximo passo

- implementar `EP06` Freeze Operacional por Round
- bloquear troca de `ROI`, `line`, `stream profile` e configuracao comercial com round `open`, `closing` ou `settling`
- registrar tentativas administrativas bloqueadas
- consolidar o stream como baseline congelado, com mudanca apenas por correcao de incidente
- preparar a camada seguinte de `EP11` para incidente e runbook quando houver degradacao operacional

### Entregavel esperado

Um round oficial protegido contra contaminacao operacional em runtime, com comportamento previsivel para operacao e suporte.

### Abordagem recomendada

Em vez de voltar a mexer no stream para explicar o jogo, a abordagem recomendada passa a ser:

1. preservar a esteira atual como baseline operacional
2. endurecer os bloqueios operacionais em torno do round oficial
3. abrir incidentes e evidencias quando a operacao fugir do esperado
4. tratar qualquer mudanca de stream como bugfix isolado, e nao como eixo da evolucao do produto

### Depois disso

Com o freeze operacional protegido, o passo seguinte passa a ser:

1. seguir com `EP11` Incidentes, Alertas e Runbooks
2. seguir com `EP12` Evidencias, Replay e Reprocessamento
3. retomar `EP07` e `EP08` para contrato externo e distribuicao assincrona do provider

## 18. Criticos de Produto

Pontos que nao devem ser adiados nas fases finais:

- `bet_close_at` antes de `ends_at`
- `void` com motivo estruturado
- freeze de ROI, line e stream profile durante round
- backend como fonte oficial do resultado
- evidencia minima por settlement
- trilha de auditoria administrativa
- idempotencia no contrato com operadora

## 19. Definicao de Pronto do Programa

O programa sera considerado concluido quando:

- houver `round engine` formal e persistido
- a operadora conseguir integrar por API e webhook
- os mercados `v1` liquidarem por resultado oficial auditavel
- existir `void`, replay, evidencias e reconciliacao
- operacao diaria puder ser feita via backoffice
- seguranca, RBAC e trilha administrativa estiverem ativos
- houver pacote minimo para auditoria, homologacao e certificacao

## 20. Referencias Operacionais

Referencias que continuam validas para orientar a execucao:

- UK Gambling Commission RTS
- GLI-19
- iTech Labs
- Supabase para camada operacional e administrativa

Essas referencias nao substituem implementacao, mas devem orientar:

- fairness
- resultado oficial
- auditabilidade
- segregacao
- monitoracao
- readiness regulatoria

## 21. Backlog Operacional por Epicos

Este backlog traduz o plano em blocos executaveis. A ideia e usar cada epico como unidade de planejamento e cada task como item concreto de implementacao.

Status sugeridos:

- `Pendente`
- `Em andamento`
- `Bloqueado`
- `Concluido`

Prioridades sugeridas:

- `P0` critico para a fundacao
- `P1` necessario para integracao real
- `P2` necessario para operacao e escala
- `P3` evolucao e refinamento

## 22. Epicos e Tasks

### EP01 - Consolidacao do Vision Worker

Objetivo:

- fechar definitivamente o worker Python como fluxo oficial de operacao

Prioridade:

- `P0`

Repositorio principal:

- `vision-worker/`
- `start.bat`
- `vision-worker/config.json`

Tasks:

- [ ] documentar o `vision-worker` como entrypoint oficial
- [ ] remover ou isolar fluxos antigos que gerem ambiguidade operacional
- [ ] revisar `start.bat` para refletir apenas o fluxo oficial
- [ ] padronizar local de configuracao do worker
- [ ] manter compatibilidade legada da raiz apenas como shim para o worker oficial
- [ ] congelar alteracoes de stream fora de correcao de incidente
- [ ] validar a esteira de streams no fluxo de startup completo
- [ ] validar sincronizacao local e remota de `stream_profiles`
- [ ] registrar o stream atual como baseline antes de retomar evolucao do provider

Criterio de aceite:

- o time sobe sempre o mesmo worker
- nao existe duvida entre app raiz e worker oficial
- o stream deixa de ser ponto de experimentacao enquanto o provider core evolui

Status atual:

- [x] documentar o `vision-worker` como entrypoint oficial
- [x] remover ou isolar fluxos antigos que gerem ambiguidade operacional
- [x] revisar `start.bat` para refletir apenas o fluxo oficial
- [x] padronizar local de configuracao do worker
- [x] manter compatibilidade legada da raiz apenas como shim para o worker oficial
- [ ] congelar alteracoes de stream fora de correcao de incidente
- [ ] validar a esteira de streams no fluxo de startup completo
- [ ] validar sincronizacao local e remota de `stream_profiles`
- [ ] registrar o stream atual como baseline antes de retomar evolucao do provider

Estado operacional de `EP01`:

- consolidado parcialmente
- o worker oficial ja esta identificado, mas ainda convive com legado na raiz
- o stream precisa voltar a ser tratado como baseline operacional, nao como frente de experimentacao
- a pendencia principal de `EP01` e fechar a ambiguidade estrutural sem abrir nova superficie de regressao no pipeline visual

### EP02 - Persistencia do Core de Rounds

Objetivo:

- criar a base persistida do jogo

Prioridade:

- `P0`

Repositorio principal:

- `backend/`
- `TrafficCounter.Api/`
- `infra/`

Tasks:

- [ ] modelar tabela `rounds`
- [ ] modelar tabela `crossing_events`
- [ ] modelar tabela `round_events`
- [ ] modelar tabela `markets`
- [ ] criar migracoes iniciais
- [ ] definir relacoes entre `rounds`, `markets` e `crossing_events`
- [ ] garantir persistencia de timestamps oficiais

Criterio de aceite:

- existe schema minimo para operar e auditar um round do inicio ao fim

Estado atual de `EP02`:

- [x] modelar tabela `rounds`
- [x] modelar tabela `crossing_events`
- [x] modelar tabela `round_events`
- [x] modelar tabela `markets`
- [x] criar migracoes iniciais
- [x] definir relacoes entre `rounds`, `markets` e `crossing_events`
- [x] garantir persistencia de timestamps oficiais

Estado operacional de `EP02`:

- a base persistida do round ja existe e responde leitura auditavel
- o backend ja reconstrui round por `round`, `count-events` e `timeline`
- a pendencia principal deixou de ser modelagem e passou a ser protecao operacional e evidencia exportavel

### EP03 - Round Engine

Objetivo:

- transformar o backend no motor oficial de lifecycle e resultado

Prioridade:

- `P0`

Repositorio principal:

- `backend/`
- `TrafficCounter.Api/`

Tasks:

- [x] extrair servico de `round engine`
- [x] implementar transicoes `open -> closing -> settling -> settled`
- [x] implementar transicao para `void`
- [x] persistir `created_at`, `bet_close_at`, `ends_at`, `settled_at`
- [x] padronizar uso de `round_id` entre servicos
- [x] suportar settlement automatico
- [x] suportar settlement manual auditado

Criterio de aceite:

- o round tem lifecycle automatico, persistido e auditavel

Estado operacional de `EP03`:

- o backend ja e a fonte oficial do lifecycle e do resultado do round
- SignalR e endpoints ja refletem o estado oficial para frontend e operacao
- o que falta agora e endurecer guardrails em volta desse lifecycle

### EP04 - Integracao Worker x Round Engine

Objetivo:

- garantir que eventos de contagem alimentem o motor oficial sem ambiguidade

Prioridade:

- `P0`

Repositorio principal:

- `vision-worker/`
- `backend_client.py`
- `backend/`

Tasks:

- [x] padronizar contrato de envio de `count-events`
- [x] anexar `round_id`, `camera_id` e `stream_profile_id` aos eventos
- [x] persistir `count_before` e `count_after`
- [x] garantir retry seguro sem dupla contagem
- [ ] tratar backend indisponivel com degradacao controlada
- [ ] registrar incidente quando integridade do envio for perdida

Criterio de aceite:

- o worker alimenta o backend de forma resiliente e sem duplicidade indevida

Estado operacional de `EP04`:

- o contrato worker x backend ja esta auditavel e idempotente
- a integracao ainda precisa de contingencia operacional e incidente automatizado quando houver perda de integridade

### EP05 - Regras de Jogo e Mercados

Objetivo:

- transformar contagem em produto comercial `v1`

Prioridade:

- `P1`

Repositorio principal:

- `backend/`
- `frontend/`
- `traffic-counter-front/`

Tasks:

- [x] separar `round normal` e `rodada turbo`
- [x] formalizar fechamento de aposta antes do fim do round
- [x] implementar mercados `Under`, `Range`, `Over`, `Exact`
- [x] definir `rodada turbo` por sorteio oficial do backend
- [x] reiniciar elegibilidade de `turbo` por troca de `stream profile`
- [x] armazenar mercados vencedores no settlement
- [x] definir copy comercial inicial dos mercados
- [ ] calibrar probabilidade e janela comercial da `turbo`
- [ ] parametrizar target e ranges por camera
- [ ] validar composicao de mercados por camera

Criterio de aceite:

- o produto consegue abrir round, encerrar round e liquidar mercados com clareza comercial

Estado operacional de `EP05`:

- `EP05` esta iniciado e funcionalmente entregue no corte `global v1`
- o backend ja cria rounds `normal` e `turbo` com mercados congelados por modo
- `roundMode` ja chega ao frontend e ao admin como contrato oficial
- a regra de carencia apos troca de `stream profile` ja protege o sorteio da `turbo`
- a pendencia principal deixou de ser implementacao de base e passou a ser calibracao comercial por camera e integracao com `EP06`

### EP06 - Freeze Operacional por Round

Objetivo:

- impedir que alteracoes operacionais contaminem rounds em andamento

Prioridade:

- `P1`

Repositorio principal:

- `vision-worker/`
- `backend/`

Tasks:

- [ ] bloquear troca de ROI durante round aberto
- [ ] bloquear troca de line durante round aberto
- [ ] bloquear troca de stream profile durante round aberto
- [ ] bloquear mudanca de target e mercados durante round aberto
- [ ] registrar tentativa administrativa bloqueada

Criterio de aceite:

- nenhuma configuracao critica muda enquanto o round estiver `open`, `closing` ou `settling`

### EP07 - Provider API

Objetivo:

- expor um contrato externo versionado para operadoras

Prioridade:

- `P1`

Repositorio principal:

- `TrafficCounter.Api/`
- `backend/`

Tasks:

- [ ] definir endpoints `sessions`, `rounds`, `events` e `reconciliation`
- [ ] padronizar payloads e erros
- [ ] adicionar versionamento de API
- [ ] implementar idempotencia por request
- [ ] documentar exemplos de request e response
- [ ] publicar contrato OpenAPI

Criterio de aceite:

- a operadora consegue homologar a integracao sem depender de interpretacao informal

### EP08 - Webhooks e Entrega Assincrona

Objetivo:

- garantir distribuicao confiavel de eventos do provider para a operadora

Prioridade:

- `P1`

Repositorio principal:

- `TrafficCounter.Api/`
- `backend/`

Tasks:

- [ ] modelar `webhook_deliveries`
- [ ] implementar assinatura HMAC
- [ ] implementar retries exponenciais
- [ ] implementar `dead-letter queue`
- [ ] criar reenvio manual
- [ ] registrar status, tentativas e resposta recebida

Criterio de aceite:

- nenhum webhook relevante fica sem rastreabilidade ou sem mecanismo de reenvio

### EP09 - Wallet e Contrato Financeiro

Objetivo:

- fechar o contrato financeiro entre provider e operador

Prioridade:

- `P1`

Repositorio principal:

- `TrafficCounter.Api/`
- `backend/`

Tasks:

- [ ] definir `balance`
- [x] definir `bet` v1 como `ledger` interno com `1 linha por compra`
- [ ] definir `settle`
- [ ] definir `rollback`
- [x] padronizar `transaction_id`, `game_session_id` e `round_id` na aposta v1
- [ ] definir erros financeiros
- [ ] suportar reconciliacao diaria

Status atual:

- [x] tabela `bets` persistida no backend
- [x] `POST /internal/bets` para aceite idempotente da aposta
- [x] `GET /bets/{betId}` para consulta operacional
- [x] congelamento de `odds`, `market_type`, `label`, `threshold/min/max/target_value`
- [x] liquidacao basica por resultado oficial do round (`settled_win` / `settled_loss`)
- [x] anulacao automatica das apostas quando o round vira `void`
- [ ] integrar `balance`, `debit` e `wallet` da operadora
- [ ] formalizar `settle` / `rollback` como contrato externo
- [ ] gerar reconciliacao diaria e codigos financeiros

Criterio de aceite:

- existe contrato financeiro claro, rastreavel e homologavel

### EP10 - Backoffice Operacional

Objetivo:

- permitir operacao, investigacao e suporte sem acesso direto ao banco

Prioridade:

- `P2`

Repositorio principal:

- `frontend/`
- `traffic-counter-front/`
- `backend/`

Tasks:

- [x] criar timeline do round
- [x] exibir eventos de contagem
- [x] exibir stream profile usado no round
- [x] exibir snapshots e evidencias
- [ ] suportar replay operacional
- [ ] permitir reenvio de webhook
- [x] permitir `void` manual controlado

Criterio de aceite:

- time operacional consegue investigar e agir sobre um round pelo painel

Estado operacional de `EP10`:

- o admin ja permite buscar round por `round_id`
- o painel ja navega entre round atual e rounds recentes por camera
- o detalhe do round ja mostra resumo oficial, mercados, timeline, crossings e snapshots persistidos
- o front de cliente deixou de exibir `Estado Oficial`, `Timeline Oficial` e `Crossing Events`
- o cliente agora usa um unico dropdown `HISTORICO` com rounds encerrados, resultado, modo e horario
- a visao tecnica de timeline e crossings continua restrita ao admin/backoffice
- `EP10` esta funcionalmente iniciado e cobre investigacao sem acesso direto ao banco
- as pendencias principais sao replay, export de evidencias e reenvio manual de webhook

### EP11 - Incidentes, Alertas e Runbooks

Objetivo:

- reduzir tempo de deteccao e resposta operacional

Prioridade:

- `P2`

Repositorio principal:

- `vision-worker/`
- `backend/`
- `frontend/`

Tasks:

- [ ] modelar `incidents`
- [ ] abrir incidente automatico por perda de stream
- [ ] abrir incidente por backend indisponivel
- [ ] abrir incidente por drift ou contagem suspeita
- [ ] definir alertas por camada
- [ ] escrever runbook de stream indisponivel
- [ ] escrever runbook de settlement atrasado
- [ ] escrever runbook de `void`

Criterio de aceite:

- incidentes operacionais sao detectados, registrados e trataveis com procedimento definido

### EP12 - Evidencias, Replay e Reprocessamento

Objetivo:

- tornar o produto defensavel em disputa e auditoria

Prioridade:

- `P2`

Repositorio principal:

- `backend/`
- `vision-worker/`
- `snapshots/`

Tasks:

- [ ] definir evidencia minima por round
- [ ] vincular snapshots a `crossing_events`
- [ ] montar export de evidencias por round
- [ ] permitir replay tecnico em ambiente controlado
- [ ] suportar reprocessamento com configuracao congelada
- [ ] registrar decisao final do reprocessamento

Criterio de aceite:

- qualquer round relevante pode ser revisado com base em eventos, snapshots e resultado oficial

### EP13 - Seguranca, RBAC e Auditoria Administrativa

Objetivo:

- proteger superficies sensiveis e rastrear acoes administrativas

Prioridade:

- `P2`

Repositorio principal:

- `TrafficCounter.Api/`
- `backend/`
- `frontend/`

Tasks:

- [ ] implementar launch token assinado
- [ ] implementar autenticacao server-to-server
- [ ] impedir aposta publica sem contexto autenticado de operadora ou sessao assinada
- [ ] falhar startup se `BackendApiKey` obrigatoria estiver ausente fora de ambiente local
- [ ] implementar RBAC administrativo
- [ ] auditar alteracao de ROI, line e stream profile
- [ ] auditar `void`, override e reprocessamento
- [ ] segregar secrets por ambiente
- [ ] validar origem e integridade do contexto recebido pelo embed

Criterio de aceite:

- toda superficie sensivel exige autenticacao e toda acao critica deixa trilha

### EP14 - LGPD, Retencao e Pacote Regulatorio

Objetivo:

- preparar o produto para auditoria e certificacao

Prioridade:

- `P2`

Repositorio principal:

- `backend/`
- `infra/`
- documentacao do projeto

Tasks:

- [ ] mapear fluxo de dados
- [ ] minimizar PII em eventos e logs
- [ ] definir retencao de snapshots e evidencias
- [ ] definir pacote de evidencia para auditoria
- [ ] implementar hash chain de resultado
- [ ] implementar hash chain ou trilha de integridade para `crossing_events` e `round_events`
- [ ] definir schema permitido para `metadataJson` e politica de minimizacao
- [ ] preparar material base para certificadora

Criterio de aceite:

- existe pacote regulatorio inicial coerente com a operacao do produto

### EP15 - Embed, Front Comercial e Rollout

Objetivo:

- preparar a entrada do produto em operadoras reais

Prioridade:

- `P3`

Repositorio principal:

- `frontend/`
- `traffic-counter-front/`
- `infra/`

Tasks:

- [ ] definir estrategia de embed
- [ ] aplicar `trusted origins`
- [ ] aplicar CSP e frame policy
- [ ] restringir `postMessage` a origins permitidas
- [ ] definir `frame-ancestors` por operador e ambiente
- [ ] fechar layout web e mobile do produto
- [ ] criar rollout por operador
- [ ] criar feature flags por camera e operador
- [ ] montar checklist de go-live

Criterio de aceite:

- o produto pode ser habilitado de forma controlada por operador e ambiente

## 23. Sequencia Recomendada de Ataque

Se formos executar agora, a ordem mais eficiente e:

1. fechar `EP01` sem novas alteracoes de stream alem de correcao de incidente
2. considerar `EP02` Persistencia do Core de Rounds como baseline funcional
3. considerar `EP03` Round Engine como baseline funcional
4. endurecer `EP04` Integracao Worker x Round Engine
5. manter o frontend consumindo o lifecycle oficial de round, e nao inferencias do stream
6. seguir com `EP06` Freeze Operacional por Round
7. seguir com `EP05` Regras de Jogo e Mercados
8. seguir com `EP07` Provider API
9. seguir com `EP08` Webhooks e Entrega Assincrona
10. seguir com `EP09` Wallet e Contrato Financeiro
11. evoluir `EP10` Backoffice Operacional com replay, export e acoes controladas
12. seguir com `EP11` Incidentes, Alertas e Runbooks
13. seguir com `EP12` Evidencias, Replay e Reprocessamento
14. seguir com `EP13` Seguranca, RBAC e Auditoria Administrativa
15. seguir com `EP14` LGPD, Retencao e Pacote Regulatorio
16. seguir com `EP15` Embed, Front Comercial e Rollout

## 24. Proxima Sprint Recomendada

Sprint tecnica inicial sugerida:

- fechar `EP06` Freeze Operacional por Round
- endurecer contingencia de `EP04` quando backend ficar indisponivel
- abrir a base de `EP11` para incidentes, alertas e runbooks
- evoluir `EP10` com export minimo de evidencias e acoes operacionais futuras
- preparar `EP07` e `EP08` sem reabrir mudanca estrutural no stream

Resultado esperado da primeira sprint:

- o round deixa de aceitar contaminacao operacional durante sua janela oficial
- worker e backend passam a ter comportamento mais previsivel em contingencia
- operacao ganha base para tratar incidente sem banco e sem depender do stream
- a plataforma fica pronta para abrir contrato externo e camada de evidencias com menos risco
