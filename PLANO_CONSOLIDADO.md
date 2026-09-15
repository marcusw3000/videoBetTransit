# Plano consolidado — videoBetTransit

Revisão: 14/09/2026, após implementação e revisão corretiva de P01–P06. Base: código local, incluindo as alterações ainda não publicadas.

**P01–P04 concluídos e validados localmente. P05 está parcial pela política de retenção ainda não definida. P06 está em preparação local; faltam os aceites em instalação limpa e ambiente operacional.** Regras vigentes: [ROUND_RULES.md](ROUND_RULES.md).

Este arquivo reúne [bet.md](bet.md), [TODO.md](TODO.md), [TODO2.md](TODO2.md), [TODO3.md](TODO3.md), [SPRINTS.md](SPRINTS.md) e [ROUND_FORMULATION.md](ROUND_FORMULATION.md). Substitui suas listas de execução para planejamento futuro; os originais servem como histórico. Instruções de instalação continuam no [README.md](README.md).

## 1. Critério da consolidação

- **Implementado:** existe no fluxo atual. Isso não significa homologação externa ou operação em produção.
- **Parcial:** existe uma base aproveitável, mas faltam entregas ou validações específicas.
- **Pendente:** trabalho útil para a aplicação atual, com escopo e aceite definidos abaixo.
- **Condicionado:** depende de uma decisão de produto, integração ou infraestrutura.
- **Adiado:** fora da execução por decisão anterior do usuário.
- **Superado:** duplicação, orientação histórica ou regra incompatível com o código atual.

Checklists antigos não comprovam conclusão. Quando documentos divergem, o código determina o comportamento existente; propostas futuras ficam identificadas como propostas.

O produto atual é uma demonstração com apostas simuladas. Não há carteira, depósito, saque ou liquidação financeira com operadora. A existência de `operatorRef`, tabelas de apostas ou configurações Supabase não comprova uma plataforma multioperadora homologada.

## 2. O que já foi feito

