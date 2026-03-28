# TODO2.md - Integracao do game provider em bet regulamentada

Roadmap tecnico e operacional para integrar este produto dentro de uma operadora de apostas regulamentada no Brasil.

Premissas usadas neste documento:
- a operadora parceira ja possui autorizacao valida para operar apostas de quota fixa no Brasil
- este projeto sera tratado como componente de jogo online / software integrado ao sistema de apostas da operadora
- a integracao precisa ser compativel com exigencias de certificacao, seguranca, jogo responsavel, auditoria e operacao continua
- o plano abaixo e tecnico-operacional e nao substitui validacao juridica, regulatoria e de certificadora habilitada

Observacao regulatoria:
- desde `1 de janeiro de 2025`, apenas empresas autorizadas pela SPA podem operar nacionalmente e os sites autorizados usam `.bet.br`
- a SPA trata plataforma, jogos online e modulos/subsistemas integrados como parte do sistema de apostas
- cada jogo online precisa de certificacao de conformidade
- certificados anteriores podem ser aproveitados por certificadora habilitada, mas a integracao ainda precisa ser testada e refletida no relatorio final

---

## 1. Objetivo de integracao

Objetivo:
- transformar este produto em oferta de `game provider` pronta para embed em site de bet regulamentado
- permitir operacao segura, auditavel e certificavel
- separar claramente o que pertence ao operador e o que pertence ao provider

Resultado esperado:
- operadora consegue publicar o jogo dentro do seu ecossistema, com autenticacao, wallet, sessao, auditoria, monitoramento e suporte regulatorio

---

## 2. Modelo alvo de arquitetura

### 2.1 Componentes

- `Frontend do jogo`: client renderizado ao usuario final, idealmente isolado do front principal da bet
- `Game Backend`: logica de round, estado, regras, configuracao e auditoria do jogo
- `Game Stream Engine`: engine Python / stream anotado / calibracao operacional
- `Provider Integration API`: camada para falar com operador, wallet, sessao, limites e callbacks
- `Operator Platform`: PAM, wallet, KYC, limites, responsavel gaming, antifraude, monitoramento e backoffice

### 2.2 Fronteiras

O provider deve ser dono de:
- motor do jogo
- regras e configuracao operacional
- rendering do jogo
- eventos tecnicos do jogo
- logs tecnicos e telemetria de execucao

O operador deve ser dono de:
- cadastro e identidade do jogador
- wallet e ledger financeiro
- limites de deposito/aposta/perda
- politicas de jogo responsavel e impedidos
- antifraude, AML e atendimento ao jogador

### 2.3 Modelo de entrega recomendado

Recomendacao principal:
- `frontend do jogo hospedado pelo provider`
- carregado pelo site da bet em rota dedicada ou `iframe` controlado
- `backend do jogo hospedado pelo provider`
- operador integra por APIs seguras para autenticacao, sessao, wallet e eventos de jogo

Motivo:
- reduz acoplamento do front da bet com o ciclo do jogo
- facilita certificacao e versionamento por provider
- deixa responsavel quem opera cada parte

Alternativa:
- `frontend empacotado para embed via SDK`

Risco:
- aumenta acoplamento com stacks diferentes de operadoras
- dificulta controle de versao, hotfix e certificacao por release

---

## 3. Fases do programa

### Fase A - Descoberta e enquadramento regulatorio

Objetivo:
- fechar escopo de integracao, responsabilidade e trilha regulatoria antes de codar

Checklist:
- [ ] Confirmar se o produto sera submetido como `jogo online` especifico, `modulo` ou combinacao dos dois.
- [ ] Mapear com juridico/compliance do operador a trilha de certificacao aplicavel.
- [ ] Confirmar com certificadora habilitada a estrategia de certificacao do jogo, da integracao e do ambiente.
- [ ] Definir se o provider hospedara o jogo em dominio proprio segregado ou sob subdominio controlado.
- [ ] Definir se a sessao do jogador entrara por `launch URL`, `JWT`, token de sessao curto ou combinacao.
- [ ] Definir matriz RACI entre operador e provider.

Entregaveis:
- documento de arquitetura alvo
- matriz de responsabilidades
- checklist de certificacao e compliance
- plano de ambientes

Gate de saida:
- nenhum desenvolvimento de producao antes dessa fase estar formalmente aprovada

### Fase B - Modelo comercial e contratual de integracao

Objetivo:
- fechar o contrato tecnico-operacional entre provider e operador

