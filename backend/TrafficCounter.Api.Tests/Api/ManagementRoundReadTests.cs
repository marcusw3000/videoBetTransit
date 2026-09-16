using System.Net;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using TrafficCounter.Api.Data;
using TrafficCounter.Api.Domain.Entities;
using TrafficCounter.Api.Tests.Infrastructure;

namespace TrafficCounter.Api.Tests.Api;

public class ManagementRoundReadTests
{
    [Xunit.Fact]
    public async Task Current_round_read_while_editing_does_not_throw_or_create_round()
    {
        await using var factory = new AppWebApplicationFactory();
        using var client = factory.CreateClient();
        using var scope = factory.Services.CreateScope();
        var dbFactory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<AppDbContext>>();
        await using var db = await dbFactory.CreateDbContextAsync();
        var state = await db.PipelineManagementStates.SingleAsync();
        state.IsActive = true;
        state.UpdatedAt = DateTime.UtcNow;
        await db.SaveChangesAsync();

        var response = await client.GetAsync("/rounds/current?cameraId=editing-camera");

        Xunit.Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Xunit.Assert.False(await db.Rounds.AnyAsync(r => r.CameraId == "editing-camera"));
    }
}
