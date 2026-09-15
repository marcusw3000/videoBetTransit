using System.ComponentModel.DataAnnotations;
using System.Security.Claims;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using TrafficCounter.Api.Security;

namespace TrafficCounter.Api.Controllers;

[ApiController, Route("auth")]
public class AuthController(AccountStore accounts, IAntiforgery antiforgery) : ControllerBase
{
    [HttpGet("csrf")]
    public IActionResult Csrf()
    {
        Response.Headers.CacheControl = "no-store";
        return Ok(new { token = antiforgery.GetAndStoreTokens(HttpContext).RequestToken });
    }

    [HttpPost("login"), EnableRateLimiting("login")]
    public async Task<IActionResult> Login(LoginRequest request)
    {
        var account = accounts.Authenticate(request.Username.Trim(), request.Password);
        if (account is null) return Unauthorized(new { error = "Usuario ou senha invalidos." });
        var claims = new[] {
            new Claim(ClaimTypes.NameIdentifier, account.Username),
            new Claim(ClaimTypes.Name, account.Username),
            new Claim(ClaimTypes.Role, account.Role),
            new Claim("operator", account.OperatorRef),
            new Claim("credential_version", account.CredentialVersion),
        };
        await HttpContext.SignInAsync(CookieAuthenticationDefaults.AuthenticationScheme,
            new ClaimsPrincipal(new ClaimsIdentity(claims, CookieAuthenticationDefaults.AuthenticationScheme)));
        return Ok(new { username = account.Username, role = account.Role, mode = "demo" });
    }

    [Authorize, HttpGet("me")]
    public IActionResult Me() => Ok(new { username = User.Identity!.Name,
        role = User.FindFirstValue(ClaimTypes.Role), mode = "demo" });

    [Authorize, HttpPost("logout")]
    public async Task<IActionResult> Logout()
    {
        await HttpContext.SignOutAsync();
        return NoContent();
    }
}

public sealed record LoginRequest(
    [Required, MaxLength(128)] string Username,
    [Required, MaxLength(1024)] string Password);
