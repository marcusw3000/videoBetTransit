# TODO.md - videoBetTransit

Checklist de evolucao do projeto, organizado por prioridade, impacto e area tecnica. A ideia e servir como guia pratico de implementacao nas proximas iteracoes.

## Como usar este arquivo

- `[ ]` nao iniciado
- `[~]` em andamento
- `[x]` concluido

Prioridades:
- `P0`: importante agora, reduz risco ou remove debito tecnico imediato
- `P1`: importante em seguida, melhora robustez e manutencao
- `P2`: importante para producao
- `P3`: evolucao de produto ou melhoria futura

---

## P0 - Limpeza e consistencia do codigo

### Plano de execucao do P0

Meta do P0:
- consolidar a arquitetura atual baseada em MJPEG
- remover restos do fluxo antigo
- reduzir duplicacao de codigo
- deixar configuracao e textos consistentes

Escopo fechado do P0:
- frontend sem dependencia do fluxo HLS legado
- engine Python com rotina unica de anotacao
- URLs principais configuradas por ambiente
- textos e mensagens sem encoding quebrado nos arquivos tocados

Arquivos mais provaveis de impacto:
- [`app.py`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\app.py)
- [`traffic-counter-front/package.json`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\traffic-counter-front\package.json)
- [`traffic-counter-front/src/App.jsx`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\traffic-counter-front\src\App.jsx)
- [`traffic-counter-front/src/components/VideoPlayer.jsx`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\traffic-counter-front\src\components\VideoPlayer.jsx)
- [`traffic-counter-front/src/components/VideoOverlayCanvas.jsx`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\traffic-counter-front\src\components\VideoOverlayCanvas.jsx)
- [`traffic-counter-front/src/services`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\traffic-counter-front\src\services)
- [`start.bat`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\start.bat)
- [`contexto.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\contexto.md)

Dependencias entre tarefas:
1. limpar HLS legado
2. extrair anotacao unica no Python
3. mover configuracao do frontend para `.env`
4. corrigir encoding e revisar mensagens

Riscos do P0:
- remover algo do fluxo antigo e quebrar build sem perceber
- alterar a anotacao do frame e gerar divergencia visual
- migrar URLs para `.env` e esquecer fallback de desenvolvimento
- misturar correcao funcional com limpeza estetica e expandir demais o escopo

Estrutura de execucao sugerida:

#### P0.1 - Consolidar frontend atual
- [x] Mapear imports e usos remanescentes do fluxo HLS/overlay.
- [x] Remover a dependencia `hls.js`.
- [x] Remover o componente `VideoOverlayCanvas.jsx` se nao houver mais referencia.
- [x] Rodar build do frontend.

Resultado esperado:
- front refletindo apenas a arquitetura MJPEG atual.

#### P0.2 - Consolidar pipeline de anotacao no Python
- [x] Criar helper de anotacao de frame.
- [x] Usar o helper para MJPEG e janela local.
- [x] Garantir que `TOTAL`, ROI, linha e boxes continuem identicos.
- [x] Validar sintaxe com `python -m py_compile app.py`.

Resultado esperado:
- uma unica fonte de verdade para anotacao visual.

#### P0.3 - Externalizar configuracao do frontend
- [x] Criar `.env.example` no frontend.
- [x] Introduzir `VITE_API_BASE_URL`.
- [x] Introduzir `VITE_MJPEG_URL`.
- [x] Ajustar `App.jsx` e servicos para usar essas variaveis.
- [x] Manter um comportamento simples para desenvolvimento local.

Resultado esperado:
- troca de ambiente sem editar codigo.

#### P0.4 - Revisao de textos e encoding
- [x] Corrigir textos quebrados dos arquivos alterados no P0.
- [x] Revisar `start.bat`.
- [x] Revisar labels principais do frontend.
- [x] Atualizar `contexto.md` para refletir o resultado final do P0.

Resultado esperado:
- base mais polida e mais facil de manter.

Definicao de pronto do P0:
- frontend buildando sem `hls.js`
- sem componentes mortos do fluxo antigo
- `app.py` com anotacao centralizada
- frontend sem URL principal hardcoded
- textos principais sem caracteres corrompidos

Validacao minima do P0:
- [x] `python -m py_compile app.py`
- [x] `npm run build` em [`traffic-counter-front`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\traffic-counter-front)
- [ ] subir via [`start.bat`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\start.bat)
- [ ] confirmar que o feed MJPEG continua aparecendo no navegador
- [ ] confirmar que a contagem e a lista de deteccoes continuam atualizando

Fora do escopo do P0:
- persistencia em banco
- autenticacao
- observabilidade avancada
- editor visual de ROI
- reestruturacao completa do backend
- deploy de producao

### 1. Remover artefatos do fluxo antigo de HLS
- [x] Remover `hls.js` de [`traffic-counter-front/package.json`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\traffic-counter-front\package.json).
- [x] Remover [`VideoOverlayCanvas.jsx`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\traffic-counter-front\src\components\VideoOverlayCanvas.jsx) se realmente nao houver mais uso.
- [x] Confirmar que nenhum outro arquivo do frontend importa componentes do fluxo antigo.
- [x] Rodar build do frontend apos a limpeza.

Objetivo:
- Reduzir dependencias desnecessarias.
- Evitar confusao sobre a arquitetura atual.

Entregavel esperado:
- Frontend limpo, sem referencias ao fluxo antigo de video com overlay local.

### 2. Extrair a rotina de anotacao do frame
- [x] Criar uma funcao dedicada em [`app.py`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\app.py) para desenhar ROI, linha, boxes, labels e contador.
- [x] Reutilizar essa funcao para o frame MJPEG e para a janela OpenCV local.
- [x] Remover duplicacao atual da logica de desenho.

Objetivo:
- Melhorar manutencao.
- Evitar divergencia visual entre MJPEG e janela local.

Entregavel esperado:
- Uma unica funcao de anotacao de frame, reutilizada em todos os pontos.

### 3. Remover configuracoes hardcoded no frontend
- [x] Mover `liveStreamUrl` de [`traffic-counter-front/src/App.jsx`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\traffic-counter-front\src\App.jsx) para `.env`.
- [x] Criar variaveis como `VITE_API_BASE_URL` e `VITE_MJPEG_URL`.
- [x] Atualizar servicos do frontend para consumir essas variaveis.
- [x] Documentar o uso no [`contexto.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\contexto.md).

