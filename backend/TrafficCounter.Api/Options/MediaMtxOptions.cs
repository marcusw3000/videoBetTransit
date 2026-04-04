namespace TrafficCounter.Api.Options;

public class MediaMtxOptions
{
    public string ApiBaseUrl { get; set; } = "http://mediamtx:9997";
    public string RtspBaseUrl { get; set; } = "rtsp://mediamtx:8554";
}
