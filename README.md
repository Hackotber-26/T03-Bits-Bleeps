# Odikyu

Odikyu is a digital bodyguard on your phone that stops scams before money leaves your account — saving you from phishing, SMS fraud, and scam messages before it's too late.

## What's where

The two components live on separate branches of this repository:

| Component | Branch | What it is |
|---|---|---|
| **Android app** | [`odikyuapp`](https://github.com/Hackotber-26/T03-Bits-Bleeps/tree/odikyuapp) | The phone app: default-SMS inbox with link/classifier warnings, Protection toggle, settings, UI in 6 languages |
| **DNS server** | [`odikyudns`](https://github.com/Hackotber-26/T03-Bits-Bleeps/tree/odikyudns) | The protection backend: RFC 8484 DNS-over-HTTPS proxy serving `/dns-query` (deployed at `dns.odikyu.tech`), plus block page and deploy scripts |

This `main` branch only holds this README.
