using Microsoft.EntityFrameworkCore;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Models;

namespace TrafficCounter.Api.Services;

public class CameraConfigService
{
    private readonly IDbContextFactory<TrafficCounterDbContext> _dbContextFactory;

    public CameraConfigService(IDbContextFactory<TrafficCounterDbContext> dbContextFactory)
    {
        _dbContextFactory = dbContextFactory;
    }

    public CameraConfigDto? GetConfig(string cameraId)
    {
        using var db = _dbContextFactory.CreateDbContext();
        var config = db.CameraConfigs
            .AsNoTracking()
            .SingleOrDefault(x => x.CameraId == cameraId);

        return config is null ? null : ToDto(config);
    }

    public CameraConfigDto SaveConfig(CameraConfigDto config)
    {
        using var db = _dbContextFactory.CreateDbContext();
        var entity = db.CameraConfigs.SingleOrDefault(x => x.CameraId == config.CameraId);

        if (entity is null)
        {
            entity = new CameraConfig { CameraId = config.CameraId };
            db.CameraConfigs.Add(entity);
        }

        entity.RoiX = config.Roi.X;
        entity.RoiY = config.Roi.Y;
        entity.RoiW = config.Roi.W;
        entity.RoiH = config.Roi.H;
        entity.CountLineX1 = config.CountLine.X1;
        entity.CountLineY1 = config.CountLine.Y1;
        entity.CountLineX2 = config.CountLine.X2;
        entity.CountLineY2 = config.CountLine.Y2;
        entity.CountDirection = config.CountDirection;

        db.SaveChanges();
        return ToDto(entity);
    }

    public List<CameraConfigDto> GetAll()
    {
        using var db = _dbContextFactory.CreateDbContext();
        return db.CameraConfigs
            .AsNoTracking()
            .OrderBy(x => x.CameraId)
            .Select(ToDto)
            .ToList();
    }

    private static CameraConfigDto ToDto(CameraConfig config)
    {
        return new CameraConfigDto
        {
            CameraId = config.CameraId,
            Roi = new RoiDto
            {
                X = config.RoiX,
                Y = config.RoiY,
                W = config.RoiW,
                H = config.RoiH,
            },
            CountLine = new CountLineDto
            {
                X1 = config.CountLineX1,
                Y1 = config.CountLineY1,
                X2 = config.CountLineX2,
                Y2 = config.CountLineY2,
            },
            CountDirection = config.CountDirection,
        };
    }
}