| Entrega implementada | Evidência principal | Limite da conclusão |
| --- | --- | --- |
| Entradas oficiais em `frontend/`, `backend/TrafficCounter.Api/` e `vision-worker/`; compatibilidade da raiz por shims | [README](README.md), [app.py](app.py), [start-dev.bat](start-dev.bat) | O frontend legado não deve orientar novas tarefas. Startup completo com a câmera real ainda precisa de aceite operacional. |
| Extração de captura, publicação, configuração, agenda, geometria e desenho do worker | [Worker](vision-worker/app.py), [desenho](vision-worker/frame_overlay.py), [geometria](vision-worker/count_geometry.py) | A modularização preserva a contagem; não demonstra ganho de precisão. |
| Perfis de stream, agenda, rotação opcional e handshake de ativação | [Agenda](vision-worker/stream_schedule.py), [controle interno](backend/TrafficCounter.Api/Controllers/InternalController.cs), [estado da câmera](backend/TrafficCounter.Api/Domain/Entities/CameraRoundState.cs) | Sincronização remota e funcionamento contínuo não foram homologados nesta revisão. |
| Editor local de ROI e linha; servidor de vídeo com Waitress | [Editor](vision-worker/calibration_editor.py), [worker](vision-worker/app.py) | Editor disponível não equivale a calibração validada com dados reais. |
| Persistência de rodadas, mercados, crossings, eventos e apostas, com migrações | [DbContext](backend/TrafficCounter.Api/Data/AppDbContext.cs), [migrações](backend/TrafficCounter.Api/Migrations) | Migração e concorrência foram verificadas em SQLite; PostgreSQL permanece sem validação equivalente. |
| Motor oficial por câmera com `open`, `closing`, `settling`, `settled` e `void` | [RoundService](backend/TrafficCounter.Api/Services/RoundService.cs) | A criação depende das condições de ativação e da janela operacional. |
| Contagem oficial no backend; eventos vinculados à rodada, deduplicados e validados pela hora de ocorrência | [RoundService](backend/TrafficCounter.Api/Services/RoundService.cs), [CrossingEventService](backend/TrafficCounter.Api/Services/CrossingEventService.cs) | Evento tardio de rodada finalizada é rejeitado; não é transferido para a seguinte. |
| Fila persistente do worker, repetição com o mesmo identificador, retenção de rejeições e decisões administrativas | [Outbox](vision-worker/event_outbox.py), [cliente](vision-worker/backend_client.py), [consulta de rejeições](scripts/review-outbox.py), [admin](backend/TrafficCounter.Api/Controllers/AdminController.cs) | A decisão fica registrada e auditada; não existe reenvio forçado. Essa fila não entrega webhooks a operadoras. |
| Encerramento de rodada, mercados e apostas na mesma gravação transacional; proteção contra concorrência | [DbContext](backend/TrafficCounter.Api/Data/AppDbContext.cs), [BetService](backend/TrafficCounter.Api/Services/BetService.cs) | Não representa uma transação com uma carteira externa. |
| Mercados `Under`, `Over`, `Range` e `Exact`, com parâmetros e odds registrados; aposta calculada pelo backend | [RoundService](backend/TrafficCounter.Api/Services/RoundService.cs), [BetService](backend/TrafficCounter.Api/Services/BetService.cs) | O fluxo atual cria rodadas Normal. A matemática comercial não está homologada. |
| Aceite idempotente, validação de moeda e valor e consulta de apostas por identidade autenticada | [BetService](backend/TrafficCounter.Api/Services/BetService.cs), [BetsController](backend/TrafficCounter.Api/Controllers/BetsController.cs) | BRL de 0,01 a 10.000,00, até duas casas decimais; sem saldo, crédito ou limite agregado de exposição. |
| Autenticação local, perfis jogador/admin, cookie HttpOnly, proteção CSRF e separação da chave do worker | [AuthController](backend/TrafficCounter.Api/Controllers/AuthController.cs), [segurança](backend/TrafficCounter.Api/Security), [cliente web](frontend/src/services/apiClient.js) | Auditoria das ações críticas entregue em P03; launch token de operadora e RBAC granular continuam condicionados. |
| Recusa de chave interna vazia/padrão e proteção do controle de pipeline | [RequireApiKeyAttribute](backend/TrafficCounter.Api/Security/RequireApiKeyAttribute.cs), [worker](vision-worker/app.py) | Recusar requisições sem chave válida não equivale a validar toda configuração no startup de produção. |
| Histórico persistido de apostas, filtros, paginação e recuperação de tentativa com resposta incerta | [Histórico](frontend/src/components/BetsHistory.jsx), [painel](frontend/src/components/BettingPanel.jsx) | O saldo fictício foi removido; o fluxo é explicitamente simulado. |
| Backoffice com consulta de rodada, mercados, timeline, crossings, exportação de evidências e anulação controlada | [AdminDashboard](frontend/src/components/AdminDashboard.jsx), [AdminController](backend/TrafficCounter.Api/Controllers/AdminController.cs), [evidências](backend/TrafficCounter.Api/Services/RoundEvidenceService.cs) | Disponibilidade local é classificada; prazo, limite e execução da retenção permanecem em P05. |
| Carregamento separado do admin e HLS, testes, lint, build, verificação de encoding e workflow de CI | [App](frontend/src/App.jsx), [VideoPlayer](frontend/src/components/VideoPlayer.jsx), [validação](validate.bat), [CI](.github/workflows/validate.yml) | O chunk HLS continua grande, mas é carregado sob demanda. Workflow criado não significa execução remota comprovada. |
| Configurações de exemplo, provisionamento local de contas e retirada de artefatos operacionais do versionamento | [Configurador](scripts/configure-local.ps1), [.gitignore](.gitignore), [README](README.md) | Contas e segredos do ambiente precisam ser provisionados pelo procedimento local. |

### Entregas de P01–P06

