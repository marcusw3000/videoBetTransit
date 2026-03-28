# TODO2.md - Integracao como game provider regulado

Planejamento estrategico para integrar o produto dentro de uma operadora regulada, partindo do estado estavel `9230acf`.

Premissa:
- este arquivo e de preparacao e arquitetura
- nada aqui deve ser implementado antes de a base tecnica voltar a evoluir com seguranca

---

## Fase A - Arquitetura provider x operador

- [ ] Definir modelo de integracao: provider-hosted vs embed
- [ ] Definir responsabilidades `provider / operador / compartilhado`
- [ ] Definir topologia de ambientes: `dev`, `qa`, `cert`, `staging`, `prod`
- [ ] Definir politica de release, rollback e suporte

Entregavel:
- documento de arquitetura aprovado

## Fase B - Seguranca e sessao

- [ ] Definir launch token assinado
- [ ] Definir autenticacao server-to-server forte
- [ ] Definir segregacao por ambiente e gestao de segredos
- [ ] Definir RBAC administrativo e auditoria

Entregavel:
- base de seguranca pronta para integracao

## Fase C - Wallet e contratos

- [ ] Definir contrato de `balance`, `bet`, `settle`, `rollback`
- [ ] Definir idempotencia e reconciliacao
- [ ] Definir chaves tecnicas: `transaction_id`, `round_id`, `game_session_id`
- [ ] Definir codigos de erro e timeout

Entregavel:
- contrato operator-provider pronto para homologacao

## Fase D - LGPD, auditoria e certificacao

- [ ] Mapear fluxo de dados e minimizacao de PII
- [ ] Definir retencao de evidencias
- [ ] Preparar trilha de auditoria e pacote de evidencias
- [ ] Definir estrategia com certificadora

Entregavel:
- pacote regulatorio inicial

## Fase E - Embed e rollout

- [ ] Definir UX embedada em `.bet.br`
- [ ] Definir trusted origins, CSP e frame policy
- [ ] Definir rollout controlado por operador
- [ ] Definir monitoracao, alertas e runbooks

Entregavel:
- plano de entrada em producao regulada
