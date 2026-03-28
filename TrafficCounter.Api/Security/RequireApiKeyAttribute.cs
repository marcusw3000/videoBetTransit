using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;

namespace TrafficCounter.Api.Security;

[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method)]
public class RequireApiKeyAttribute : Attribute, IAsyncAuthorizationFilter
{
    private const string HeaderName = "X-API-Key";
    private readonly string _configPath;

    public RequireApiKeyAttribute(string configPath = "Security:BackendApiKey")
    {
        _configPath = configPath;
    }

    public Task OnAuthorizationAsync(AuthorizationFilterContext context)
    {
        var configuration = context.HttpContext.RequestServices.GetRequiredService<IConfiguration>();
        var expectedKey = configuration[_configPath];

        if (string.IsNullOrWhiteSpace(expectedKey))
            return Task.CompletedTask;

        var providedKey = context.HttpContext.Request.Headers[HeaderName].FirstOrDefault();
        if (providedKey == expectedKey)
            return Task.CompletedTask;

        context.Result = new UnauthorizedObjectResult(new { message = "Invalid or missing API key." });
        return Task.CompletedTask;
    }
}
