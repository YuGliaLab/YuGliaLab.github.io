# Yu Lab Website (GitHub Pages)

This repo contains a static mirror of the current Wix site under `/site`.

## Local preview

```bash
python3 -m http.server 4173 --directory site
# then open http://localhost:4173/
```

## GitHub Pages (custom domain)

1. Create a GitHub repo and push this code.
2. In **Settings → Pages**, set the source to **GitHub Actions**.
3. Add your custom domain `yu-lab.org` (or `www.yu-lab.org`) in GitHub Pages settings.
4. In your DNS provider:
   - Create an `A` record for apex `yu-lab.org` pointing to GitHub Pages IPs (per GitHub docs), OR
   - Use `CNAME` for `www` and redirect apex to `www`.

This repo includes `/site/CNAME` set to `yu-lab.org`.

## Decap CMS

Decap CMS is included at `/site/admin`.

**Important limitation:** GitHub Pages does not provide authentication. To use Decap CMS editing you need an auth provider (e.g. Netlify Identity + Git Gateway, or your own OAuth/proxy). The CMS config is currently set with placeholders:

- `site/admin/config.yml` → update `repo: OWNER/REPO` and `branch:`

If you want, I can help set up a minimal auth approach (Netlify for admin only, or Cloudflare Pages, etc.).
