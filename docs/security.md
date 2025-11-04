# MAMMON Security Documentation

## Security Principles

MAMMON is built with security as the top priority. This document outlines our security architecture and practices.

## Critical Security Rules

### NEVER
1. ❌ Store private keys in code or version control
2. ❌ Commit .env files or secrets
3. ❌ Skip input validation on external data
4. ❌ Allow transactions without limits
5. ❌ Ignore error conditions
6. ❌ Run on mainnet without extensive testing

### ALWAYS
1. ✅ Validate all inputs
2. ✅ Enforce spending limits
3. ✅ Require approval for large transactions
4. ✅ Log all critical operations
5. ✅ Use type hints and validation
6. ✅ Test on testnet first

## Multi-Layered Security

### Layer 1: Configuration Security
- Pydantic validation of all environment variables
- Rejection of placeholder values
- Type checking on all settings
- No hardcoded secrets

### Layer 2: Input Validation
- All addresses validated (checksummed Ethereum format)
- All amounts validated (positive, reasonable decimals)
- All protocol names sanitized
- All URLs validated (HTTPS required)

### Layer 3: Spending Limits
- Per-transaction maximum
- Daily spending limit
- Weekly spending limit
- Monthly spending limit

### Layer 4: Approval Workflows
- Threshold-based approval requirement
- Manual confirmation for large amounts
- Timeout on approval requests
- Audit trail of all approvals

### Layer 5: Audit Logging
- Immutable audit log
- All transactions logged
- All decisions logged
- All security events logged

## Threat Model

### Threats We Protect Against
1. **Accidental Loss**: Spending limits prevent mistakes
2. **Configuration Errors**: Validation catches bad config
3. **Malicious Input**: Input validation prevents injection
4. **Unauthorized Transactions**: Approval workflows add oversight
5. **Protocol Risks**: Risk assessment evaluates safety

### Threats Outside Scope (Phase 1)
1. **Smart Contract Exploits**: Rely on protocol security audits
2. **Market Manipulation**: Not attempting MEV protection yet
3. **Network Attacks**: Rely on RPC provider security
4. **Compromised Dependencies**: Trust Poetry lock file

## Security Checklist

### Before Testnet
- [ ] All secrets in .env, not code
- [ ] Spending limits configured
- [ ] Approval threshold set
- [ ] Input validation complete
- [ ] Audit logging working
- [ ] Tests passing

### Before Mainnet
- [ ] Extensive testnet testing
- [ ] Security review completed
- [ ] All limits verified
- [ ] Approval workflow tested
- [ ] Database backups configured
- [ ] Monitoring alerts set up

## Incident Response

### If Private Key Compromised
1. Immediately transfer all funds to new wallet
2. Revoke all API keys
3. Review audit logs
4. Generate new wallet
5. Update configuration

### If Unauthorized Transaction Detected
1. Check audit logs for source
2. Review approval history
3. Verify spending limits enforced
4. If loss occurred, document and analyze
5. Implement additional safeguards

## Best Practices

### For Developers
- Review security docs before changes
- Never skip validation
- Test security features
- Log security-relevant events
- Ask when unsure

### For Operators
- Use strong API keys
- Rotate keys regularly
- Monitor audit logs
- Review approvals carefully
- Keep secrets secure

### For Testing
- Use testnet first
- Test with small amounts
- Verify all limits work
- Test approval workflows
- Simulate error conditions

## Security Roadmap

### Phase 1 (Current)
- Basic security controls
- Spending limits
- Approval workflows
- Audit logging

### Phase 2
- Enhanced monitoring
- Automated alerts
- Advanced risk models
- Multi-sig support (maybe)

### Phase 3
- Formal security audit
- Bug bounty program
- Security certifications
- Insurance integration (if available)

## Responsible Disclosure

If you discover a security vulnerability:
1. Do NOT open a public issue
2. Email: [your-email]
3. Allow 90 days for fix
4. Disclosure after fix deployed

## Resources

- [Coinbase CDP Security](https://docs.cdp.coinbase.com/agentkit/docs/security)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Smart Contract Security](https://consensys.github.io/smart-contract-best-practices/)
