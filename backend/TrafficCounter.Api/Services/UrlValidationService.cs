namespace TrafficCounter.Api.Services;

public class UrlValidationResult
{
    public bool IsValid { get; private set; }
    public string? ErrorMessage { get; private set; }

    public static UrlValidationResult Ok() => new() { IsValid = true };
    public static UrlValidationResult Fail(string message) => new() { IsValid = false, ErrorMessage = message };
}

public class UrlValidationService
{
    private static readonly HashSet<string> ValidSchemes = new(StringComparer.OrdinalIgnoreCase)
    {
        "rtsp", "rtmp", "srt", "http", "https"
    };

    private static readonly HashSet<string> ValidExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".m3u8", ".ts", ".mp4"
    };

    private static readonly string[] StreamPathHints = { "/stream", "/live", "/hls", "/rtsp", "/video" };

    public Task<UrlValidationResult> ValidateAsync(string url, string protocol)
    {
        if (string.IsNullOrWhiteSpace(url))
            return Task.FromResult(UrlValidationResult.Fail("URL cannot be empty."));

        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri))
            return Task.FromResult(UrlValidationResult.Fail("URL is not a valid absolute URI."));

        var scheme = uri.Scheme.ToLowerInvariant();

        if (!ValidSchemes.Contains(scheme))
            return Task.FromResult(UrlValidationResult.Fail($"Unsupported scheme '{scheme}'. Accepted: rtsp, rtmp, srt, http, https."));

        // Non-HTTP schemes are always accepted (RTSP, RTMP, SRT)
        if (scheme is not "http" and not "https")
            return Task.FromResult(UrlValidationResult.Ok());

        // For HTTP/HTTPS: must look like a media URL, not a web page
        var path = uri.AbsolutePath;
        var ext = Path.GetExtension(path);

        if (ValidExtensions.Contains(ext))
            return Task.FromResult(UrlValidationResult.Ok());

        if (StreamPathHints.Any(hint => path.Contains(hint, StringComparison.OrdinalIgnoreCase)))
            return Task.FromResult(UrlValidationResult.Ok());

        return Task.FromResult(UrlValidationResult.Fail(
            "HTTP/HTTPS URLs must point to a media stream (e.g. .m3u8, .mp4) or a known stream path. " +
            "Web page URLs are not accepted."));
    }
}