Objetivo:
- Facilitar troca de ambiente.
- Evitar edicao manual de codigo para mudar IP ou porta.

Entregavel esperado:
- Frontend configuravel por ambiente.

### 4. Corrigir encoding e padronizacao de texto
- [x] Corrigir textos quebrados em [`start.bat`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\start.bat).
- [x] Corrigir textos quebrados em [`traffic-counter-front/src/App.jsx`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\traffic-counter-front\src\App.jsx) e demais arquivos com caracteres corrompidos.
- [x] Padronizar arquivos novos em UTF-8.
- [x] Revisar mensagens de log e interface.

Objetivo:
- Melhorar acabamento do projeto.
- Evitar ruidao visual na operacao e na UI.

Entregavel esperado:
- Mensagens e labels limpas em toda a aplicacao.

---

## P1 - Robustez e manutencao

### 5. Adicionar testes unitarios para a engine Python
- [x] Criar testes para `inside_roi`.
- [x] Criar testes para `crossed_horizontal_segment`.
- [x] Criar testes para `bbox_area`.
- [x] Criar testes para regras de contagem e prevencao de dupla contagem.
- [x] Cobrir cenarios de `count_direction` (`up`, `down`, `any`).

Objetivo:
- Garantir que a logica critica de contagem continue correta.

Entregavel esperado:
- Suite minima de testes da engine com execucao previsivel.

### 6. Adicionar testes de integracao no backend .NET
- [x] Testar `GET /api/rounds/current`.
- [x] Testar `GET /api/rounds/history`.
- [x] Testar `POST /api/rounds/settle`.
- [x] Testar `POST /api/rounds/count-events`.
- [x] Verificar comportamento quando o round ja foi encerrado.

Objetivo:
- Validar o contrato da API.
- Reduzir risco de regressao no fluxo de round.

Entregavel esperado:
- Backend com cobertura minima dos endpoints principais.

