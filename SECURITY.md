# Security Policy

## Supported Versions

The Navicane project is under active development. Currently, we only provide security updates for the `main` branch.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| older   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability within Navicane, please do **not** open a public issue. Instead, please follow these steps:

1. Send a private message to the repository owner or open a Draft Security Advisory on GitHub if the feature is enabled.
2. Provide a detailed description of the vulnerability, including:
   - Steps to reproduce.
   - The potential impact.
   - Information about the environment where the bug was found.

We take all security issues seriously and will respond as quickly as possible to assess and patch the vulnerability.

## Secure Deployment

When deploying the Navicane container to a Raspberry Pi:
- The Docker container runs in `privileged` mode to access I2C and GPIO pins. **Do not** expose the Docker daemon or the Raspberry Pi to the public internet without proper firewall configuration and SSH key authentication.
- Regularly update the host OS (Raspberry Pi OS / Debian) and Docker Engine.
- Do not run the container as root inside the image unless strictly necessary for GPIO access (currently required by `gpiozero` and `picamera2`).
