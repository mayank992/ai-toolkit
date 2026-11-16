# Getting started

You need Claude Code, `python3` (3.9 or newer, which macOS has), and `git`. Node and pnpm are only needed to build the dashboard.

## 1. Install the plugin

From GitHub:

```bash
claude plugin marketplace add mayank992/ai-toolkit
claude plugin install ai-toolkit@ai-toolkit
```

From a local clone. Claude Code copies the plugin when it installs it, so after you change hook or skill code run `claude plugin update ai-toolkit@ai-toolkit` and start a new session (`ait doctor` says when the copy is behind):

```bash
git clone git@github.com:mayank992/ai-toolkit.git ~/code/repos/ai-toolkit
claude plugin marketplace add ~/code/repos/ai-toolkit
claude plugin install ai-toolkit@ai-toolkit
```

Start a new Claude Code session. Inside the session, the hooks, `/lesson` and `/mr-retro` are active, and Claude can run `ait` and `hs`.

## 2. Put `ait` in your own terminal (optional)

Either link the scripts:

```bash
ln -s ~/code/repos/ai-toolkit/bin/ait ~/code/repos/ai-toolkit/bin/hs ~/.local/bin/
```

Or install the package as a tool:

```bash
uv tool install git+https://github.com/mayank992/ai-toolkit
```

Then check everything:

```bash
ait doctor
```

## 3. First lesson

Work as usual. When you push back on Claude ("no, use pnpm instead"), the lessons feature captures it. When the session ends, it distills the pushback into a candidate lesson, and promotes the lesson once the same pushback shows up in a second session. To record one directly:

```
/lesson always run the linter with --fix before committing
```

Then see what was captured:

```bash
hs status          # config, stores, queue
hs list            # candidate and active lessons
hs inject          # what the next session in this repo would be told
```

To keep work lessons separate from personal ones, add a store that matches your company's remotes:

```bash
hs store add org --match '*yourcompany.com/*' --remote git@github.com:you/ai-memory-org.git
```

## 4. The dashboard (optional)

Build it once, then run it whenever you want:

```bash
pnpm -C ~/code/repos/ai-toolkit/ui install
pnpm -C ~/code/repos/ai-toolkit/ui build
ait ui
```

## 5. Your setup on a new machine (optional)

```bash
ait setup init ~/code/ai-setup --remote git@github.com:you/ai-setup.git   # keep this repo private
ait setup export --push
```

On the new machine, install the plugin (step 1), then:

```bash
ait setup apply ~/code/ai-setup --dry-run
```

## Upgrading from 0.1

If you installed with the old `install.sh`, its hooks stop running once you pull 0.2, because the paths they point at are gone. Your config files are still read and your state moves over by itself. Switch to the plugin:

```bash
cd ~/code/repos/ai-toolkit && git pull
claude plugin marketplace add ~/code/repos/ai-toolkit
claude plugin install ai-toolkit@ai-toolkit
ait migrate-legacy --dry-run      # lists the 0.1 hooks and links it would remove
ait migrate-legacy                # backs settings.json up first
```

Run `ait` from the clone (`./bin/ait`) if it isn't on your PATH yet. Restart Claude Code sessions afterwards. Your memory stores, config and state are never touched.

## Turning things off

- **One feature:** set `"enabled": false` in its section of `~/.config/ai-toolkit/config.json`.
- **Every hook, for now:** `export AI_TOOLKIT_DISABLE=1`.
- **The whole plugin:**

  ```bash
  claude plugin disable ai-toolkit@ai-toolkit
  ```

  Or `claude plugin uninstall ai-toolkit@ai-toolkit`. Memory stores and config stay. Delete them with `hs purge` if you want them gone.
