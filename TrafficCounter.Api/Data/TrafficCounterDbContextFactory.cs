using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace TrafficCounter.Api.Data;

public class TrafficCounterDbContextFactory : IDesignTimeDbContextFactory<TrafficCounterDbContext>
{
    public TrafficCounterDbContext CreateDbContext(string[] args)
    {
        var optionsBuilder = new DbContextOptionsBuilder<TrafficCounterDbContext>();
        optionsBuilder.UseSqlite("Data Source=trafficcounter.db");
        return new TrafficCounterDbContext(optionsBuilder.Options);
    }
}
