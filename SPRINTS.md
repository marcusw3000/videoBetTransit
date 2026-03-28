# SPRINTS.md - Replanejamento a partir do 9230acf

Sequencia recomendada de sprints depois do rollback para o commit estavel `9230acf`.

Premissa:
- primeiro proteger a base que voltou a funcionar
- depois reintroduzir produto
- por ultimo voltar a mexer em tracking/performance

---

## Sprint 1 - Congelamento e retomada

Foco:
- registrar o ponto estavel e reorganizar backlog

Itens:
- [x] congelar o projeto em `9230acf`
- [x] criar `RETOMADA.md`
- [x] recriar `TODO2.md`
- [x] recriar `TODO3.md`
- [x] recriar `SPRINTS.md`
- [x] atualizar `TODO.md`

Gate:
- repositório limpo e planejamento consistente

## Sprint 2 - Produto v1 no backend/frontend

Foco:
- reintroduzir o jogo sem tocar no Python

Itens:
- [ ] estados do round
- [ ] mercados `Under / Range / Over / Exact`
- [ ] historico comercial
- [ ] UI `v1` web/mobile

Gate:
- produto comercial refletido no front e no backend

## Sprint 3 - Ferramentas de calibracao

Foco:
- preparar diagnostico sem alterar a base de video

Itens:
- [ ] ferramentas de revisao de casos
- [ ] instrumentacao leve
- [ ] testes auxiliares

Gate:
- time consegue calibrar com evidencias reais

## Sprint 4 - Tracking

Foco:
- melhorar contagem com passos pequenos

Itens:
- [ ] rever thresholds
- [ ] validar em pista real
- [ ] medir antes/depois

Gate:
- melhoria mensuravel sem regressao operacional

## Sprint 5 - Performance

Foco:
- otimizar sem quebrar a janela Python

Itens:
- [x] medir latencia e FPS do estado base
- [x] otimizar encode/configuracao primeiro
- [ ] testar mudancas mais profundas em branch separada
- [ ] comparar stream original vs stream anotado e decidir diretriz de produto para o cliente final
- [x] encontrar uma baseline funcional de baixa latencia sem quebrar estabilidade

Gate:
- video mais fluido sem perda de estabilidade

## Sprint 6 - Integracao regulada

Foco:
- avancar na trilha provider/operador

Itens:
- [ ] sessao
- [ ] wallet
- [ ] seguranca
- [ ] auditoria
- [ ] embed

Gate:
- base pronta para homologacao com operador
