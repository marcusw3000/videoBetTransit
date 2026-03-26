using TrafficCounter.Api.Models;

namespace TrafficCounter.Api.Services;

public class CameraConfigService
{
    private readonly Dictionary<string, CameraConfigDto> _configs = new();

    public CameraConfigDto? GetConfig(string cameraId)
    {
        return _configs.TryGetValue(cameraId, out var config) ? config : null;
    }

    public CameraConfigDto SaveConfig(CameraConfigDto config)
    {
        _configs[config.CameraId] = config;
        return config;
    }

    public List<CameraConfigDto> GetAll()
    {
        return _configs.Values.ToList();
    }
}
