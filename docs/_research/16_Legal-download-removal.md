# Legal Download Removal - Research Note

Date: 2026-07-02

## Status

Holds. The optional download/acquisition module is removed from Syncbox v1. Syncbox must remain purchase-only for missing tracks until the owner approves a separate, lawful, rights-cleared music acquisition design.

## Sources Checked

- Spotify Developer Policy: `https://developer.spotify.com/policy`
- Spotify Compliance Tips: `https://developer.spotify.com/compliance-tips`
- Deezer Terms of Use for Developers: `https://developers.deezer.com/termsofuse`
- Deezer Developer Guidelines: `https://developers.deezer.com/guidelines`

## Findings

1. Spotify requires developers to comply with the Developer Terms and Policy, to avoid misleading users, to comply with the law, and not to encourage or enable unlawful behavior.
2. Spotify Audio Preview Clips are constrained to streaming-style promotional uses and must not be offered as a standalone product.
3. Deezer developer terms prohibit association with illegal or unauthorized use, streaming, downloading, or sharing of music content.
4. Deezer terms state that full-length listening is limited to authorized private use contexts, that protected content is covered by DRM, and that developers must not bypass these measures to download content.
5. Deezer guidelines distinguish user levels with 30-second clip restrictions for non-paying contexts.

## Decision

Remove all implementation work for:

- Deezer full-track download,
- streamrip,
- deemix or deemix forks,
- ARL storage and ARL UI,
- SoundCloud download,
- ffmpeg-based download,
- download job queues,
- download progress jobs,
- POC #6 full-track download validation.

Keep only:

- Spotify read-only playlist metadata sync under approved OAuth scopes,
- Rekordbox local collection maintenance,
- legal purchase/search links opened in the user's browser,
- manual relink to files the user already lawfully owns,
- local read-only quality diagnostics.

Legacy research files about download tooling are historical only. Build agents must not read or implement them unless the owner explicitly reopens this topic with a new legal design decision.