| Item | Status | Entrega e evidência |
| --- | --- | --- |
| P01 | Concluído localmente | [Especificação normal-v1](ROUND_RULES.md), rótulos dos mercados alinhados às comparações do backend, explicação da rodada na interface e identificação dos seis documentos anteriores como históricos. |
| P02 | Concluído localmente | Registro versionado da configuração; snapshots operacionais e de regras em cada nova rodada; bloqueio de alteração de mercados e snapshots; eventos vinculados à versão usada; bloqueios nos controles locais, remotos e de pipeline. [RoundService](backend/TrafficCounter.Api/Services/RoundService.cs), [DbContext](backend/TrafficCounter.Api/Data/AppDbContext.cs), [worker](vision-worker/app.py), [testes de integridade](backend/TrafficCounter.Api.Tests/Api/RoundIntegrityTests.cs). |
| P03 | Concluído localmente | Motivo estruturado de anulação, justificativa obrigatória, auditoria de decisões e tentativas recusadas, consulta restrita ao admin e proteção contra alteração da auditoria pela aplicação. [AdminController](backend/TrafficCounter.Api/Controllers/AdminController.cs), [middleware de auditoria](backend/TrafficCounter.Api/Security/AdministrativeAuditMiddleware.cs), [painel](frontend/src/components/AdminDashboard.jsx). |
| P04 | Concluído localmente | Recuperação idempotente da outbox, retenção de rejeições, diagnóstico somente leitura e decisões administrativas append-only auditadas. |
| P05 | Parcial | JSON/CSV administrativo com campos permitidos, referências sanitizadas e disponibilidade explícita. Política e execução de retenção ainda pendentes. |
| P06 | Parcial | Diagnóstico local, configuração inicial completa, backup SQLite consistente com WAL, manifesto e restauração confinada. Instalação limpa e ambiente publicado ainda sem aceite. |

### Revisão corretiva de P01–P06

| Achado | Correção aplicada | Evidência/limite |
| --- | --- | --- |
| Restauração aceitava caminhos fora do destino | Canonicalização, confinamento ao backup/destino e recusa de links/junctions | Teste com manifesto `../escape.txt` e teste de restauração válida |
| Backup podia perder conteúdo do WAL | Cópia pela API `sqlite3_backup` e `quick_check` na origem e no destino | Teste mantém transação confirmada apenas no WAL |
| Backup ignorava caminhos efetivos | Resolução da conexão local, `EVENT_OUTBOX_PATH`, `DataProtection:KeyPath` e `snapshot_dir`; caminhos externos ao projeto são recusados | Exercício com configuração operacional real continua em P06 |
| Instalação limpa herdava conexão com placeholder e não configurava Data Protection | `configure-local.ps1` registra SQLite local e `.auth-keys`; startup e diagnóstico validam banco, chave e admin | Provisionamento de senha continua interativo e não foi executado nesta revisão |
| Direções horizontais eram recusadas no snapshot | Contrato aceita `left` e `right` | Testes .NET para ambas as direções |
| Auditoria dependia da capitalização da URL | Comparações de rota passaram a `OrdinalIgnoreCase` | Teste de tentativa em `/ADMIN/...` |
| Evidência podia expor ator, motivo livre ou URL de imagem | Categorias de origem, retirada de motivo livre, whitelist dos snapshots e referência da imagem pelo crossing | Testes procuram identidade, senha, token e texto livre no JSON/CSV |
| P05 declarava retenção e disponibilidade concluídas | Disponibilidade local distingue `available`, `missing`, `external_unverified` e `not_recorded`; P05 voltou a parcial | Prazo, limite e execução auditada da retenção continuam pendentes |

A migração [FreezeRoundConfigurationAndAudit](backend/TrafficCounter.Api/Migrations/20260914083515_FreezeRoundConfigurationAndAudit.cs) mantém snapshots e códigos históricos ausentes como nulos. Por padrão, novas rodadas aguardam configuração registrada e ativação da câmera. O painel mostra explicitamente a ausência de configuração nos registros antigos. Ator `worker` identifica a credencial interna; não identifica individualmente quem utiliza a interface local Python.

### Evidência de validação disponível

A execução final de `validate.bat`, registrada em `artifacts/validation-p01-p03.log`, aprovou **104 testes Python, 111 testes .NET e 3 testes JavaScript**, além de lint, encoding e build. Os **3 testes Playwright** passaram, incluindo motivo estruturado de anulação, acesso ao snapshot e auditoria, com inspeção visual de desktop e mobile. Total: **221 testes**. Os testes de navegador usam API controlada; a API real e o banco SQLite são exercitados pelos testes .NET.

A revisão corretiva de P01–P06 aprovou **108 testes Python, 117 testes .NET e 3 testes JavaScript**, além de sintaxe PowerShell, lint, encoding e build. O ensaio permanece local: não inclui instalação separada, câmera real, PostgreSQL ou ambiente publicado.

Os novos cenários verificam bloqueios em aberto/fechamento/apuração, preparação controlada durante apuração, rejeição de versão incompatível, preservação do evento enfileirado após mudança de perfil, ausência histórica explícita, controle de acesso à auditoria e rollback conjunto de rodada, aposta e auditoria quando uma falha é injetada no banco.

