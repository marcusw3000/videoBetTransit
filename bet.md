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

- fixar a regra `RODADA TURBO` de 2 minutos
- manter `bet_close_at` antes de `ends_at`
- formalizar mercados `Under`, `Range`, `Over`, `Exact`
- parametrizar target, ranges e odds por camera
- congelar configuracao por round

### Entregaveis

- especificacao de round `v1`
- composicao inicial de mercados `v1`
- modelo de configuracao comercial por camera
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
- validar bloqueio de alteracao de perfil/ROI/line durante round
- revisar configuracao comercial por camera

### Definicao de pronto

- existe round comercial fechado
- os mercados podem ser liquidados com base no resultado oficial
- nenhuma configuracao critica muda em round aberto

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

- definir `balance`, `bet`, `settle`, `rollback`
- suportar `seamless wallet` e preparar `transfer wallet`
- gerar reconciliacao diaria
- garantir consistencia entre round, transacao e settlement

### Entregaveis

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

- fluxo completo de aposta e settlement em ambiente de homologacao
- teste de rollback
- comparacao entre reconciliacao e eventos do dia

### Definicao de pronto

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

Analisando a estrutura atual do codigo, o projeto parece estar entre a Fase 0 e a Fase 1:

- ja existem `rounds` e `round_markets` no backend
- ja existe lifecycle basico de round com `open`, `closing`, `settled` e `void`
- ja existem endpoints internos para contagem e anulacao
- o `start.bat` ja assume `vision-worker\app.py` como worker oficial
- ainda existe duplicidade relevante entre `app.py` na raiz e `vision-worker\app.py`
- ainda nao estao formalizados no backend os eventos soberanos esperados para `crossing_events` e `round_events`
- o endpoint `GET /rounds/{roundId}/count-events` ainda esta em stub

Conclusao pratica:

- a Fase 1 foi iniciada antes de a Fase 0 estar completamente fechada
- o maior risco imediato continua sendo `split-brain` entre entrypoints, configuracao e fluxo oficial do worker
- por isso, o proximo passo recomendado nao e abrir novas integracoes de operadora ainda

## 17. Proximo Passo Recomendado Agora

O proximo passo deve ser concluir de forma explicita a Fase 0, congelando um unico fluxo operacional oficial antes de expandir o provider core.

### Objetivo imediato

Eliminar ambiguidade entre worker raiz, worker oficial, configuracao e ponto de execucao.

### Escopo do proximo passo

- declarar `vision-worker\app.py` como unico entrypoint Python suportado
- remover ou aposentar o `app.py` da raiz como fluxo operacional concorrente
- garantir que `config.json`, profiles e sync operacional apontem para um unico caminho de execucao
- revisar `start.bat`, scripts auxiliares e documentacao para refletir somente esse fluxo
- validar que health, troca de stream, reaplicacao de ROI/line e envio de eventos continuam funcionando no worker oficial

### Entregavel esperado

Um baseline operacional sem duplicidade de entrypoint, pronto para a proxima etapa de persistencia formal de eventos do round.

### Depois disso

Com a Fase 0 realmente encerrada, o passo seguinte passa a ser:

1. modelar e persistir `crossing_events` com vinculacao a `round_id`
2. criar `round_events` para transicoes oficiais do lifecycle
3. substituir o endpoint stub de `count-events` por consulta real auditavel

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
- [ ] validar a esteira de streams no fluxo de startup completo
- [ ] validar sincronizacao local e remota de `stream_profiles`

Criterio de aceite:

- o time sobe sempre o mesmo worker
- nao existe duvida entre app raiz e worker oficial

Status atual:

- [x] documentar o `vision-worker` como entrypoint oficial
- [x] remover ou isolar fluxos antigos que gerem ambiguidade operacional
- [x] revisar `start.bat` para refletir apenas o fluxo oficial
- [x] padronizar local de configuracao do worker
- [x] manter compatibilidade legada da raiz apenas como shim para o worker oficial
- [ ] validar a esteira de streams no fluxo de startup completo
- [ ] validar sincronizacao local e remota de `stream_profiles`

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

### EP03 - Round Engine

Objetivo:

