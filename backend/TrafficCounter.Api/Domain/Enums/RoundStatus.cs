namespace TrafficCounter.Api.Domain.Enums;

public enum RoundStatus
{
    Open,      // 0–70s: apostas abertas
    Closing,   // 70–180s: apostas fechadas, contagem continua
    Settled,   // round encerrado, resultado final registrado
    Void,      // round anulado
}
