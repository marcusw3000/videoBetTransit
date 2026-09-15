# VideoBetTransit

Demonstracao de rodadas baseadas em contagem de veiculos. As apostas registradas sao simuladas; nao existe carteira, deposito, saque ou movimentacao financeira.

## Instalar e iniciar no Windows

Requisitos: .NET 8 SDK, Node 22, Python 3.12, FFmpeg e MediaMTX. Os launchers oficiais usam `backend/TrafficCounter.Api`, `frontend/` e `vision-worker/`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r vision-worker/requirements.txt
npm ci --prefix frontend
.\scripts\configure-local.ps1 -Username admin -Role admin
.\scripts\configure-local.ps1 -Username jogador -Role player
.\start-dev.bat
```

O configurador pede a senha com entrada oculta, grava somente seu hash e sincroniza uma chave aleatoria entre backend e worker. Ele preserva as cameras e os demais ajustes locais existentes. Execute com o worker parado para evitar escrita concorrente no arquivo de configuracao. Cadastre a origem e calibre uma camera no painel Python ao configurar uma instalacao nova.

Acesse `http://127.0.0.1:5173`. `/admin` requer uma conta administrativa. Repita o configurador para trocar a senha; sessoes antigas dessa conta serao invalidadas. Chaves de ambiente prevalecem sobre os arquivos locais. O nome de usuario e a identidade estavel: nao reutilize nomes de contas removidas para outra pessoa.

## Validar

```powershell
.\validate.bat
npm exec --prefix frontend -- playwright install chromium
npm run test:e2e --prefix frontend
```

A validacao executa testes Python, API (incluindo banco SQLite real), testes JavaScript, lint, verificacao UTF-8 e build. Os testes de navegador usam respostas controladas da API para verificar login, permissoes da interface, repeticao de tentativa e historico. A integracao real de autenticação e banco e coberta pelos testes .NET. Esses testes nao medem a precisao do modelo ou a qualidade de uma transmissao real.

## Dados e recuperacao

- Backend: banco SQLite local por padrao. As migracoes sao aplicadas na inicializacao, incluindo compatibilidade com colunas criadas pelo reparo legado. Antes de atualizar uma instalacao, mantenha backup consistente do banco.
- Worker: fila persistente em `vision-worker/data/events.sqlite3`; `EVENT_OUTBOX_PATH` altera o caminho. Preserve esse arquivo entre reinicios e monte um volume em containers.
- A entrega conserva o identificador ate receber `{ "received": true }`. Falhas temporarias sao reenviadas na ordem, com espera progressiva. Um processo interrompido pode deixar uma reserva de ate 30 segundos antes da retomada.
- Eventos recebidos apos o fim podem ser aceitos durante a apuracao se ocorreram dentro da janela original. Eventos de rodadas ja liquidadas/anuladas, ou de outra camera, sao rejeitados e preservados na fila para revisao. Nunca migram para a rodada seguinte.
- Rejeicoes ficam na tabela `outbox`, com `rejected=1`. Consulte com `python scripts/review-outbox.py --status rejected` ou `--json`; o diagnóstico e somente leitura e nao exibe payloads. Nao altere timestamps, IDs ou rodadas para forcar aceitação.
- Falhas de rede, timeout, 429 e 5xx permanecem pendentes e sao repetidas pelo worker com o mesmo `eventHash`. Erros 400, 409, 410 e 422 tornam o evento rejeitado definitivamente. Para encerrar uma rejeicao, um admin registra `acknowledged`, `investigating` ou `closed` em `POST /admin/recovery-events/{eventId}/decision`, com codigo de motivo; a decisao e auditada e nao reenvia, altera ou reassocia o evento.
- Rodada, mercados, apostas e eventos de encerramento sao gravados juntos. O gerenciador reconcilia apostas antigas ainda pendentes em rodadas finalizadas. Notificacoes SignalR podem ser recuperadas pelas consultas REST periodicas.
- Logs, backups, configuracoes locais e publicacoes foram retirados do versionamento, mantendo suas copias locais. `traffic-counter-front/` e referencia legada; nao e usado pelos launchers ou pela validacao.

## Evidências por rodada e retenção

Para uma rodada `settled` ou `void`, um admin pode obter `GET /admin/rounds/{id}/evidence` (JSON versionado) ou `GET /admin/rounds/{id}/evidence.csv` (timeline e crossings). A exportação é somente leitura: não recalcula resultados, não reenvia eventos e não inclui apostas, contas, motivos livres, identidades de atores, URLs de origem, chaves ou payloads do worker. A imagem é referenciada pelo identificador seguro do crossing, sem copiar seu caminho ou URL. Imagens locais são classificadas como `available` ou `missing`; referências externas ficam como `external_unverified`; a ausência histórica aparece como `not_recorded`.