- transformar o backend no motor oficial de lifecycle e resultado

Prioridade:

- `P0`

Repositorio principal:

- `backend/`
- `TrafficCounter.Api/`

Tasks:

- [ ] extrair servico de `round engine`
- [ ] implementar transicoes `open -> closing -> settling -> settled`
- [ ] implementar transicao para `void`
- [ ] persistir `created_at`, `bet_close_at`, `ends_at`, `settled_at`
- [ ] padronizar uso de `round_id` entre servicos
- [ ] suportar settlement automatico
- [ ] suportar settlement manual auditado

Criterio de aceite:

- o round tem lifecycle automatico, persistido e auditavel

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

- [ ] padronizar contrato de envio de `count-events`
- [ ] anexar `round_id`, `camera_id` e `stream_profile_id` aos eventos
- [ ] persistir `count_before` e `count_after`
- [ ] garantir retry seguro sem dupla contagem
- [ ] tratar backend indisponivel com degradacao controlada
- [ ] registrar incidente quando integridade do envio for perdida

Criterio de aceite:

- o worker alimenta o backend de forma resiliente e sem duplicidade indevida

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

- [ ] formalizar `RODADA TURBO` de 2 minutos
- [ ] formalizar fechamento de aposta antes do fim do round
- [ ] implementar mercados `Under`, `Range`, `Over`, `Exact`
- [ ] parametrizar target e ranges por camera
- [ ] armazenar mercados vencedores no settlement
- [ ] definir copy comercial final dos mercados
- [ ] validar composicao de mercados por camera

Criterio de aceite:

- o produto consegue abrir round, encerrar round e liquidar mercados com clareza comercial

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
- [ ] definir `bet`
- [ ] definir `settle`
- [ ] definir `rollback`
- [ ] padronizar `transaction_id`, `game_session_id` e `round_id`
- [ ] definir erros financeiros
- [ ] suportar reconciliacao diaria

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

- [ ] criar timeline do round
- [ ] exibir eventos de contagem
- [ ] exibir stream profile usado no round
- [ ] exibir snapshots e evidencias
- [ ] suportar replay operacional
- [ ] permitir reenvio de webhook
- [ ] permitir `void` manual controlado

Criterio de aceite:

- time operacional consegue investigar e agir sobre um round pelo painel

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
- [ ] implementar RBAC administrativo
- [ ] auditar alteracao de ROI, line e stream profile
- [ ] auditar `void`, override e reprocessamento
- [ ] segregar secrets por ambiente

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
- [ ] fechar layout web e mobile do produto
- [ ] criar rollout por operador
- [ ] criar feature flags por camera e operador
- [ ] montar checklist de go-live

Criterio de aceite:

- o produto pode ser habilitado de forma controlada por operador e ambiente

## 23. Sequencia Recomendada de Ataque

Se formos executar agora, a ordem mais eficiente e:

1. `EP01` Consolidacao do Vision Worker
2. `EP02` Persistencia do Core de Rounds
3. `EP03` Round Engine
4. `EP04` Integracao Worker x Round Engine
5. `EP05` Regras de Jogo e Mercados
6. `EP06` Freeze Operacional por Round
7. `EP07` Provider API
8. `EP08` Webhooks e Entrega Assincrona
9. `EP09` Wallet e Contrato Financeiro
10. `EP10` Backoffice Operacional
11. `EP11` Incidentes, Alertas e Runbooks
12. `EP12` Evidencias, Replay e Reprocessamento
13. `EP13` Seguranca, RBAC e Auditoria Administrativa
14. `EP14` LGPD, Retencao e Pacote Regulatorio
15. `EP15` Embed, Front Comercial e Rollout

## 24. Proxima Sprint Recomendada

Sprint tecnica inicial sugerida:

- `EP01` fechar entrypoint, startup e configuracao operacional
- `EP02` modelar schema inicial de rounds e eventos
- `EP03` implementar lifecycle basico do round
- `EP04` padronizar envio de `count-events` com `round_id`

Resultado esperado da primeira sprint:

- round persistido
- eventos persistidos
- worker apontando para um backend que ja entende lifecycle
- base pronta para comecar `Provider API`
