# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Email:** [w1se82](https://github.com/w1se82) via GitHub private message

Please include:
- A description of the vulnerability
- Steps to reproduce the issue
- Potential impact

I will try to respond within 7 days and work on a fix as soon as possible.

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest on `master` | Yes |

## Security Considerations

### API Keys

- Alpaca API keys are stored in `.env` and **never committed to git**
- `.env` is listed in `.gitignore`
- The Claude Code CLI authenticates independently — no API key is stored in this project

### Network

- The web dashboard binds to `localhost` (127.0.0.1) by default and is not exposed to the network
- Use `--host 0.0.0.0` only on trusted networks (e.g. home LAN for Raspberry Pi access)
- There is no authentication on the dashboard — anyone with network access can view account data and execute trades

### Trading Safety

- Paper trading mode is enabled by default
- Switching from paper to live requires an explicit toggle
- A drawdown circuit breaker automatically liquidates positions if losses exceed the configured threshold
- PDT protection prevents violating the pattern day trader rule on accounts under $25,000

## Best Practices

- Never commit `.env` or any file containing API keys
- Use paper trading API keys during development and testing
- Restrict network access to the dashboard when running on a server
- Review `logs/` regularly for unexpected activity
