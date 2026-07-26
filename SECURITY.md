# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |
| < Latest| :x:                |

## Reporting a Vulnerability

Please report security vulnerabilities to the maintainers privately via GitHub Security Advisories or email. Do not open public issues for security vulnerabilities.

## Security Measures Implemented

### 🔒 Authentication & Authorization
- Bearer token authentication for Linkwarden API
- Environment-based secrets management (never hardcoded)
- Mandatory validation of all required environment variables at startup

### 🛡️ Input Validation
- URL validation against whitelist (http/https only)
- Rejection of private/localhost addresses (SSRF protection)
- Message size limits (configurable, default 50KB)
- Safe URL extraction using urllib.parse instead of ReDoS-vulnerable regex

### 🚦 Rate Limiting
- Per-user rate limiting: 10 messages per 60 seconds (configurable)
- Prevents denial-of-service attacks on Linkwarden API
- Configurable thresholds via environment variables

### 🔐 Container Security
- Non-root user execution (UID 1001)
- Alpine Linux base image (minimal attack surface)
- No package cache in Docker image
- Pinned dependency versions

### 📝 Logging & Monitoring
- Configurable log levels (WARNING by default in production)
- No sensitive data logged (API keys, full URLs with query params)
- Error messages don't expose internal details

### ✅ API Communication Security
- HTTPS enforced for external APIs
- Request timeout (10 seconds)
- Automatic retry with exponential backoff (3 attempts max)
- Response validation before processing

## Environment Variables

Set these securely in your deployment:

```bash
TELEGRAM_TOKEN=<bot-token>              # Required: Telegram bot token
LINKWARDEN_API_URL=<url>                # Required: Linkwarden API base URL
LINKWARDEN_API_KEY=<api-key>            # Required: Linkwarden API key
LINKWARDEN_COLLECTION_ID=<collection>   # Required: Target collection ID
LOG_LEVEL=WARNING                       # Optional: DEBUG|INFO|WARNING|ERROR|CRITICAL
RATE_LIMIT_THRESHOLD=10                 # Optional: Max messages per window
RATE_LIMIT_WINDOW=60                    # Optional: Time window in seconds
MAX_MESSAGE_SIZE=51200                  # Optional: Max message size in bytes
```

## Deployment Best Practices

### Secrets Management
- Use secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)
- Rotate API keys regularly
- Use different API keys for different environments (dev/staging/prod)
- Never commit `.env` to version control

### Network Security
- Run bot in isolated private network
- Use VPN/private link to Linkwarden instance
- Restrict Telegram API access to known IPs if possible
- Enable TLS 1.2+ only

### Monitoring & Logging
- Monitor failed API requests
- Alert on rate limit violations
- Log errors to centralized logging system
- Regularly review logs for anomalies

### Container Orchestration
```yaml
# Kubernetes example
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

### CI/CD Pipeline
- Run `pip check` to detect vulnerable dependencies
- Use security scanners: `bandit`, `safety`
- Scan Docker image with Trivy/Grype
- Use code signing for releases

## Known Limitations

- Rate limiting is in-memory (resets on restart). Use Redis for distributed rate limiting in clustered deployments
- No persistent audit logging; add external logging for compliance requirements
- LINKWARDEN_API_KEY exposed via environment (consider Telegram bot group for trusted users only)

## Updates & Security Patches

Keep dependencies updated:
```bash
pip list --outdated
pip install --upgrade -r requirements.txt
```

Use tool like `dependabot` to automate dependency updates.