A nova migração foi aplicada duas vezes em `artifacts/p01-p03-upgrade.db`, cópia do banco de referência, preservando **6.170 rodadas, 6 apostas e 5.545 crossings**. As 6.170 rodadas antigas permaneceram sem snapshot, sem reconstrução artificial. O banco operacional não foi migrado por esta validação. Backend e worker devem ser atualizados juntos; consulte o [procedimento no README](README.md).

PostgreSQL, sincronização Supabase, transmissão real e integrações com operadoras continuam sem aceite equivalente. A auditoria é protegida pela aplicação, não certificada contra alteração direta por um administrador do banco.

## 3. O que está parcial e ainda agrega

| Área | Base existente | Lacuna real | Destino |
| --- | --- | --- | --- |
| Evidências | Pacote JSON/CSV e disponibilidade local verificável | Falta definir prazo, limite, backup obrigatório e execução auditada da retenção | P05 |
| Operação e implantação | Launchers, configuração de exemplo, migrações e documentação | Falta aceite integrado em ambiente limpo, restauração de backup e implantação reproduzível | P06 |
| Segurança de publicação | Sessão local, CSRF, administração protegida e chave interna separada | `postMessage` ainda usa `*`; faltam políticas explícitas de embed e schema permitido de metadados | P07 |
| Contratos do frontend | Serviços separados e testes dos fluxos principais | Tipagem dos contratos críticos ainda depende de convenções | P08 |
| Observabilidade e precisão | Métricas, health e ferramentas de calibração existentes | Medições reais e novos mecanismos de monitoramento não estão validados | Adiado; ver seção 6 |

## 4. Backlog útil para a aplicação atual

P01–P04 estão encerrados localmente. P05 e P06 estão parciais; P07–P08 permanecem pendentes. Os critérios abaixo preservam o escopo de cada entrega.

### P01 — Unificar regras e comunicação — prioridade alta

**Status: concluído e validado localmente em 14/09/2026.**

- [x] Consolidar uma especificação de rodada baseada na configuração efetiva do backend: abertura, fechamento de apostas, fim da contagem, apuração e próxima ativação.
- [x] Explicar os limites exatos de cada mercado e usar os mesmos termos na interface, API e exemplos.
- [x] Remover afirmações de Turbo ativo e prazos fixos incompatíveis com o fluxo atual. Reativar Turbo exige decisão separada.
- [x] Explicar que o vídeo pode ter atraso e que o backend determina o resultado.

**Aceite:** um mesmo exemplo de rodada e de contagem no limite produz a mesma explicação em todos os pontos; nenhuma tela promete duração ou modalidade que o backend não oferece.

Origem: `TODO3` BN1–BN3, `ROUND_FORMULATION`, `bet` EP05 e `TODO2` fase E.

### P02 — Completar o congelamento e os snapshots por rodada — prioridade alta

**Status: concluído e validado localmente em 14/09/2026.**

- [x] Registrar na criação da rodada a configuração operacional necessária à reconstrução: câmera, perfil, identificação da origem, ROI, linha, direção e versão da configuração; relacionar os parâmetros comerciais já registrados.
- [x] Impedir que alterações posteriores sobrescrevam a configuração histórica.
- [x] Revisar alterações vindas do editor local, endpoints e sincronização remota. Manter a exceção de preparação entre rodadas explícita, sem mudar os dados da rodada anterior.
- [x] Para registros antigos sem snapshot completo, indicar a ausência; não reconstruir um histórico supostamente exato a partir da configuração atual.

**Aceite:** alterar o perfil seguinte não modifica a evidência da rodada encerrada; alterações manuais proibidas são recusadas; testes cobrem a exceção durante apuração e a preservação dos eventos anteriores.

Dependência: P01. Origem: `bet` EP06, `TODO3` BN4 e `ROUND_FORMULATION`.

### P03 — Completar auditoria administrativa e motivos de anulação — prioridade alta

**Status: concluído e validado localmente em 14/09/2026.**

- [x] Registrar ator, horário, ação, alvo, resultado e motivo das alterações críticas e das tentativas bloqueadas.
- [x] Definir códigos de motivo de `void`, mantendo descrição humana complementar e compatibilidade com os motivos históricos.
- [x] Cobrir mudança de configuração, anulação e futuras ações de recuperação; não registrar senhas, chaves ou payloads sensíveis.
- [x] Expor a trilha no backoffice com a autorização adequada.

