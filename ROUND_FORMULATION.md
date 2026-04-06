# Formulacao da Criacao de Rounds

## Objetivo

Definir como um `round` deve nascer, evoluir e encerrar no `videoBetTransit`, agora que a contagem oficial deve vir do backend.

## Principio Central

- o `vision-worker` detecta cruzamentos
- o backend persiste eventos e calcula a contagem oficial
- o frontend comercial exibe o `round.currentCount` do backend
- o total do Python existe apenas como telemetria operacional

## Fonte de Verdade

A criacao e o lifecycle do round devem ser responsabilidade exclusiva do backend.

Isso significa:

- o Python nao cria round
- o frontend nao cria round
- o `RoundService` cria, fecha, liquida e anula rounds

## Quando Criar um Round

Um novo round deve ser criado em apenas tres situacoes:

1. na inicializacao do backend, se nao existir round ativo
2. imediatamente apos um round ir para `settled`
3. imediatamente apos um round ir para `void`

Regra:

- deve existir no maximo um round ativo por camera ou mesa logica

## Estados Oficiais

O round deve seguir este lifecycle:

1. `open`
2. `closing`
3. `settling`
4. `settled`

Estado excepcional:

1. `void`

Sem estados paralelos no frontend.

## Estrutura Minima do Round

Cada round deve nascer com:

- `round_id`
- `display_name`
- `status = open`
- `created_at`
- `bet_close_at`
- `ends_at`
- `current_count = 0`
- `final_count = null`
- `markets`
- `camera_id`
- `stream_profile_snapshot`
- `roi_snapshot`
- `count_line_snapshot`
- `count_direction_snapshot`

Os snapshots acima devem ser congelados no momento da criacao.

## Regra de Tempo Recomendada

Para `Rodada Turbo`:

- `created_at = agora`
- `bet_close_at = created_at + 70s`
- `ends_at = created_at + 180s`

Regra:

- apostas fecham antes do fim do round
- a contagem continua ate `ends_at`
- settlement acontece depois de `ends_at`

## Regra de Contagem

Todo veiculo contado pelo worker deve virar um `crossing_event` no backend.

Fluxo ideal:

1. worker detecta cruzamento
2. worker envia `crossing-event`
3. backend valida integridade e idempotencia
4. backend persiste `crossing_event`
5. backend localiza o round ativo da camera
6. backend incrementa `round.currentCount`
7. backend publica `count_updated`
8. frontend atualiza a UI com a contagem oficial

## Regra de Vinculo

O evento deve ser associado ao round ativo pelo backend.

Ou seja:

- o worker pode enviar `camera_id`
- o backend decide qual `round_id` esta ativo para aquela camera
- o `round_id` nao deve ser decidido pelo frontend

## Regra de Idempotencia

Cada `crossing_event` precisa de chave de deduplicacao.

Sugestao:

- `camera_id`
- `track_id`
- `frame_number`
- `timestamp_utc`
- `event_hash`

Com isso:

- retries nao podem duplicar a contagem
- o round nao pode subir duas vezes para o mesmo cruzamento

## Regra de Freeze

Durante `open`, `closing` e `settling`, deve ficar congelado:

- stream profile
- ROI
- count line
- count direction
- mercados
- odds

Esses dados devem ser snapshottados no round no momento da criacao.

## Criacao de Mercados

Os mercados devem ser gerados no nascimento do round a partir da configuracao comercial da camera.

Exemplo `v1`:

- `under`
- `range`
- `over`
- `exact`

Cada mercado nasce com:

- `market_id`
- `round_id`
- `market_type`
- `label`
- `odds`
- `threshold/min/max/target`
- `sort_order`
- `is_winner = null`

## Settlement

Quando `ends_at` chegar:

1. round vai para `settling`
2. `final_count = current_count`
3. backend avalia mercados vencedores
4. round vai para `settled`
5. backend publica `round_settled`
6. backend cria o proximo round

## Void

Um round deve poder virar `void` quando houver:

- perda de stream
- drift grave
- falha de backend
- alteracao operacional indevida
- contagem suspeita
- incidente formal

Ao virar `void`:

- `void_reason` deve ser obrigatorio
- mercados ficam sem vencedor
- backend cria o proximo round

## Regra de Frontend

Frontend comercial deve exibir:

- `total oficial da rodada = round.currentCount`
- status do round
- timer do round
- mercados do round

Frontend nao deve usar o contador do Python como numero oficial do produto.

O contador do Python deve ficar somente em:

- painel operacional
- health
- debug
- comparacao tecnica

## Regra de Escalabilidade

Se o produto operar com mais de uma camera, a formulacao deve ser:

- um round ativo por camera
- eventos vinculados por `camera_id`
- configuracao comercial e operacional por camera

Nao deve existir round global compartilhado entre cameras diferentes.

## Modelo Recomendado de Criacao

Servico central:

- `RoundService.CreateRoundForCameraAsync(cameraId)`

Entradas:

- `camera_id`
- configuracao comercial da camera
- configuracao operacional congelada

Saida:

- round persistido com mercados e snapshots

## Formula Final

Round e uma janela temporal oficial criada pelo backend, associada a uma camera, com configuracao congelada, mercados fixados no nascimento, contagem alimentada exclusivamente por `crossing_events` aceitos pelo backend e settlement determinado pelo `round engine`.

## Proxima Implementacao Recomendada

1. adicionar `camera_id` em `Round`
2. criar snapshots operacionais no `Round`
3. vincular `crossing_events` ao round ativo por camera
4. eliminar dependencia do contador do Python na UI comercial
5. fazer o frontend ler apenas `round.currentCount`
6. separar painel comercial de painel operacional
