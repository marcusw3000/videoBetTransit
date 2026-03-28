# LATENCIA_E_CONFIANCA.md

Diretrizes para evoluir a entrega de video do jogo com foco em:
- menor latencia percebida pelo cliente
- menor espaco para suspeita de manipulacao
- maior robustez operacional e auditavel

Ponto de partida:
- estado atual de referencia do projeto: `9230acf`
- a contagem oficial continua sendo responsabilidade do backend/engine
- o objetivo nao e apenas deixar o video rapido, mas deixar a experiencia confiavel

---

## 1. Principio central

A confianca do cliente precisa vir da combinacao de:
- video o mais ao vivo possivel
- regra de round clara
- resultado oficial persistido e auditavel
- evidencia tecnica suficiente para revisao e disputa

Regra pratica:
- o video ajuda a percepcao de transparencia
- a fonte oficial do resultado continua sendo o backend

---

## 2. Abordagens possiveis

## Abordagem A - Video original com menor latencia possivel

Descricao:
- entregar ao cliente a stream original com o menor buffer possivel
- manter a engine Python como origem da contagem oficial
- manter overlay minimo para o cliente

Cliente ve:
- stream
- `mark line`
- boxes
- status do round
- timer
- `round_id`

Vantagens:
- melhor percepcao de "ao vivo"
- menor sensacao de video atrasado propositalmente
- reduz friccao de confianca

Riscos:
- a stream visual e a contagem oficial podem nao ser exatamente a mesma pipeline
- exige cuidado para que a UX nao pareca divergente do settlement

Quando usar:
- se a prioridade principal for confianca percebida do jogador

---

## Abordagem B - Stream anotado de baixa latencia

Descricao:
- entregar ao cliente o proprio stream anotado pela engine
- otimizar essa pipeline para operar com o menor atraso possivel

Vantagens:
- o cliente ve exatamente o que a engine esta usando
- reduz ambiguidade entre video e contagem

Riscos:
- pipeline mais pesada
- maior risco de latencia se inferencia, desenho e encode nao forem muito bem controlados

Quando usar:
- se houver capacidade tecnica de manter atraso muito baixo com estabilidade

---

## Abordagem C - Migracao de protocolo para low latency real

Descricao:
- substituir HLS/MJPEG por tecnologia mais apropriada para latencia baixa
- candidato principal: `WebRTC`

Vantagens:
- latencia muito menor
- experiencia mais proxima de transmissao ao vivo real
- melhor encaixe para produto sensivel a percepcao de atraso

Riscos:
- infraestrutura mais complexa
- aumento de custo e complexidade de operacao
- exige nova trilha de arquitetura

Quando usar:
- se o produto for para operacao comercial real e a latencia virar requisito central

---

## Abordagem D - Fonte oficial auditavel como centro da confianca

Descricao:
- independentemente do protocolo de video, o backend consolidado e a fonte oficial do resultado

Cada round deve registrar:
- `round_id`
- `camera_id`
- `created_at`
- `bet_close_at`
- `ends_at`
- `final_count`
- `settlement_status`
- eventos de contagem
- motivo de `void`, quando houver

Vantagens:
- reduz discussao sobre manipulacao
- sustenta auditoria, disputa e certificacao
- desacopla confianca do usuario do protocolo de video isoladamente

Quando usar:
- sempre

---

## 3. Recomendacao para o produto

Recomendacao principal:
1. manter o backend como fonte oficial do resultado
2. entregar ao cliente o video com o menor atraso possivel
3. fechar apostas antes do fim do round
4. mostrar apenas overlays minimos ao cliente
5. manter trilha de auditoria completa

Equilibrio recomendado:
- curto prazo: melhorar a entrega atual sem quebrar estabilidade
- medio prazo: revisar protocolo de streaming
- longo prazo: avaliar `WebRTC`

---

## 4. Regras de produto que aumentam confianca

## 4.1 Fechamento antecipado de aposta

Regra:
- apostas fecham antes do fim do round

Objetivo:
- absorver latencia residual
- reduzir exploracao de atraso
- deixar o settlement tecnicamente mais confiavel

## 4.2 Overlays minimos

Permitir ao cliente ver apenas:
- `mark line`
- boxes de identificacao
- timer
- status
- identificacao do round

Nao mostrar:
- `ROI`
- debug
- paines operacionais
- sinais tecnicos internos

## 4.3 Transparencia simples

Sempre deixar claro:
- a contagem oficial considera a passagem pela linha de marcacao
- o resultado oficial e consolidado ao final do round
- rounds podem ser anulados em caso de falha tecnica relevante

---

## 5. Estrategia de implementacao

## Fase 1 - Confianca sem grande refactor

- estabilizar o tracking
- estabilizar a janela Python
- documentar o settlement como fonte oficial
- manter stream com overlay minimo
- validar latencia real do estado atual

Status atual:
- [x] documento de estrategia criado
- [x] instrumentacao basica da pipeline adicionada ao `/health`
- [ ] medir diferenca real entre stream original e stream anotado

## Fase 2 - Reducao de atraso com baixo risco

- medir gargalo de inferencia
- medir gargalo de encode
- medir diferenca entre stream original e stream anotado
- reduzir custo por frame de forma incremental

## Fase 3 - Revisao arquitetural de streaming

- avaliar se HLS/MJPEG atende o produto final
- avaliar uso de WebRTC
- definir topologia final para ambiente de operadora

## Fase 4 - Operacao regulada

- garantir trilha de auditoria completa
- garantir retencao de evidencias
- garantir politicas de `void`, disputa e revisao

---

## 6. Criterios de decisao

Escolher prioridade principal:

### Prioridade 1 - Confianca percebida
- favorece video mais ao vivo possivel
- mesmo que o overlay seja minimo

### Prioridade 2 - Consistencia visual com a engine
- favorece stream anotado pela propria pipeline oficial

### Prioridade 3 - Menor latencia tecnica absoluta
- favorece revisao de protocolo, especialmente `WebRTC`

### Prioridade 4 - Escalabilidade regulada
- favorece backend auditavel, trilha de evidencias e contratos claros

---

## 7. Recomendacao executiva final

Para a solucao final:
- o cliente deve ver video de baixa latencia
- o backend deve continuar como unica fonte oficial do resultado
- a UI do cliente deve ser simples e transparente
- a aposta deve fechar antes do fim
- cada round deve ser auditavel

Melhor direcao de longo prazo:
- migrar para arquitetura de stream mais apropriada para latencia baixa
- manter settlement, auditoria e evidencia no backend

Melhor direcao de curto prazo:
- nao tentar resolver confianca apenas com o frontend
- melhorar a entrega de video e a clareza da regra de contagem
