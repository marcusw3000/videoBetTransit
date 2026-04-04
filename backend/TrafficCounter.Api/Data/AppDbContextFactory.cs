using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace TrafficCounter.Api.Data;

public class AppDbContextFactory : IDesignTimeDbContextFactory<AppDbContext>
{
    public AppDbContext CreateDbContext(string[] args)
    {
        var connString = Environment.GetEnvironmentVariable("ConnectionStrings__DefaultConnection")
            ?? "Host=localhost;Port=5432;Database=trafficcounter_dev;Username=tc;Password=tc";

        var options = new DbContextOptionsBuilder<AppDbContext>()
            .UseNpgsql(connString)
            .Options;

        return new AppDbContext(options);
    }
}