Checklist:
- [ ] Definir SLA, SLO e janela de suporte.
- [ ] Definir responsabilidade por incidente, chargeback regulatorio, auditoria e indisponibilidade.
- [ ] Definir formato de billing/revenue share.
- [ ] Definir processo de mudanca de versao e congelamento para certificacao.
- [ ] Definir evidencias minimas que o provider entrega ao operador por release.
- [ ] Definir plano de contingencia e rollback.

Entregaveis:
- runbook de operacao conjunta
- contrato tecnico de integracao
- politica de release e rollback

### Fase C - Infraestrutura e ambientes

Objetivo:
- preparar ambientes segregados, auditaveis e reproduziveis

Checklist:
- [ ] Criar ambientes separados: `dev`, `qa`, `cert`, `staging`, `prod`.
- [ ] Separar configuracoes por ambiente para frontend, backend e engine.
- [ ] Colocar segredos em cofre seguro.
- [ ] Definir rede, firewall, allowlist e TLS ponta a ponta.
- [ ] Definir topologia de deploy final.
- [ ] Padronizar CI/CD com aprovacao por ambiente.
- [ ] Definir estrategia de alta disponibilidade para backend e stream.
- [ ] Definir backup, retention e disaster recovery.
- [ ] Definir armazenamento de snapshots e evidencias fora do disco local.

Entregaveis:
- diagrama de rede
- matriz de ambientes
- pipeline de deploy
- politica de backup/restore

Detalhes recomendados:
- API do provider atras de `WAF` e `reverse proxy`
- banco com backup automatico e restore testado
- CDN apenas para assets estaticos do client, nunca para chamadas autenticadas sensiveis
- logs e eventos com retencao definida

### Fase D - Seguranca, identidade e sessao

Objetivo:
- garantir autenticacao forte, segregacao de dados e controles de acesso

Checklist:
- [ ] Trocar `X-API-Key` simples por credencial de sistema apropriada entre provider e operador.
- [ ] Adotar autenticacao servidor-servidor com assinatura ou mTLS para rotas criticas.
- [ ] Definir token de launch curto, assinado e com `nonce`.
- [ ] Garantir expiracao curta e one-time use para launch do jogo.
- [ ] Implementar validacao de origem e anti-replay.
- [ ] Segregar segredos por operador.
- [ ] Implementar RBAC para operacao interna e painel administrativo.
- [ ] Garantir rotacao de segredos.
- [ ] Formalizar trilha de auditoria de acoes administrativas e operacionais.

Entregaveis:
- especificacao de autenticacao
- matriz de autorizacao
- trilha de auditoria

Controles minimos:
- TLS 1.2+
- cifragem em repouso para dados sensiveis
- principle of least privilege
- segregacao entre conta tecnica do provider e identidades humanas

### Fase E - Dados pessoais, LGPD e compliance

Objetivo:
- minimizar dados pessoais e tratar apenas o necessario para integracao

Checklist:
- [ ] Definir quais dados do jogador entram no provider.
- [ ] Minimizar PII; preferir `player_id` pseudonimizado ao inves de dados cadastrais completos.
- [ ] Formalizar papeis `controlador` e `operador` entre bet e provider.
- [ ] Mapear base legal e fluxo de tratamento.
- [ ] Definir retention e descarte de logs/eventos.
- [ ] Garantir atendimento a direitos do titular nos dados hospedados pelo provider.
- [ ] Formalizar processo de incidente de dados.

Entregaveis:
- data flow de PII
- inventario de dados
- politica de retencao
- anexos contratuais de dados

Recomendacao:
- o provider deve receber o minimo necessario para operar o jogo
- wallet, KYC e cadastro devem permanecer preferencialmente no operador

### Fase F - Integracao com operador

Objetivo:
- conectar o jogo ao ecossistema da bet sem quebrar regras do operador

Checklist:
- [ ] Definir API de `launch session`.
- [ ] Definir API de `balance`, `bet`, `settle`, `rollback` e reconciliacao.
- [ ] Garantir idempotencia em todas as chamadas financeiras.
- [ ] Definir timeout, retry, circuit breaker e deduplicacao.
- [ ] Definir correlacao por `transaction_id`, `round_id`, `game_session_id` e `operator_player_id`.
- [ ] Definir tratamento de erro para indisponibilidade parcial.
- [ ] Definir protocolo de reconciliacao diaria.
- [ ] Integrar com limites, autoexclusao, jogo responsavel e impedidos do operador.

Entregaveis:
- contrato OpenAPI / webhook spec
- tabela de codigos de erro
- matriz de idempotencia
- runbook de reconciliacao