### 7. Melhorar observabilidade
- [x] Logar FPS medio e FPS instantaneo.
- [x] Logar tempo de inferencia por frame.
- [x] Logar tempo de encode JPEG do MJPEG.
- [x] Expor numero de clientes conectados ao feed MJPEG.
- [x] Melhorar o endpoint `/health` para incluir status basico de stream/backend.

Objetivo:
- Facilitar diagnostico.
- Entender gargalos de performance.

Entregavel esperado:
- Logs e sinais operacionais mais confiaveis.

### 8. Melhorar resiliencia da comunicacao com backend
- [x] Revisar `backend_client.py` para timeout, retry e logging mais claros.
- [x] Tratar queda temporaria do backend sem travar o loop principal.
- [x] Evitar explosao de threads se o backend estiver indisponivel.
- [ ] Considerar fila interna com descarte controlado para eventos.

Objetivo:
- Fazer a engine degradar de forma segura em caso de falha externa.

Entregavel esperado:
- Fluxo de envio HTTP mais robusto.

### 9. Refinar o start.bat
- [x] Validar se a porta do backend ja esta em uso.
- [x] Validar se a porta do MJPEG ja esta em uso.
- [x] Checar se `node_modules` e `.venv` estao saudaveis.
- [x] Fazer teste opcional do endpoint `/health` depois de subir a engine.
- [x] Exibir URLs finais de frontend, backend e MJPEG.

Objetivo:
- Melhorar a experiencia operacional local.

Entregavel esperado:
- Script de start mais confiavel e autoexplicativo.

---

## P2 - Pronto para producao

### 10. Substituir o servidor de desenvolvimento do Flask
- [x] Trocar `Flask.run()` por `waitress` ou outra opcao apropriada para Windows.
- [x] Isolar a criacao do app Flask para facilitar deploy.
- [x] Garantir encerramento limpo do servidor.

Objetivo:
- Tornar o servidor MJPEG mais adequado para carga real.

Entregavel esperado:
- Feed MJPEG servido por runtime mais estavel.

### 11. Colocar frontend, backend e MJPEG sob a mesma estrategia de publicacao
- [ ] Definir topologia final de deploy.
- [x] Evitar mixed content entre frontend HTTPS e MJPEG HTTP.
- [x] Considerar reverse proxy unico para React, API e MJPEG.
- [x] Documentar isso no [`contexto.md`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\contexto.md).

Objetivo:
- Reduzir problemas de navegador e simplificar acesso.

Entregavel esperado:
- Arquitetura de publicacao coerente.

### 12. Persistir rounds, eventos e configuracoes
- [x] Substituir armazenamento in-memory do backend por banco.
- [x] Persistir rounds.
- [x] Persistir count-events.
- [x] Persistir configuracoes da camera, ROI e linha.
- [x] Criar migracoes e estrategia de inicializacao.

Objetivo:
- Manter historico real.
- Tornar o sistema confiavel entre reinicios.

Entregavel esperado:
- Backend com persistencia.

### 13. Adicionar autenticacao e autorizacao
- [x] Proteger rotas administrativas.
- [x] Proteger alteracao de configuracoes da camera.
- [x] Proteger endpoint de settle manual.
- [x] Definir se o feed MJPEG deve ser publico ou protegido.
- [x] Adicionar politica de CORS e segredos por ambiente.

Objetivo:
- Evitar uso indevido em ambiente real.

Entregavel esperado:
- Superficies sensiveis protegidas.

---

## P3 - Evolucao de produto

### 14. Melhorar a tela operacional
- [x] Mostrar status da camera.
- [x] Mostrar status do backend.
- [x] Mostrar status do feed MJPEG.
- [x] Mostrar FPS e latencia estimada.
- [x] Mostrar ultimo evento recebido.

Objetivo:
- Dar visibilidade operacional para quem acompanha a contagem.

Entregavel esperado:
- Dashboard mais util para uso real.

### 15. Melhorar historico e analise
- [ ] Permitir filtro por camera.
- [ ] Permitir filtro por periodo.
- [ ] Permitir filtro por round.
- [ ] Exibir tendencia de contagem.
- [ ] Exportar rounds e eventos para CSV.

