using TrafficCounter.Api.Services;
using Xunit;

namespace TrafficCounter.Api.Tests.Services;

public class UrlValidationServiceTests
{
    private readonly UrlValidationService _svc = new();

    [Theory]
    [InlineData("rtsp://192.168.1.1:554/stream", "rtsp")]
    [InlineData("rtmp://live.example.com/app/key", "rtmp")]
    [InlineData("srt://192.168.1.1:9000", "srt")]
    [InlineData("https://cdn.example.com/hls/stream.m3u8", "hls")]
    [InlineData("http://192.168.1.1:8080/stream", "hls")]
    public async Task Valid_media_urls_pass(string url, string protocol)
    {
        var result = await _svc.ValidateAsync(url, protocol);
        Assert.True(result.IsValid, result.ErrorMessage);
    }

    [Theory]
    [InlineData("https://www.youtube.com/watch?v=abc", "hls")]
    [InlineData("https://example.com/index.html", "hls")]
    public async Task Web_page_urls_are_rejected(string url, string protocol)
    {
        var result = await _svc.ValidateAsync(url, protocol);
        Assert.False(result.IsValid);
    }

    [Fact]
    public async Task Empty_url_is_rejected()
    {
        var result = await _svc.ValidateAsync("", "rtsp");
        Assert.False(result.IsValid);
    }

    [Fact]
    public async Task Invalid_scheme_is_rejected()
    {
        var result = await _svc.ValidateAsync("ftp://example.com/file.ts", "rtsp");
        Assert.False(result.IsValid);
    }
}
