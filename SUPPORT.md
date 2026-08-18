# Getting help with Syncbox

Syncbox is maintained by one person in their spare time. There is no support
inbox and no SLA — but everything below gets read.

## I have a question

Open a [new issue](https://github.com/Adridot/syncbox/issues/new) and describe
what you were trying to do. Check the [user guide](docs/USER_GUIDE.md) first;
most "how do I…" answers are already there.

## Something is broken

Open an [issue](https://github.com/Adridot/syncbox/issues/new) and include:

- **Syncbox version** — shown in Settings;
- **macOS version** and whether you are on Apple Silicon;
- **what you expected** vs. what happened;
- **the logs** — open **Collection Health → Backups & logs**, choose *Open the
  logs folder*, and attach the relevant log file. Logs exclude Spotify tokens
  and credentials by design (see [docs/PRIVACY.md](docs/PRIVACY.md)).

If the problem involves a Rekordbox write, say whether Rekordbox was closed
and whether a backup was created. Do not attach your `master.db`.

## I think I found a security problem

Do **not** open a public issue. Follow
[.github/SECURITY.md](.github/SECURITY.md) and use GitHub's private
vulnerability reporting.

## I want to change something

See [CONTRIBUTING.md](CONTRIBUTING.md).
