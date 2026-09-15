using Microsoft.AspNetCore.Identity;

namespace TrafficCounter.Api.Security;

public sealed class LocalAccount
{
    public string Username { get; set; } = "";
    public string PasswordHash { get; set; } = "";
    public string Role { get; set; } = "player";
    public string OperatorRef { get; set; } = "local";
    [System.Text.Json.Serialization.JsonIgnore]
    public string CredentialVersion => Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(
        System.Text.Encoding.UTF8.GetBytes(PasswordHash)));
}

public sealed class AccountStore(IConfiguration configuration)
{
    private readonly PasswordHasher<LocalAccount> _hasher = new();
    // An unknown username still performs password hashing work.
    private readonly string _dummyHash = new PasswordHasher<LocalAccount>()
        .HashPassword(new LocalAccount(), Guid.NewGuid().ToString());

    public LocalAccount? Find(string username) =>
        (configuration.GetSection("Auth:Users").Get<LocalAccount[]>() ?? [])
        .FirstOrDefault(a => string.Equals(a.Username, username, StringComparison.OrdinalIgnoreCase)
            && a.Role is "player" or "admin" && !string.IsNullOrWhiteSpace(a.PasswordHash));

    public LocalAccount? Authenticate(string username, string password)
    {
        var account = Find(username);
        try
        {
            var result = _hasher.VerifyHashedPassword(account ?? new LocalAccount(),
                account?.PasswordHash ?? _dummyHash, password);
            return result != PasswordVerificationResult.Failed ? account : null;
        }
        catch (FormatException) { return null; }
    }
}
