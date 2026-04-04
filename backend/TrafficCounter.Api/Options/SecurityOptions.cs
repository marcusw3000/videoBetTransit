namespace TrafficCounter.Api.Options;

public class SecurityOptions
{
    public string BackendApiKey { get; set; } = "CHANGE_ME";
    public bool EnforceHashChain { get; set; } = false;
}
