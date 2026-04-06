namespace TrafficCounter.Api.Domain.Entities;

public class RoundMarket
{
    public Guid MarketId { get; set; }
    public Guid RoundId { get; set; }
    public Round Round { get; set; } = null!;

    /// <summary>"under" | "over" | "range" | "exact"</summary>
    public string MarketType { get; set; } = string.Empty;
    public string Label { get; set; } = string.Empty;
    public decimal Odds { get; set; }

    /// <summary>Limite para under/over.</summary>
    public int? Threshold { get; set; }

    /// <summary>Limites inferiores e superiores para range.</summary>
    public int? Min { get; set; }
    public int? Max { get; set; }

    /// <summary>Valor alvo para exact.</summary>
    public int? TargetValue { get; set; }

    /// <summary>null enquanto aberto, true/false após encerrado.</summary>
    public bool? IsWinner { get; set; }

    /// <summary>Preserva a ordem de exibição definida na config.</summary>
    public int SortOrder { get; set; }
}
