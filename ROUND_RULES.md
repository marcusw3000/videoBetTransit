# Regras vigentes das rodadas

Versão `normal-v1`, implementada em 14/09/2026. Esta especificação prevalece sobre exemplos históricos de Turbo em `bet.md`, `TODO3.md` e `ROUND_FORMULATION.md`.

## Horários e contagem

O backend cria apenas rodadas **Normal**. Os horários publicados para cada rodada são a referência da interface; o relógio do vídeo não determina o aceite da aposta.

| Marco | Regra | Exemplo com os valores padrão atuais |
| --- | --- | --- |
| Criação | `createdAt` | 12:00:00 |
| Fechamento das apostas | `createdAt + BetWindowSeconds` | 12:00:15 |
| Fim da contagem | `betCloseAt + DurationSeconds` | 12:01:15 |
| Apuração automática | Após `endsAt + SettleDelaySeconds`, no próximo ciclo do gerenciador | A partir de 12:01:17 |
| Próxima rodada | Após o intervalo de descanso e com a câmera pronta | Não antes de 10 segundos após a liquidação |

Os padrões são 15 segundos de aposta, mais 60 segundos até o fim da contagem, 2 segundos de tolerância de entrega na apuração e 10 segundos entre rodadas liquidadas. `DurationSeconds` não é a duração total: neste exemplo a janela total de contagem é de 75 segundos. Configuração por ambiente pode alterar os valores; os horários persistidos e as regras registradas em cada rodada prevalecem.

A contagem oficial aceita ocorrências no intervalo `createdAt <= crossedAt < endsAt`, incluindo a janela inicial de apostas. Uma aposta só é aceita com a rodada aberta e antes de `betCloseAt`. O vídeo pode apresentar atraso.

Estados: `open` → `closing` → `settling` → `settled`. A anulação produz `void`. Durante a apuração, um evento atrasado ainda pode ser aceito se ocorreu na janela original, corresponde à configuração da rodada e ela não foi finalizada. Eventos de rodadas encerradas não migram para a seguinte.

## Mercados

| Tipo da API | Texto apresentado | Condição de vitória | Exemplo |
| --- | --- | --- | --- |
| `under` | Menos de T | Contagem `< T` | Menos de 20 perde com 20 |
| `over` | T ou mais | Contagem `>= T` | 20 ou mais ganha com 20 |
| `range` | Entre A e B | `A <= contagem <= B` | Entre 11 e 20 ganha com 11 e com 20 |
| `exact` | Exatamente T | Contagem `== T` | Exatamente 20 perde com 19 ou 21 |

Cada mercado é avaliado de forma independente; pode haver mais de um vencedor. Os limites e odds vêm do backend e ficam preservados na rodada e na aposta. Os exemplos acima explicam os limites, não impõem um conjunto fixo de mercados. Nomes históricos já persistidos não são reescritos.

## Configuração e integridade

Antes de abrir novas rodadas, o worker registra câmera, perfil, fingerprint da origem, ROI, linha, direção e parâmetros de verificação secundária. O backend gera a versão pelo hash dessa configuração. A URL original, que pode conter credenciais, não entra no snapshot exportado ao admin.

Cada rodada guarda uma cópia imutável da configuração e das regras comerciais e temporais. O evento enviado pelo worker leva a versão usada no momento da contagem. Mudar o perfil seguinte não altera a configuração da rodada anterior; eventos com outra versão são recusados.

Alterações manuais ficam bloqueadas em `open`, `closing` e `settling`. A preparação operacional explícita entre rodadas pode usar `AllowSettling`: permite preparar o próximo perfil durante a apuração, sem alterar o anterior. A ativação e a confirmação de prontidão continuam necessárias. A prévia do editor não altera a geometria usada pela inferência antes do aceite.

`Rounds:RequireOperationalSnapshot` é `true` por padrão. Sem configuração registrada, novas rodadas aguardam o worker. A opção `false` serve à compatibilidade dos testes legados e não deve ser usada para contornar o registro em operação. Rodadas antigas sem snapshot são apresentadas como configuração não registrada; seus dados não são inventados a partir do estado atual.

## Anulação e auditoria

O administrador informa justificativa e um código: `manual_intervention`, `stream_loss`, `backend_failure`, `count_integrity` ou `configuration_change`. Clientes antigos que enviam somente justificativa continuam com o código padrão de intervenção manual. Registros históricos sem código mantêm essa ausência.

A anulação, a atualização das apostas e o evento de auditoria da decisão são gravados na mesma transação. A auditoria registra ator autenticado, alvo, horário, ação, resultado e motivo. Ações vindas da chave interna são identificadas como `worker`; ela não identifica individualmente a pessoa no painel local Python. Tentativas recusadas pela autorização, CSRF e bloqueios de configuração também são registradas, sem copiar corpos de requisição ou segredos.

Consulta de auditoria e configuração detalhada exige administrador. A aplicação impede alteração e exclusão de registros de auditoria; isso não é uma promessa de armazenamento imutável contra um administrador do banco, nem de certificação externa.

## Escopo do produto

As apostas são simuladas, em BRL, entre 0,01 e 10.000,00, com até duas casas decimais. Não há carteira ou movimentação financeira. Turbo, integração de operadoras, calibração do detector e novos mecanismos de monitoramento não fazem parte desta entrega.
