using Microsoft.AspNetCore.Antiforgery;

namespace TrafficCounter.Api.Security;

public sealed class BrowserCsrfMiddleware(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext context, IAntiforgery antiforgery)
    {
        var path = context.Request.Path;
        // Internal endpoints use worker credentials and never accept cookies as authorization.
        var browserWrite = !HttpMethods.IsGet(context.Request.Method)
            && !HttpMethods.IsHead(context.Request.Method)
            && !HttpMethods.IsOptions(context.Request.Method)
            && (path.StartsWithSegments("/auth") || path.StartsWithSegments("/bets")
                || path.StartsWithSegments("/admin") || path.StartsWithSegments("/streams")
                || path.StartsWithSegments("/rounds/frontend-ready"));
        if (browserWrite)
        {
            try { await antiforgery.ValidateRequestAsync(context); }
            catch (AntiforgeryValidationException)
            {
                context.Response.StatusCode = 400;
                await context.Response.WriteAsJsonAsync(new { error = "Sessao de seguranca expirada. Atualize a pagina." });
                return;
            }
        }
        await next(context);
    }
}
