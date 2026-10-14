# Privacy Policy

Last updated: October 14, 2026

## 1. Overview
This Privacy Policy explains how the **Switch Games Data** synchronization project handles data and credentials. This repository is designed to maintain and distribute public game metadata for Nintendo Switch games.

## 2. Information Collection and Use
- **No Personal Data:** We do not collect, store, sell, or transmit any personally identifiable information (PII) from users or visitors.
- **No Tracking:** We do not employ cookies, web beacons, or third-party analytics trackers.

## 3. Google OAuth & API Access
- **Purpose of Access:** Google OAuth 2.0 credentials are used exclusively by automated GitHub Actions background workflows to read metadata from specified Google Sheets.
- **Scope of Data:** Access is strictly read-only (`spreadsheets.readonly`) for designated spreadsheet documents. We do not access, modify, or read any other user files, Google Drive data, or emails.
- **Credential Storage:** All API client IDs, client secrets, and refresh tokens are securely encrypted within GitHub Actions Repository Secrets. No secrets are stored in plain text or exposed to the public.

## 4. Third-Party Services
- **GitHub:** Project code, issues, and public data files (`data/games.json`, `images/*.jpg`) are hosted on GitHub and subject to the [GitHub Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-privacy-statement).
- **Google Sheets API:** Sheet data synchronization complies with the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy).

## 5. Contact
For any questions regarding this policy, please open an issue on the [GitHub repository](https://github.com/uongsuadaubung/switch-games-data).

