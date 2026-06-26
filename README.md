# Zotero Daily News

Daily Zotero paper digest with DeepSeek summaries, a local control panel, scheduled delivery, and optional Zotero note backfill.

Repository: [TomatooEgg/Zotero-Daily-News](https://github.com/TomatooEgg/Zotero-Daily-News)

## Platforms

- Windows 10/11 x86_64
- macOS 11+
- Zotero must be installed and running

In Zotero, enable local API access:

`Settings -> Advanced -> Allow other applications on this computer to communicate with Zotero`

## Windows Quick Start

Use one of the release artifacts:

- `Zotero-Daily-News-Windows-x86_64.msi`
- `Zotero-Daily-News-Windows-x86_64-Portable.zip`

For the MSI, double-click the installer and start **Zotero Daily News** from the desktop shortcut or Start menu.

For the portable ZIP, unzip it and run `Zotero Daily News.exe`.

On first launch the setup wizard asks for:

- DeepSeek API key
- DeepSeek base URL and model names
- Zotero API key with write permission
- Optional Zotero library ID

The app saves the settings, tests DeepSeek and Zotero, then enables scheduled tasks only after validation succeeds.

Windows scheduling uses Task Scheduler tasks named `ZoteroDailyNews\Push*` and `ZoteroDailyNews\Prepare*`.

## macOS Quick Start

From source:

```bash
git clone https://github.com/TomatooEgg/Zotero-Daily-News.git
cd Zotero-Daily-News
bash install.sh
```

`install.sh` creates the Python environment, installs dependencies, builds the macOS app bundle, and creates the desktop shortcut. It does not register launchd immediately. Start the app first, complete the setup wizard, then use the control panel to enable scheduled delivery.

For a DMG build, open the app from the DMG and complete the same first-launch wizard. Do not edit `.env` inside the app bundle.

macOS scheduling uses launchd after setup validation.

## Source Usage

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt  # Windows PowerShell
.venv\Scripts\python launcher.py
```

On macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python launcher.py
```

Common commands:

| Action | Windows | macOS/Linux |
| --- | --- | --- |
| Start UI | `.\start_ui.ps1` | `bash start_ui.sh` |
| Manual push | `.\run.ps1 --push-queue` | `bash run.sh --push-queue` |
| Refresh queue | `.\run.ps1 --refresh-queue` | `bash run.sh --refresh-queue` |
| Pre-generate | `.\prepare_queue.ps1` | `bash prepare_queue.sh` |
| Preview only | `.\run.ps1 --dry-run --push-queue` | `bash run.sh --dry-run --push-queue` |
| Skip AI | `.\run.ps1 --metadata-only` | `bash run.sh --metadata-only` |

## Configuration

The single source of built-in defaults is `config_manager.DEFAULT_CONFIG`.

`config.example.yaml` is an example file for source users. Runtime configuration is written to the user config directory, not the repository.

Default values:

| Key | Default |
| --- | --- |
| `priority_tag` | `want` |
| `count` | `2` |
| `history_days` | `14` |
| `queue.size` | `4` |
| `queue.prepare_before_minutes` | `120` |
| `schedule` | `10:00`, `18:00` |
| `ui.port` | `18765` |

User config paths:

| Platform | Config and `.env` |
| --- | --- |
| Windows | `%APPDATA%\Zotero Daily News\` |
| macOS | `~/Library/Application Support/Zotero Daily News/` |
| Linux | `$XDG_CONFIG_HOME/zotero-daily-news/` or `~/.config/zotero-daily-news/` |

Runtime state paths:

| Platform | Runtime files |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Zotero Daily News\` |
| macOS | `~/Library/Application Support/Zotero Daily News/` |
| Linux | `$XDG_STATE_HOME/zotero-daily-news/` or `~/.local/state/zotero-daily-news/` |

Runtime files include `history.json`, `queue.json`, `pending_publish.json`, `summaries/`, `hubs/`, and `logs/`.

## Build Windows Artifacts

Run on Windows:

```powershell
.\build_windows.ps1
```

Outputs:

- `dist\Zotero-Daily-News-Windows-x86_64.msi`
- `dist\Zotero-Daily-News-Windows-x86_64-Portable.zip`

## CI

GitHub Actions runs tests on Windows and macOS for pull requests and pushes. A manual workflow or tag build also produces the Windows MSI and portable ZIP.

## Security

Markdown/LLM output is sanitized before HTML rendering. Unsafe tags, event attributes, `javascript:` URLs, and images are stripped while Markdown tables, code blocks, Mermaid classes, and Zotero links are preserved.

## Troubleshooting

**Cannot connect to Zotero**

Make sure Zotero is running and local API access is enabled.

**DeepSeek validation fails**

Check the API key, base URL, and model names in the setup wizard or Settings tab.

**Zotero backfill fails**

Create a Zotero API key at [zotero.org/settings/keys](https://www.zotero.org/settings/keys) with library write permission, then re-run setup validation.

**Scheduled delivery did not update**

Open the control panel and click the scheduler reload button after changing schedule settings.

## License

[MIT License](LICENSE)