**Aceite:** uma ação autorizada e uma tentativa recusada podem ser rastreadas até o responsável; anular continua sendo atômico com o encerramento das apostas.

Dependência: P02 para auditoria da configuração. Origem: `bet` EP06/EP10/EP13 e `TODO3` BN4.

### P04 — Fechar a recuperação operacional — prioridade alta

**Status: concluído e validado localmente em 14/09/2026.**

- [x] Documentar diagnóstico e tratamento de backend indisponível, fila acumulada, rejeição definitiva e apuração atrasada.
- [x] Definir quais falhas permitem repetição e quais exigem decisão administrativa, usando o estado já persistido.
- [x] Preservar IDs, payloads e horários originais. Rejeições de rodadas finalizadas não podem ser forçadas para outra rodada nem reabrir resultados silenciosamente.
- [x] Vincular a decisão de tratamento à trilha de auditoria. Uma tela pode ser adicionada quando o procedimento estiver definido.

O worker repete apenas falhas temporárias com o mesmo `eventHash`; respostas 400, 409, 410 e 422 permanecem como rejeições definitivas na outbox. `scripts/review-outbox.py` fornece diagnóstico somente leitura, com campos operacionais permitidos e sem payloads. O admin pode registrar decisões append-only (`acknowledged`, `investigating` ou `closed`) em `POST /admin/recovery-events/{eventId}/decision`; cada decisão é também vinculada à auditoria administrativa e não reenvia, edita ou reassocia o evento.

**Aceite:** queda e retorno do backend recuperam eventos elegíveis sem duplicar contagem; rejeições definitivas permanecem consultáveis, com decisão e responsável registrados. Validado localmente por testes de timeout/retomada idempotente, rejeição definitiva, diagnóstico sem payload e decisão administrativa imutável; não equivale à homologação com backend/câmera do ambiente operacional.

Dependência: P03 para ações administrativas. Origem: `TODO` item 8, `bet` EP04/EP11/EP16. Não inclui novos alertas ou monitoramento de detecção.

### P05 — Exportar e conservar evidências — prioridade média

**Status: parcial — exportação validada localmente; retenção pendente.**

- [x] Definir pacote por rodada contendo horários, resultado, mercados, crossings, timeline, snapshot da configuração e referências às imagens.
- [x] Exportar JSON e, quando útil à operação, CSV; evitar conteúdo pessoal ou segredos desnecessários.
- [ ] Definir prazo de retenção, limite de armazenamento, backup obrigatório e execução auditada. Usar armazenamento externo apenas se houver necessidade concreta.
- [x] Distinguir exportação de evidências de replay de vídeo e de reprocessamento do detector.

O pacote `videobettransit-round-evidence-v1` é disponível somente para admins e para rodadas encerradas, por JSON ou CSV. Ele exclui apostas, identidades, motivos livres, URLs de origem, credenciais e payloads do worker. Referências são sanitizadas; imagens locais distinguem `available` e `missing`, e externas ficam `external_unverified`. A política atual não remove evidências automaticamente.

**Aceite parcial:** uma rodada encerrada pode ser investigada pelo pacote exportado e ausências aparecem explicitamente. Validado localmente com JSON/CSV, autorização, sanitização e disponibilidade local. O aceite de retenção depende de prazo, limite, backup e procedimento auditado.

Dependências: P02 e P03. Origem: `TODO` item 15/BT4, `TODO3` BN4 e `bet` EP10/EP12/EP14.

### P06 — Validar instalação, backup e publicação — prioridade média

**Status: parcial — preparação local implementada em 14/09/2026.**

- [x] Criar diagnóstico da instalação, backup SQLite consistente com WAL/`quick_check` e manifesto, e restauração confinada a destino explícito.
- [x] Exigir configuração local de chave interna e conta admin antes do backend servir HTTP, exceto em testes e migração isolada.
- [x] Documentar conjunto de backup, restauração separada e preservação de chaves de sessão.
- [ ] Exercitar instalação limpa e restauração em outra instalação com os segredos reais provisionados.
- [ ] Escolher e homologar ambiente de publicação, HTTPS/proxy/persistência/rollback e handshake da câmera real.

