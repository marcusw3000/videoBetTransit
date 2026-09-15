using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Identity;

namespace TrafficCounter.Api.Security;

public static class AccountCommand
{
    public static void Run(string[] args)
    {
        string? Argument(string name)
        { var index = Array.IndexOf(args, name); return index >= 0 && index + 1 < args.Length ? args[index + 1] : null; }
        var username = Argument("--create-user")?.Trim().ToLowerInvariant();
        var role = Argument("--role") ?? "player";
        if (string.IsNullOrWhiteSpace(username) || username.Length > 128 || role is not "player" and not "admin")
            throw new ArgumentException("Informe --create-user NOME --role player|admin.");
        Console.Error.Write("Senha (minimo 12 caracteres, entrada oculta): ");
        var password = "";
        if (Console.IsInputRedirected) password = Console.ReadLine() ?? "";
        else
        {
            ConsoleKeyInfo key;
            while ((key = Console.ReadKey(true)).Key != ConsoleKey.Enter)
                if (key.Key == ConsoleKey.Backspace) password = password.Length > 0 ? password[..^1] : password;
                else if (!char.IsControl(key.KeyChar)) password += key.KeyChar;
            Console.Error.WriteLine();
        }
        if (password.Length < 12) throw new ArgumentException("Use pelo menos 12 caracteres.");
        var file = Path.GetFullPath(Argument("--accounts-file") ?? "appsettings.Local.json");
        var config = File.Exists(file) ? JsonNode.Parse(File.ReadAllText(file))!.AsObject() : new JsonObject();
        var auth = config["Auth"]?.AsObject() ?? new JsonObject();
        if (config["Auth"] is null) config["Auth"] = auth;
        var users = auth["Users"]?.AsArray() ?? new JsonArray();
        if (auth["Users"] is null) auth["Users"] = users;
        var account = new LocalAccount { Username = username, Role = role };
        account.PasswordHash = new PasswordHasher<LocalAccount>().HashPassword(account, password);
        var existing = users.FirstOrDefault(u => string.Equals(u?["Username"]?.GetValue<string>(), username, StringComparison.OrdinalIgnoreCase));
        if (existing is not null) users.Remove(existing);
        users.Add(JsonSerializer.SerializeToNode(account));
        var temporary = file + ".tmp";
        File.WriteAllText(temporary, config.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        File.Move(temporary, file, overwrite: true);
        Console.WriteLine($"Conta {username} ({role}) configurada em {file}. A senha nao foi gravada em texto aberto.");
    }
}
