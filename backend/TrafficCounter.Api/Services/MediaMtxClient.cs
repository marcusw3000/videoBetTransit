using System.Net.Http.Json;
using Microsoft.Extensions.Options;
using TrafficCounter.Api.Options;

namespace TrafficCounter.Api.Services;

public interface IMediaMtxClient
{
    Task<bool> AddPathAsync(string pathName, string sourceUrl, CancellationToken ct = default);
    Task<bool> RemovePathAsync(string pathName, CancellationToken ct = default);
    Task<bool> PathExistsAsync(string pathName, CancellationToken ct = default);
}

public class MediaMtxClient : IMediaMtxClient
{
    private readonly HttpClient _http;
    private readonly MediaMtxOptions _options;
    private readonly ILogger<MediaMtxClient> _logger;

    public MediaMtxClient(HttpClient http, IOptions<MediaMtxOptions> options, ILogger<MediaMtxClient> logger)
    {
        _http = http;
        _options = options.Value;
        _http.BaseAddress = new Uri(_options.ApiBaseUrl);
        _logger = logger;
    }

    public async Task<bool> AddPathAsync(string pathName, string sourceUrl, CancellationToken ct = default)
    {
        try
        {
            var body = new { source = sourceUrl };
            var response = await _http.PostAsJsonAsync($"/v3/config/paths/add/{pathName}", body, ct);
            return response.IsSuccessStatusCode;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to add MediaMTX path '{Path}'", pathName);
            return false;
        }
    }

    public async Task<bool> RemovePathAsync(string pathName, CancellationToken ct = default)
    {
        try
        {
            var response = await _http.DeleteAsync($"/v3/config/paths/remove/{pathName}", ct);
            return response.IsSuccessStatusCode;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to remove MediaMTX path '{Path}'", pathName);
            return false;
        }
    }

    public async Task<bool> PathExistsAsync(string pathName, CancellationToken ct = default)
    {
        try
        {
            var response = await _http.GetAsync($"/v3/paths/get/{pathName}", ct);
            return response.IsSuccessStatusCode;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Could not check MediaMTX path '{Path}'", pathName);
            return false;
        }
    }
}