`configure-local.ps1` completa SQLite local e o caminho persistente de Data Protection sem inventar senhas. `Test-LocalInstallation.ps1` valida esses requisitos. O backup resolve os caminhos efetivos dentro do projeto, consolida SQLite por sua API nativa e registra ausências; a restauração recusa travessia de diretório, links e divergências de tamanho ou hash antes de gravar. Testes locais cobrem WAL, manifesto válido e caminho malicioso, mas não substituem o exercício com uma instalação e dados operacionais reais.

- Testar instalação limpa e provisionamento de contas, startup completo, handshake de câmera e recuperação após reinício.
- Documentar e exercitar backup consistente e restauração do banco, outbox e configurações; preservar chaves de sessão quando aplicável.
- Escolher o ambiente de publicação e exercitar HTTPS, proxy, persistência e rollback nesse ambiente.
- Validar migrações e concorrência em PostgreSQL somente se ele for o banco de destino; validar Supabase remoto somente se utilizado.
- Antes de exposição pública, validar configuração obrigatória no startup e o comportamento quando segredos estiverem ausentes.

**Aceite:** outra instalação pode ser criada e restaurada com procedimento reproduzível; o relatório separa testes locais de verificações do ambiente publicado.

Origem: `TODO` itens 9–13/BT4, `bet` EP01/EP16 e `TODO2` fase A. Não inclui benchmark de precisão ou certificação de operação 24/7.

### P07 — Restringir embed e dados opcionais — prioridade média

- Definir se o embed continuará disponível na demonstração. Se permanecer, restringir `postMessage` às origens configuradas e validar mensagens recebidas quando houver esse fluxo.
- Aplicar CSP e política de enquadramento coerentes com a hospedagem escolhida.
- Definir campos permitidos para `metadataJson`, além do limite de tamanho existente; revisar dados enviados aos logs e eventos do embed.
- Não adaptar cookies para uma integração externa indefinida: autenticação entre sites depende do contrato de operador da seção 5.

**Aceite:** origem não permitida não recebe eventos direcionados; metadados fora do schema são recusados ou removidos conforme contrato; login local e navegação continuam funcionando.

Dependência: decisão de hospedagem de P06 para os cabeçalhos finais. Origem: revisão de segurança de `bet`, EP13–EP15 e `TODO2` fases B/D/E.

### P08 — Tipar os contratos críticos sem reescrever a interface — prioridade baixa

- Introduzir tipos ou JSDoc para autenticação, rodadas, mercados, apostas e respostas de erro.
- Concentrar a melhoria nos serviços e nas fronteiras da API; manter o carregamento sob demanda já entregue.

**Aceite:** os contratos críticos são verificáveis no desenvolvimento e alterações incompatíveis são detectadas antes da execução; não é necessária uma migração integral para TypeScript.

Origem: `TODO` BT1.

### Ordem de execução

1. **Concluído localmente — regras, integridade e recuperação:** P01 → P02 → P03 → P04.
2. **Próximo bloco — concluir retenção e instalação:** P05 → P06.
3. **Publicação e manutenção:** P07 antes de liberar embed público; P08 conforme necessidade de manutenção.

P06 pode antecipar testes de instalação e backup. P07 pode antecipar schema de metadados e restrição de mensagens. A ordem não autoriza ativar as frentes condicionadas ou adiadas.

## 5. O que agrega somente com evolução para provider