Objetivo:
- Transformar o sistema em fonte de consulta e nao apenas tela ao vivo.

Entregavel esperado:
- Historico mais exploravel.

### 16. Editor visual de ROI e linha
- [x] Permitir ajustar ROI no proprio Python por arraste.
- [x] Permitir ajustar linha de contagem no proprio Python por arraste.
- [x] Mostrar preview ao vivo na janela OpenCV.
- [x] Persistir as configuracoes em `config.json`.
- [x] Persistir as configuracoes tambem no backend.
- [x] Aplicar configuracoes sem reiniciar a engine.
- [x] Adicionar janela de controle com botoes no executavel Python.

Objetivo:
- Reduzir atrito na calibracao da camera.

Entregavel esperado:
- Configuracao operacional feita direto pela interface.

### 17. Alertas e monitoramento
- [x] Alertar quando o stream cair.
- [x] Alertar quando a contagem ficar zerada por tempo suspeito.
- [x] Alertar quando o backend ficar indisponivel.
- [x] Alertar quando o feed MJPEG nao tiver frames recentes.

Objetivo:
- Detectar falhas cedo.

Entregavel esperado:
- Sistema mais observavel para operacao diaria.

---

## Backlog tecnico complementar

- [ ] Adicionar tipagem melhor no frontend onde fizer sentido.
- [ ] Revisar chunk grande do build do Vite e considerar code splitting.
- [ ] Revisar consumo de CPU do encode JPEG.
- [ ] Avaliar reduzir resolucao ou `imgsz` dinamicamente por camera.
- [ ] Avaliar mover snapshots para armazenamento externo.
- [ ] Criar comando unico de validacao local com build e testes.
- [ ] Testar `imgsz=640` ou maior para melhorar deteccao de veiculos pequenos.
- [ ] Avaliar troca de `yolov8s.pt` para `yolov8m.pt` ou modelo fine-tunado por camera.
- [ ] Ajustar `conf`, `min_hits_to_count` e `min_bbox_area` com base em erros reais da pista.
- [ ] Adicionar thresholds de area por classe (`car`, `motorcycle`, `bus`, `truck`).
- [ ] Adicionar zona morta perto da linha para reduzir dupla contagem por oscilacao do bbox.
- [ ] Avaliar filtros dependentes da posicao vertical/perspectiva da camera.
- [ ] Salvar e revisar casos problematicos de deteccao para calibracao guiada por evidencia.

---

## Ordem recomendada de execucao

### Fase 1 - Limpeza e consolidacao
- [x] Remover HLS legado
- [x] Extrair funcao de anotacao
- [x] Corrigir encoding
- [x] Mover configuracoes para `.env`

### Fase 2 - Confiabilidade
- [x] Testes Python
- [x] Testes backend
- [x] Observabilidade
- [~] Resiliencia do `backend_client.py`

### Fase 3 - Operacao
- [ ] Melhorar `start.bat`
- [x] Melhorar `/health`
- [ ] Medir gargalos de MJPEG em ambiente real

### Fase 4 - Producao
- [x] Servidor MJPEG apropriado
- [x] Persistencia
- [x] Seguranca
- [ ] Estrategia de deploy unificada

### Fase 5 - Produto
- [x] Dashboard operacional
- [ ] Historico avancado
- [x] Editor visual de ROI/linha
- [x] Alertas

---

## Definicao de pronto por fase

### Fase 1 pronta quando
- fluxo antigo removido
- codigo sem duplicacao obvia na anotacao
- configuracao de ambiente sem hardcode principal

### Fase 2 pronta quando
- regras criticas cobertas por teste
- logs suficientes para diagnostico
- engine nao degrada mal quando backend cai

### Fase 3 pronta quando
- subir o sistema localmente estiver previsivel
- health checks derem contexto real

### Fase 4 pronta quando
- reinicio nao apaga dados importantes
- acesso sensivel estiver protegido
- segredos e CORS estiverem separados por ambiente
- publicacao nao depender de ajustes manuais no codigo

### Fase 5 pronta quando
- operacao diaria puder ser feita mais pela interface e menos por ajuste manual