Ponto critico:
- nenhuma movimentacao economica deve depender do frontend
- frontend apenas orquestra a experiencia; ledger e autorizacao devem ser server-side

### Fase G - Frontend e embedding dentro da bet

Objetivo:
- encaixar o jogo no site da operadora com UX segura e controlada

Checklist:
- [ ] Definir `launch flow` do lobby da bet para o jogo.
- [ ] Decidir entre rota dedicada e `iframe` sandboxed.
- [ ] Implementar design token / skinning por operador.
- [ ] Implementar modo responsivo para desktop, tablet e mobile.
- [ ] Garantir tratamento de perda de sessao e expiração.
- [ ] Garantir mensagens para indisponibilidade, reconexao e manutencao.
- [ ] Implementar `postMessage` seguro se usar `iframe`.
- [ ] Definir politicas de CSP, frame-ancestors e trusted origins.
- [ ] Exibir informacoes de round, status e jogo responsavel conforme guideline do operador.

Entregaveis:
- launch contract
- UI kit de embedding
- matriz de compatibilidade webview/browser

Recomendacao de front:
- evitar acoplamento com o SPA principal da bet
- isolar analytics, erros e estilos
- manter versao do client controlada pelo provider

### Fase H - Certificacao, QA e evidencias

Objetivo:
- preparar o produto para certificacao formal e homologacao com operador

Checklist:
- [ ] Montar pacote de evidencias tecnicas da release.
- [ ] Congelar versao candidata para certificacao.
- [ ] Executar testes de integracao com operador.
- [ ] Executar testes de carga e resiliencia.
- [ ] Executar teste de falha de wallet, timeout, rollback e reconciliacao.
- [ ] Executar pentest e remediacao.
- [ ] Validar logs, trilhas e relatórios de auditoria.
- [ ] Validar fluxo de autoexclusao e impedidos no onboarding e no uso recorrente.

Entregaveis:
- pacote de certificacao
- checklist de homologacao
- relatorio de seguranca
- relatorio de performance

### Fase I - Observabilidade, fraude e operacao 24x7

Objetivo:
- operar o jogo como produto critico de receita

Checklist:
- [ ] Centralizar logs, metricas e traces.
- [ ] Criar dashboards por operador, por jogo e por ambiente.
- [ ] Monitorar latencia de launch, erro de wallet, erro de stream e taxa de abandono.
- [ ] Criar alertas para indisponibilidade, fila, backlog e divergencia de reconciliacao.
- [ ] Definir playbooks de incidente.
- [ ] Definir rota de escalation entre N1/N2/N3 e operador.
- [ ] Detectar comportamento anomalo e abuso de integracao.

Entregaveis:
- dashboards operacionais
- alertas acionaveis
- runbooks de incidente

### Fase J - Rollout controlado

Objetivo:
- entrar em producao com risco controlado

Checklist:
- [ ] Publicar primeiro em ambiente restrito ou marca piloto.
- [ ] Habilitar rollout por operador / marca / dominio.
- [ ] Habilitar feature flags para launch do jogo.
- [ ] Medir erro tecnico, taxa de launch, reconexao e receita.
- [ ] Definir criterio de go/no-go para escala.
- [ ] Validar suporte operacional nos primeiros dias de producao.

Entregaveis:
- plano de rollout
- criterio de go-live
- relatorio de hiper-care

---

## 4. Backlog tecnico por trilha

### T1 - Core de plataforma provider
- [ ] Separar `game API`, `operator API` e `admin API`.
- [ ] Introduzir versionamento de contratos.
- [ ] Implementar idempotencia e deduplicacao nativa para eventos criticos.
- [ ] Separar configuracao por operador e por camera/mesa/jogo.
- [ ] Formalizar multi-tenant com isolamento logico por operador.

### T2 - Wallet e transacoes
- [ ] Modelar `reserve`, `bet`, `settle`, `cancel`, `refund`, `rollback`.
- [ ] Garantir ledger interno de reconciliacao, mesmo com wallet no operador.
- [ ] Persistir `transaction_id` do operador e `provider_tx_id`.
- [ ] Criar relatorio diario de reconciliacao.
- [ ] Criar rotina de replay seguro de callbacks falhos.

### T3 - Seguranca
- [ ] Implementar autenticacao server-to-server forte.
- [ ] Assinar requests e callbacks.
- [ ] Implementar pinning de origem e allowlist por operador.
- [ ] Integrar varredura de vulnerabilidade no CI/CD.
- [ ] Criar trilha imutavel para eventos administrativos.