| Frente condicionada | O que aproveitar | O que ainda precisa ser entregue | Condição de entrada |
| --- | --- | --- | --- |
| Contrato provider–operador | Core de rodadas e apostas | Responsabilidades, sessões, launch token, autenticação entre servidores, API versionada, OpenAPI e erros contratuais | Definir operador e modelo de integração; `TODO2` A/B e `bet` EP07/EP13 |
| Webhooks externos | Experiência da outbox do worker | Outbox própria do backend, HMAC, proteção contra replay, retries, rejeições, consulta e reenvio auditado por operador | Contrato externo definido; `bet` EP08 |
| Carteira e reconciliação financeira | Identificadores idempotentes e registro das apostas simuladas | Modelo de carteira, balance/debit/settle/rollback, tratamento de timeout, conciliação e limites agregados | Decisão explícita sobre dinheiro real e contrato financeiro; `TODO2` C e `bet` EP09 |
| Matemática comercial | Mercados e serviço de linhas dinâmicas existentes | Validação de probabilidades, odds, exposição máxima e elegibilidade de mercados por câmera | Dados confiáveis e decisão comercial; `TODO3` BN5 e `bet` EP05. Depende também da retomada da trilha adiada |
| Multioperadora | Identidade autenticada com escopo de operador | Entidades de operadores, isolamento completo, credenciais, moedas, limites, webhooks e permissões por tenant | Mais de uma integração concreta; `bet` EP16 |
| Operação contínua | Persistência, health e recuperação local | Serviços supervisionados, política de disponibilidade, failover, ensaios de carga e procedimentos de suporte | Ambiente e metas definidos; novos mecanismos de monitoramento continuam adiados |
| Auditoria externa e requisitos regulatórios | Eventos, evidências e auditoria interna a completar | Mapeamento de dados, retenção aplicável, integridade verificável, avaliação especializada e pacote de homologação | Jurisdição, operador e requisitos definidos; `TODO2` D e `bet` EP14. Referências antigas não comprovam conformidade |
| Replay e reprocessamento | Eventos e snapshots disponíveis | Gravações suficientes, execução isolada com configuração versionada e decisão auditada sem sobrescrever o resultado original | Necessidade de suporte demonstrada e política de evidências pronta; `bet` EP12 |
| Rollout por operador | Frontend e admin existentes | Ambiente de homologação, flags, critérios de habilitação, rollback e aprovação operacional | Contratos, segurança e validações anteriores concluídos; `TODO2` E e `bet` EP15 |

Uma VPS com um worker pode continuar como proposta inicial simples. Separar máquinas, adicionar câmeras, adotar Supabase como banco principal ou criar serviços independentes depende do ambiente escolhido e de necessidade comprovada; não é uma entrega obrigatória da demonstração.

## 6. O que permanece adiado por decisão anterior

O usuário excluiu o **item 6 da análise de melhorias anterior: precisão da detecção e novos mecanismos de monitoramento**. Essa exclusão não se refere ao item 6 do `TODO.md` (testes .NET), nem automaticamente à fase 6 de `bet.md`.

Permanecem fora da execução:

- Benchmark com vídeos rotulados e medição de falsos positivos, falsos negativos e dupla contagem.
- Troca ou ajuste de modelo, `imgsz`, tracking, perspectiva e thresholds guiados por novos experimentos.
- Novos alertas, métricas de frescor real de frames, detecção automática de deriva e monitoramento adicional de precisão.
- Retomada dos experimentos de stream/encode associados a essa trilha sem novo escopo.

Isso abrange principalmente `TODO` BT3 e partes de BT2/item 17, `SPRINTS` 3–5 e partes de `bet` EP11/EP16. Ferramentas e métricas existentes continuam sendo base; não tornam essa trilha concluída. Procedimentos de recuperação de dados em P04 têm escopo distinto e não reabrem esse trabalho.

## 7. Contradições resolvidas e tarefas filtradas

