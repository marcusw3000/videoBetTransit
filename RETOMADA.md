# RETOMADA.md - Plano de retomada a partir do 9230acf

Documento de retomada segura do projeto a partir do commit estavel `9230acf`.

Objetivo:
- preservar o ponto que voltou a funcionar bem
- reintroduzir evolucoes em ordem de menor risco
- evitar repetir o acoplamento entre tracking, performance e produto

---

## 1. Ponto atual

Estado congelado:
- commit de referencia: `9230acf`
- tracking funcionando
- video no Python rodando bem
- prioridade: nao quebrar a base operacional
- baseline atual de latencia:
  - tuning moderado da captura FFmpeg
  - `imgsz: 320`
  - atraso percebido caiu de aproximadamente `2 min` para algo proximo do stream original

Regra de trabalho:
- qualquer nova evolucao deve partir deste ponto
- mudancas de tracking e mudancas de performance nao entram no mesmo ciclo
- todo passo deve ser validado antes do seguinte

---

## 2. Ordem de reaplicacao recomendada

### Etapa A - Planejamento e documentacao
- [x] Recriar `TODO2.md`
- [x] Recriar `TODO3.md`
- [x] Recriar `SPRINTS.md`
- [x] Atualizar `TODO.md` para registrar o rollback

Objetivo:
- recuperar organizacao sem mexer no runtime

### Etapa B - Produto no frontend/backend, sem tocar no Python
- [ ] Reintroduzir regras de negocio de rounds e mercados no backend .NET
- [ ] Reintroduzir cards de mercados no frontend
- [ ] Reintroduzir historico comercial e estados do round

Objetivo:
- evoluir produto sem arriscar tracking e video

### Etapa C - Ferramentas de calibracao
- [ ] Reintroduzir utilitarios de revisao de casos
- [ ] Reintroduzir testes auxiliares que nao alterem a runtime principal
- [ ] Reintroduzir instrumentacao leve para revisar pistas reais

Objetivo:
- preparar a calibracao sem mexer na base de captura

### Etapa D - Tracking
- [ ] Revisar `conf`, `min_hits_to_count` e `min_bbox_area`
- [ ] Validar uma alteracao por vez em pista real
- [ ] Registrar baseline antes/depois de cada ajuste

Objetivo:
- melhorar deteccao sem repetir regressao de estabilidade

### Etapa E - Performance
- [x] Medir FPS e latencia reais no estado base
- [x] Atacar primeiro configuracao e encode, nao arquitetura de captura
- [ ] So testar captura assincrona em branch separada e com rollback facil
- [x] Encontrar um baseline operacional de baixa latencia sem trocar a arquitetura da captura

Objetivo:
- evitar nova quebra da janela Python

---

## 3. Gates obrigatorios

Cada reaplicacao so avanca se passar em:
- `python -m py_compile app.py`
- `dotnet test`
- `npm run build`
- teste manual real

Para tracking/performance:
- validar video no Python
- validar tracking
- validar contagem

---

## 4. O que nao fazer agora

- nao misturar performance do Python com nova logica de contagem
- nao reintroduzir varias heuristicas de crossing no mesmo passo
- nao mexer em frontend, backend e Python ao mesmo tempo sem necessidade
- nao usar o repositório principal como laboratorio de captura assincrona

---

## 5. Definicao de sucesso

Sucesso desta retomada:
- projeto continua estavel no Python
- backlog volta a existir de forma organizada
- proxima evolucao fica claramente separada por trilha
