namespace TrafficCounter.Api.Contracts.Inbound;

public class VoidRoundRequest
{
    [System.ComponentModel.DataAnnotations.RegularExpression("^(manual_intervention|stream_loss|backend_failure|count_integrity|configuration_change)$")]
    public string ReasonCode { get; set; } = "manual_intervention";
    [System.ComponentModel.DataAnnotations.Required]
    [System.ComponentModel.DataAnnotations.StringLength(512)]
    public string Reason { get; set; } = string.Empty;
}
