using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.WebUtilities;

namespace TrafficCounter.Api.Controllers;

[ApiController]
[Route("proxy")]
public class MjpegProxyController : ControllerBase
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly IConfiguration _configuration;

    public MjpegProxyController(
        IHttpClientFactory httpClientFactory,
        IConfiguration configuration
    )
    {
        _httpClientFactory = httpClientFactory;
        _configuration = configuration;
    }

    [HttpGet("video-feed")]
    public async Task VideoFeed(CancellationToken cancellationToken)
    {
        var upstreamUrl = BuildUpstreamUrl("MjpegProxy:UpstreamVideoFeedUrl");
        if (string.IsNullOrWhiteSpace(upstreamUrl))
        {
            Response.StatusCode = 500;
            await Response.WriteAsJsonAsync(
                new { message = "MJPEG upstream URL is not configured." },
                cancellationToken
            );
            return;
        }

        var client = _httpClientFactory.CreateClient();
        using var request = new HttpRequestMessage(HttpMethod.Get, upstreamUrl);
        using var upstreamResponse = await client.SendAsync(
            request,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken
        );

        if (!upstreamResponse.IsSuccessStatusCode)
        {
            Response.StatusCode = (int)upstreamResponse.StatusCode;
            await Response.WriteAsync(
                $"Upstream MJPEG request failed with HTTP {(int)upstreamResponse.StatusCode}.",
                cancellationToken
            );
            return;
        }

        Response.StatusCode = (int)upstreamResponse.StatusCode;
        Response.ContentType = "multipart/x-mixed-replace; boundary=frame";
        Response.Headers.CacheControl = "no-store, no-cache, must-revalidate, max-age=0";
        Response.Headers.Pragma = "no-cache";
        await Response.StartAsync(cancellationToken);

        await using var upstreamStream = await upstreamResponse.Content.ReadAsStreamAsync(cancellationToken);
        var buffer = new byte[16 * 1024];

        while (!cancellationToken.IsCancellationRequested)
        {
            var bytesRead = await upstreamStream.ReadAsync(buffer, cancellationToken);
            if (bytesRead == 0)
                break;

            await Response.Body.WriteAsync(buffer.AsMemory(0, bytesRead), cancellationToken);
            await Response.Body.FlushAsync(cancellationToken);
        }
    }

    [HttpGet("health")]
    public async Task<IActionResult> Health(CancellationToken cancellationToken)
    {
        var upstreamUrl = BuildUpstreamUrl("MjpegProxy:UpstreamHealthUrl");
        if (string.IsNullOrWhiteSpace(upstreamUrl))
            return StatusCode(500, new { message = "MJPEG health upstream URL is not configured." });

        var client = _httpClientFactory.CreateClient();
        using var request = new HttpRequestMessage(HttpMethod.Get, upstreamUrl);
        using var upstreamResponse = await client.SendAsync(request, cancellationToken);
        var content = await upstreamResponse.Content.ReadAsStringAsync(cancellationToken);

        return Content(
            content,
            upstreamResponse.Content.Headers.ContentType?.ToString() ?? "application/json"
        );
    }

    private string BuildUpstreamUrl(string configKey)
    {
        var url = _configuration[configKey] ?? string.Empty;
        var token = _configuration["MjpegProxy:UpstreamToken"];

        if (string.IsNullOrWhiteSpace(url) || string.IsNullOrWhiteSpace(token))
            return url;

        return QueryHelpers.AddQueryString(url, "token", token);
    }
}
