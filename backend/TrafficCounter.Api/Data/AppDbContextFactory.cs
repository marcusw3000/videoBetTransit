using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;
using Microsoft.Extensions.Configuration;

namespace TrafficCounter.Api.Data;

public class AppDbContextFactory : IDesignTimeDbContextFactory<AppDbContext>
{
    public AppDbContext CreateDbContext(string[] args)
    {
        var environment = Environment.GetEnvironmentVariable("ASPNETCORE_ENVIRONMENT") ?? "Development";
        var config = new ConfigurationBuilder()
            .SetBasePath(Directory.GetCurrentDirectory())
            .AddJsonFile("appsettings.json", optional: false)
            .AddJsonFile($"appsettings.{environment}.json", optional: true)
            .AddEnvironmentVariables()
            .Build();

        var connString = config.GetConnectionString("DefaultConnection")
            ?? "Data Source=trafficcounter.db";

        var optionsBuilder = new DbContextOptionsBuilder<AppDbContext>();
        if (connString.StartsWith("Data Source", StringComparison.OrdinalIgnoreCase))
            optionsBuilder.UseSqlite(connString);
        else
            optionsBuilder.UseNpgsql(connString);

        return new AppDbContext(optionsBuilder.Options);
    }
}
