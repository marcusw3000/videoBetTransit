namespace TrafficCounter.Api.Contracts.Requests;

public class CreateStreamRequest
{
    public string Name { get; set; } = string.Empty;
    public string CameraId { get; set; } = string.Empty;
    public string SourceUrl { get; set; } = string.Empty;
    public string SourceProtocol { get; set; } = "rtsp";
    public CountLineRequest CountLine { get; set; } = new();
    public string Direction { get; set; } = "down_to_up";
}

public class CountLineRequest
{
    public int X1 { get; set; }
    public int Y1 { get; set; }
    public int X2 { get; set; }
    public int Y2 { get; set; }
}