### T4 - Front e experiencia de integracao
- [ ] Criar launch URL assinada.
- [ ] Criar SDK leve de embed para operadores.
- [ ] Criar tela de manutencao / indisponibilidade padrao.
- [ ] Criar theming por operador.
- [ ] Criar contrato de eventos do front para analytics do operador.

### T5 - Dados e compliance
- [ ] Minimizar PII enviada ao provider.
- [ ] Formalizar retention de logs, exports e snapshots.
- [ ] Implementar fluxo de expurgo.
- [ ] Criar evidencias de auditoria para certificacao.
- [ ] Integrar verificacoes obrigatorias de impedidos e jogo responsavel conforme contrato com operador.

### T6 - Operacao
- [ ] Criar dashboards e alertas por operador.
- [ ] Criar health checks de dependencias externas.
- [ ] Criar indicadores de launch success, bet success, settle success e rollback success.
- [ ] Definir RTO/RPO.
- [ ] Testar DR e restore.

---

## 5. Ordem recomendada

1. `Fase A` e `Fase B`
2. `Fase C`, `Fase D` e `Fase E`
3. `Fase F` e `Fase G`
4. `Fase H`
5. `Fase I`
6. `Fase J`

Regra pratica:
- nao vale acelerar frontend de embed antes de fechar contrato de sessao, wallet e certificacao
- nao vale entrar em homologacao sem trilha de auditoria e reconciliacao

---

## 6. Principais decisoes que precisam ser tomadas cedo

- [ ] O jogo sera `provider-hosted` ou parcialmente embutido no front da bet?
- [ ] O provider vai controlar apenas o jogo ou tambem round/settlement economico?
- [ ] O operador usara wallet central propria ou habra wallet intermediaria do provider?
- [ ] O stream/gameplay precisa ser certificado como jogo especifico ou como composicao com modulos adicionais?
- [ ] O fluxo de launch sera por `JWT`, `signed launch URL` ou `server-side session handoff`?
- [ ] Qual a topologia de producao: cloud do provider, cloud do operador ou modelo hibrido?

---

## 7. Riscos principais

- certificar o jogo, mas deixar a integracao operator-provider sem evidencias suficientes
- depender demais de `iframe` sem contrato robusto de sessao e seguranca
- misturar dados de operador e provider sem governanca clara de LGPD
- deixar wallet e reconciliacao subespecificados
- operar sem playbook de incidente e sem observabilidade por operador
- construir front bonito antes de fechar launch, token, rollback e fluxo financeiro

---

## 8. Definicao de pronto para entrar em bet regulamentada

- o jogo esta certificado na trilha aplicavel
- a integracao com a operadora foi homologada
- a autenticacao entre operador e provider esta endurecida
- ha trilha de auditoria, reconciliacao e rollback
- o fluxo de impedidos, jogo responsavel e politicas do operador esta integrado
- existe observabilidade por operador e runbook de incidente
- a topologia de producao esta documentada, aprovada e testada
- o rollout pode ser feito de forma controlada e reversivel

---

## Fontes oficiais consultadas

- SPA/MF - Apostas de Quota Fixa: https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/apostas-de-quota-fixa
- SPA/MF - Legislacao de Apostas de Quota Fixa: https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/legislacao/apostas-de-quota-fixa
- SPA/MF - Todos os jogos on-line devem ser certificados?: https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/apostas-de-quota-fixa/tire-suas-duvidas/jogos-online/todos-os-jogos-on-line-devem
- SPA/MF - Requisitos de seguranca dos sistemas: https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/apostas-de-quota-fixa/tire-suas-duvidas/seguranca/quais-requisitos-de-seguranca-dos
- SPA/MF - Software de apostas: https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/apostas-de-quota-fixa/questoes-tecnicas/o-software-de-apostas
- SPA/MF - Modulos do sistema de apostas: https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/apostas-de-quota-fixa/questoes-tecnicas/qual-a-definicao-de-modulos
- SPA/MF - Aproveitamento de certificados em processos de integracao: https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/apostas-de-quota-fixa/questoes-tecnicas/82-as-certificadoras-autorizadas-pela
- SPA/MF - Modulo de Impedidos: https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/modulo-de-impedidos
- SPA/MF - FAQ do Modulo de Impedidos: https://www.gov.br/fazenda/pt-br/composicao/orgaos/secretaria-de-premios-e-apostas/modulo-de-impedidos/perguntas-frequentes
- Governo Federal - LGPD: https://www.gov.br/esporte/pt-br/acesso-a-informacao/privacidade-e-protecao-de-dados