| Registro antigo | Resultado do cruzamento |
| --- | --- |
| `TODO` manda remover `hls.js` e adotar apenas MJPEG | Superado. O player atual utiliza HLS sob demanda e caminhos de fallback. Não remover uma dependência ativa para satisfazer um checklist antigo. |
| Tarefas apontam para `traffic-counter-front/` ou tratam `app.py` da raiz como implementação principal | Superado. Usar os diretórios oficiais; manter os shims enquanto necessários à compatibilidade. |
| `bet` EP05 declara sorteio de Normal/Turbo concluído | Não corresponde ao fluxo atual: `RoundService` cria `RoundMode.Normal` e usa timing/mercados Normal. Tipos legados não provam modalidade ativa. |
| `TODO3`: Turbo de 120 segundos, fechamento 30 segundos antes do fim; `ROUND_FORMULATION`: 180 segundos, fechamento aos 70 | Conflito de especificação. Não escolher uma duração arbitrariamente. P01 documentará os valores efetivos e sua semântica; no código `EndsAt = BetCloseAt + DurationSeconds`. |
| `TODO3` descreve Over como “supera” o alvo | O código aplica `>=`; Under usa `<`, Range inclui os dois extremos e Exact exige igualdade. A comunicação deve refletir esses limites. |
| `ROUND_FORMULATION` prevê próxima rodada imediatamente e associação apenas à rodada ativa | A ativação tem condições operacionais. Eventos precisam respeitar câmera, rodada original e janela de ocorrência; não podem ser reassociados para compensar atraso. |
| `bet` recomenda uma câmera global; `ROUND_FORMULATION` modela rodadas por câmera | Não exige reescrita: uma implantação pode operar uma câmera usando o modelo por câmera. Escala simultânea não está automaticamente aprovada. |
| `bet` EP09 considera `POST /internal/bets` a entrada vigente | Superado. Aposta passa pelo fluxo autenticado de `/bets`; a chave do worker não concede identidade de jogador. |
| Revisão de abril diz que qualquer cliente pode forjar identidade e que chave vazia libera acesso | Corrigido no fluxo local atual. Permanecem pendentes o contrato de operador, o embed e a validação completa de configuração de produção. |
| `TODO` marca histórico/CSV e alertas como inteiramente concluídos | Não assumir paridade com telas antigas. Há histórico e backoffice atuais; exportação completa vai para P05 e novos alertas permanecem adiados. |
| `bet` marca retry, hash e auditoria como base suficiente para provider | Deduplicação e outbox não equivalem a entrega externa, trilha imutável ou prova de integridade. Cada lacuna tem destino próprio. |
| `SPRINTS` propõe retornar ao commit `9230acf` como preparação | Histórico de retomada, não tarefa atual. Não desfazer as correções existentes para reproduzir aquela sequência. |
| `TODO` chama precisão de requisito obrigatório para encerrar todo o projeto | Trilha relevante, mas adiada pela decisão posterior do usuário. Não afirmar conclusão total nem reativá-la implicitamente. |
| Tabelas, migrações ou arquivos de deploy aparecem como produção concluída | Preparação técnica. Exigir os aceites reais de P06 e, quando aplicável, os da seção 5. |

Foram removidas da fila de trabalho as repetições de modelagem já entregue, recriação do motor de rodadas, implementação inicial de autenticação, histórico já disponível e divisão de bundle já realizada. Novas abstrações, infraestrutura distribuída e substituição do transporte de vídeo sem problema demonstrado não entram como tarefas obrigatórias.

## 8. Rastreabilidade dos seis documentos

| Fonte | Destino da parte aproveitável |
| --- | --- |
| `TODO.md` P0, itens 5–16 e BT1 | Base implementada; lacunas específicas em P05–P08. Orientações de frontend e HLS antigos foram superadas. |
| `TODO.md` item 17, BT2 e BT3 | Recursos existentes registrados; melhorias de precisão e novos mecanismos de monitoramento adiados. |
| `TODO.md` BT4 | Retenção e recuperação em P05/P06; armazenamento externo condicionado ao volume. |
| `TODO2.md` A–E | Seção 5; segurança básica já entregue; proteção de embed e metadados em P07. |
| `TODO3.md` BN1–BN3 | Motor e UX existentes; regras e linguagem em P01. |
| `TODO3.md` BN4–BN5 | Integridade e evidências em P02/P03/P05; matemática comercial condicionada. |
| `SPRINTS.md` 1–2 | Retomada histórica e entregas atuais; não repetir rollback nem refazer a base. |
| `SPRINTS.md` 3–5 | Trilha adiada; carregamento do frontend já melhorado, sem afirmar benchmark real de vídeo. |
| `SPRINTS.md` 6 | Integração externa condicionada na seção 5. |
| `ROUND_FORMULATION.md` | Autoridade do backend preservada; regras em P01, snapshots e bloqueios em P02, auditoria e evidências em P03/P05. |
| `bet.md` EP01–EP04 | Núcleo implementado; startup em P06 e recuperação em P04. |
| `bet.md` EP05–EP06 | P01/P02/P03; Turbo e matemática comercial dependem de decisão específica. |
| `bet.md` EP07–EP09 | Contratos externos condicionados; registro e liquidação de apostas simuladas já implementados. |
| `bet.md` EP10–EP12 | Backoffice parcial; P03–P05; replay condicionado e novos alertas adiados. |
| `bet.md` EP13–EP16 | Segurança local implementada; P03/P06/P07; provider, regulação e escala condicionados. |

## 9. Como manter este plano

Atualizar o status do item somente com referência à implementação e à validação correspondente. Separar sempre código entregue, teste local, teste integrado e aceite de produção. Para encerrar o backlog da aplicação atual, concluir os itens restantes P05–P08 ou registrar explicitamente uma decisão de retirada. As frentes condicionadas e adiadas não devem ser marcadas como concluídas por consequência desse encerramento.