Ainda não há remoção automática de imagens ou evidências. Antes de habilitá-la, definir prazo de retenção separado para banco e imagens, limite de armazenamento, local de backup e procedimento que preserve o pacote e registre `removed_by_retention` ou `unavailable` em vez de ocultar a ausência. A exportação de evidências não é replay de vídeo nem reprocessamento do detector.

## Instalação, backup e restauração local

Depois de instalar dependências e executar `scripts/configure-local.ps1` para ao menos uma conta admin, valide a instalação sem expor segredos com:

```powershell
.\scripts\Test-LocalInstallation.ps1
```

O backend não inicia para servir HTTP sem uma chave interna diferente de `CHANGE_ME` e uma conta admin válida. Após iniciar os serviços, `-CheckRunning` também verifica API e worker. Em uma instalação restaurada, use `-RequireExistingDataProtectionKeys` para confirmar que as chaves de sessão foram preservadas.

Pare backend e worker antes do backup para congelar configurações e imagens. Os bancos SQLite são copiados pela API de backup, incluindo transações confirmadas no WAL, e passam por `quick_check`. Os caminhos efetivos vêm da conexão local, de `EVENT_OUTBOX_PATH`, de `DataProtection:KeyPath` e de `snapshot_dir`; caminhos externos ao projeto são recusados para manter a restauração portável. O backup inclui configurações locais e chaves de Data Protection; snapshots são opcionais:

```powershell
.\scripts\Backup-VideoBetTransit.ps1 -Destination C:\Backups\VideoBetTransit -ConfirmStopped
.\scripts\Backup-VideoBetTransit.ps1 -Destination C:\Backups\VideoBetTransit -IncludeSnapshots -ConfirmStopped
```

Restaure somente em uma cópia separada e parada do projeto. O script confere tamanho, hash e confinamento de cada caminho antes de gravar qualquer arquivo, recusa links/junctions e exige confirmação explícita:

```powershell
.\scripts\Restore-VideoBetTransit.ps1 -BackupPath C:\Backups\VideoBetTransit\videobet-backup-AAAAmmdd-HHmmss-fff -TargetRoot C:\ambientes\videoBetTransit -ConfirmOverwrite
```

Esses procedimentos são locais. HTTPS, proxy, persistência de volumes em produção, escolha de VPS/container/IIS, PostgreSQL e handshake com câmera real ainda exigem um ambiente de homologação definido.

## Acesso e publicacao

O browser usa cookie HttpOnly e token antifalsificacao; o worker usa `X-API-Key`, sem permissao de jogador ou administrador. Campos de identidade enviados pelo frontend nao concedem acesso. Consultas de apostas sao sempre limitadas a conta e operador autenticados. Registros antigos sem identidade confiavel permanecem no banco, sem atribuicao automatica a novas contas.

Em producao use HTTPS, origens CORS explicitas e armazenamento persistente das chaves de Data Protection (`DataProtection__KeyPath`). Publique frontend e API sob o mesmo site, preferencialmente com proxy reverso. Cookies SameSite=Lax nao suportam autenticacao em iframes de outro site; uma integracao com operador externo precisa de um fluxo de identidade e hospedagem apropriado. Nenhuma credencial `VITE_*` deve ser administrativa.

O aceite de apostas demonstra valores BRL entre 0,01 e 10.000,00 com ate duas casas decimais. Esses limites nao representam saldo ou credito. A mesma chave de transacao, conta e operador so pode ser repetida com o mesmo conteudo. Respostas 503 devem ser repetidas com o mesmo identificador.

## Estrutura do worker

`app.py` coordena o processo e mantem os nomes exportados por compatibilidade. Captura (`stream_capture`), publicacao (`video_publisher`), configuracao (`worker_config`), agenda (`stream_schedule`), calibracao (`calibration_editor`), geometria (`count_geometry`), desenho (`frame_overlay`), estatisticas (`runtime_stats`) e entrega (`event_outbox`) ficam em modulos separados. A extracao preservou as regras de contagem existentes.

## Regras e auditoria das rodadas

Consulte [ROUND_RULES.md](ROUND_RULES.md) para horários, mercados, configuração congelada e anulação. O painel administrativo exibe snapshots e auditoria; anular exige código de motivo e justificativa. Dados antigos sem snapshot aparecem como não registrados.

A atualização inclui a migração `FreezeRoundConfigurationAndAudit`. Atualize backend e worker juntos: novas rodadas aguardam o registro da configuração operacional, e os eventos carregam sua versão. Preserve a outbox no upgrade. Eventos antigos sem versão de rodadas sem snapshot continuam sujeitos à janela original; não atribua a eles a versão atual para forçar aceite. Reinicie a esteira conforme o procedimento local após aplicar a atualização. Não é necessário alterar parâmetros do detector.
