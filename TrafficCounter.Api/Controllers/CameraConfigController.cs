using Microsoft.AspNetCore.Mvc;
using TrafficCounter.Api.Models;
using TrafficCounter.Api.Security;
using TrafficCounter.Api.Services;

namespace TrafficCounter.Api.Controllers;

[ApiController]
[Route("api/camera-config")]
[RequireApiKey]
public class CameraConfigController : ControllerBase
{
    private readonly CameraConfigService _configService;

    public CameraConfigController(CameraConfigService configService)
    {
        _configService = configService;
    }

    [HttpGet("{cameraId}")]
    public IActionResult GetConfig(string cameraId)
    {
        var config = _configService.GetConfig(cameraId);
        if (config == null)
            return NotFound(new { message = $"Config not found for camera '{cameraId}'." });
        return Ok(config);
    }

    [HttpPost("{cameraId}")]
    public IActionResult SaveConfig(string cameraId, [FromBody] CameraConfigDto config)
    {
        config.CameraId = cameraId;
        var saved = _configService.SaveConfig(config);
        return Ok(saved);
    }

    [HttpGet]
    public IActionResult GetAll()
    {
        return Ok(_configService.GetAll());
    }
}
