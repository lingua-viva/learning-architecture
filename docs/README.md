# Lingua Viva Landing Page

Static site for `linguaviva.art`, served via GitHub Pages from this `docs/` folder.

Push to `main` → site auto-deploys.

## Local Preview

```sh
cd docs && python3 -m http.server 4177
```

Open `http://127.0.0.1:4177/`.

## DNS

Namecheap Advanced DNS for `linguaviva.art`:
- A records → GitHub Pages IPs (185.199.108–111.153)
- CNAME `www` → `lingua-viva.github.io`

## Download Buttons

Linked to GitHub release assets (`/releases/latest/download/lv-*`).
Always points to latest release tag.
