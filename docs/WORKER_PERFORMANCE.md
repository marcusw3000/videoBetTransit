# Worker e vídeo — validação local em 15/09/2026

## Diagnóstico e correções

- A leitura direta HLS entregava rajadas ao slot de último frame, descartando a maioria das imagens e deixando pausas entre segmentos. O FPS instantâneo antigo permanecia alto mesmo com a imagem parada. Houve amostras com quase 9 segundos de imagem antiga no primeiro ensaio e pausas de até 18 segundos durante a investigação.
- Consultas HTTP de rodada/configuração eram síncronas na thread que atende Tk/OpenCV. Agora são single-flight, em segundo plano, com descarte de respostas de outra câmera. Falha de consulta não desativa um modo de gerenciamento já confirmado.
- A inicialização em modo de edição tentava completar a ativação operacional repetidamente. O fluxo de preview não executa esse handshake, e a consulta de rodada no backend deixa de produzir HTTP 500 por tentar criar rodada durante gerenciamento.
- A captura YouTube usa `buffered_hls.py`: fila limitada a três segmentos comprimidos, arquivos temporários removidos após consumo, download separado da decodificação e renovação de URL preservando a próxima sequência. Não armazena o arquivo DVR inteiro nem uma fila de imagens 1080p descomprimidas. Não foram adicionadas dependências.
- RTSP mantém a captura nativa. HLS criptografado, playlists master e formatos com mapa/byte-range retornam ao leitor nativo. `youtube_segment_buffering: false` na configuração do worker permite desligar esse caminho para comparação.
- Os timeouts OpenCV são passados na abertura, não por `set()` depois da conexão. A thread de captura é dona da liberação do decoder, evitando `release()` concorrente com `read()`.
- O publisher usa um único relógio, sem espera dupla que reduzia 15 FPS para aproximadamente 7,5 FPS. Frames publicados podem ser repetidos: não são usados como prova de frames novos.
- Tabelas Tk são atualizadas incrementalmente; a UI continua atendendo eventos enquanto aguarda frames. A imagem antiga recebe aviso de ausência de frames.
- Callbacks do player React permanecem estáveis; atualização de título, contador ou status não reinicia HLS. Quando disponível, HLS.js é preferido à detecção nativa que anunciava suporte mas falhava nessa transmissão. A lista de câmeras não força reconexão SignalR a cada healthcheck. O polling do formulário não sobrescreve entradas locais nem troca silenciosamente sua revisão-base.

## Evidências

Fonte: câmera YouTube já selecionada (`cam_087`), resolução preservada em 1920 × 1080, modelo e parâmetros de contagem inalterados. Modo de gerenciamento mantido no backend.

| Ensaio | Resultado |
| --- | --- |
| Worker integrado, 179 segundos incluindo preparação | 19,84 frames novos/s; três amostras iniciais sem frames; nenhuma depois da preparação; maior idade observada de frame disponível: 165,67 ms |
| Worker já ativo, 59,44 segundos | 22,95 frames novos/s; mínimo 16 e máximo 28 por intervalo de aproximadamente 1 segundo; captura 29,37 FPS; publicação 14,99 FPS |
| Continuidade na segunda janela | Zero amostras sem frames novos, zero desconexões, zero reinícios do publisher; maior idade observada de frame: 98,66 ms |
| Resposta da janela de configuração | 120 mensagens Win32 de verificação, zero timeout de 250 ms, máximo 87,46 ms |
| Player real com stream local, 45 segundos | 14,99 FPS decodificados, nenhuma amostra congelada e nenhum frame descartado pelo navegador; componente real em harness, com callbacks/título atualizados a cada 100 ms |
| Testes Python | 127 aprovados, incluindo I/O lento, single-flight, descarte de câmera antiga, pacing, parâmetros de timeout, posse do decoder, parser HLS, renovação sem replay, limite de download e limpeza do temporário |
| Testes .NET | 118 aprovados, incluindo leitura de rodada durante gerenciamento sem criação nem erro 500 |
| Playwright | 5 aprovados; dois novos testes para estabilidade do decoder e preservação da edição/revisão |
| Frontend | Lint, encoding, build e 3 testes JavaScript aprovados; permanece o aviso não bloqueante de tamanho do chunk HLS |

O teste de resposta Win32 mede atendimento da janela, não cobre todos os cliques e operações de salvar. Os testes automatizados do painel usam APIs controladas. O ensaio de vídeo real foi realizado no componente do frontend com a fonte local, sem usar credenciais da conta administrativa. O buffer foi exercitado também com falhas 403 e renovação da URL na fonte real. Não há garantia de disponibilidade externa, medição homologada de latência ponta a ponta ou aceite de precisão de contagem.

O fluxo canônico `validate.bat` também concluiu com sucesso; saída em `artifacts/validation-worker-performance.log`. A execução Playwright é adicional a esse fluxo.

## Reproduzir

```powershell
.\start.bat
.\.venv\Scripts\python.exe scripts/measure-worker-performance.py --duration 180
.\validate.bat
cd frontend
npm run test:e2e
```

O script de medição lê somente `/health`, compara contadores entre amostras e não imprime URLs assinadas nem credenciais. Executar a validação com um backend que bloqueie a recompilação de sua DLL pode exigir encerrar somente esse backend ou executar os testes .NET em `Release`.

## Limites e continuidade

Três segmentos representam até cerca de 15 segundos de material comprimido nesta fonte de segmentos de 5 segundos. Isso oferece margem para download/renovação, mas não é promessa de latência zero. O atraso real deve ser homologado antes de operação oficial. Uma indisponibilidade longa da origem ainda pode esvaziar o buffer.

O plano geral não foi ampliado: P05 continua dependente da política de retenção e P06 dos aceites em instalação limpa e ambiente operacional. Não houve commit ou push nesta tarefa.

Referência técnica consultada: os timeouts de captura são propriedades de abertura conforme a [documentação do OpenCV](https://docs.opencv.org/4.13.0/d4/d15/group__videoio__flags__base.html).
