using System.Text;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.WebUtilities;

namespace TrafficCounter.Api.Controllers;

[ApiController]
[Route("proxy/hls")]
public class HlsProxyController : ControllerBase
{
    private static readonly Regex TagUriRegex = new(
        "URI=\"(?<uri>[^\"]+)\"",
        RegexOptions.Compiled | RegexOptions.IgnoreCase
    );

    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IConfiguration _configuration;

    public HlsProxyController(
        IHttpClientFactory httpClientFactory,
        IConfiguration configuration
    )
    {
        _httpClientFactory = httpClientFactory;
        _configuration = configuration;
    }

    [HttpGet("manifest")]
    public async Task<IActionResult> Manifest(CancellationToken cancellationToken)
    {
        var upstreamUrl = _configuration["HlsProxy:UpstreamManifestUrl"] ?? string.Empty;
        if (string.IsNullOrWhiteSpace(upstreamUrl))
            return StatusCode(500, new { message = "HLS upstream manifest URL is not configured." });

        var upstreamUri = new Uri(upstreamUrl, UriKind.Absolute);
        var client = _httpClientFactory.CreateClient();
        using var request = new HttpRequestMessage(HttpMethod.Get, upstreamUri);
        using var upstreamResponse = await client.SendAsync(request, cancellationToken);

        if (!upstreamResponse.IsSuccessStatusCode)
        {
            return StatusCode(
                (int)upstreamResponse.StatusCode,
                new { message = $"Upstream HLS manifest request failed with HTTP {(int)upstreamResponse.StatusCode}." }
            );
        }

        var manifest = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);
        var rewrittenManifest = RewritePlaylist(manifest, upstreamUri);
        return Content(rewrittenManifest, "application/vnd.apple.mpegurl", Encoding.UTF8);
    }

    [HttpGet("media")]
    public async Task Media([FromQuery] string url, CancellationToken cancellationToken)
    {
        if (!TryValidateUpstreamMediaUrl(url, out var mediaUri))
        {
            Response.StatusCode = 400;
            await Response.WriteAsJsonAsync(
                new { message = "Invalid or unauthorized HLS media URL." },
                cancellationToken
            );
            return;
        }

        var client = _httpClientFactory.CreateClient();
        using var request = new HttpRequestMessage(HttpMethod.Get, mediaUri);

        if (Request.Headers.Range.Count > 0)
            request.Headers.TryAddWithoutValidation("Range", Request.Headers.Range.ToString());

        using var upstreamResponse = await client.SendAsync(
            request,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken
        );

        if (!upstreamResponse.IsSuccessStatusCode && upstreamResponse.StatusCode != System.Net.HttpStatusCode.PartialContent)
        {
            Response.StatusCode = (int)upstreamResponse.StatusCode;
            await Response.WriteAsync(
                $"Upstream HLS media request failed with HTTP {(int)upstreamResponse.StatusCode}.",
                cancellationToken
            );
            return;
        }

        Response.StatusCode = (int)upstreamResponse.StatusCode;
        Response.ContentType = upstreamResponse.Content.Headers.ContentType?.ToString()
            ?? "application/octet-stream";

        foreach (var header in upstreamResponse.Headers)
            Response.Headers[header.Key] = header.Value.ToArray();

        foreach (var header in upstreamResponse.Content.Headers)
            Response.Headers[header.Key] = header.Value.ToArray();

        Response.Headers.CacheControl = "no-store, no-cache, must-revalidate, max-age=0";
        await Response.StartAsync(cancellationToken);

        await using var upstreamStream = await upstreamResponse.Content.ReadAsStreamAsync(cancellationToken);
        await upstreamStream.CopyToAsync(Response.Body, cancellationToken);
        await Response.Body.FlushAsync(cancellationToken);
    }

    private string RewritePlaylist(string playlist, Uri manifestUri)
    {
        var output = new StringBuilder();
        using var reader = new StringReader(playlist);

        while (reader.ReadLine() is { } line)
        {
            if (line.StartsWith("#"))
            {
                output.AppendLine(RewriteTaggedUri(line, manifestUri));
                continue;
            }

            if (string.IsNullOrWhiteSpace(line))
            {
                output.AppendLine();
                continue;
            }

            output.AppendLine(BuildMediaProxyUrl(new Uri(manifestUri, line.Trim())));
        }

        return output.ToString();
    }

    private string RewriteTaggedUri(string line, Uri manifestUri)
    {
        return TagUriRegex.Replace(
            line,
            match =>
            {
                var rawUri = match.Groups["uri"].Value;
                var absoluteUri = new Uri(manifestUri, rawUri);
                return $"URI=\"{BuildMediaProxyUrl(absoluteUri)}\"";
            }
        );
    }

    private string BuildMediaProxyUrl(Uri mediaUri)
    {
        var proxyBase = $"{Request.Scheme}://{Request.Host}/proxy/hls/media";
        return QueryHelpers.AddQueryString(proxyBase, "url", mediaUri.ToString());
    }

    private bool TryValidateUpstreamMediaUrl(string rawUrl, out Uri mediaUri)
    {
        mediaUri = new Uri("http://localhost");
        if (
            string.IsNullOrWhiteSpace(rawUrl)
            || !Uri.TryCreate(rawUrl, UriKind.Absolute, out var parsedMediaUri)
        )
            return false;

        mediaUri = parsedMediaUri;

        var upstreamManifestUrl = _configuration["HlsProxy:UpstreamManifestUrl"] ?? string.Empty;
        if (!Uri.TryCreate(upstreamManifestUrl, UriKind.Absolute, out var upstreamManifestUri))
            return false;

        return string.Equals(mediaUri.Scheme, upstreamManifestUri.Scheme, StringComparison.OrdinalIgnoreCase)
            && string.Equals(mediaUri.Host, upstreamManifestUri.Host, StringComparison.OrdinalIgnoreCase)
            && mediaUri.Port == upstreamManifestUri.Port;
    }
}
