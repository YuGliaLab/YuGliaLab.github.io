# Yu Lab local website editor

## Visual editor (Wix-style workflow)

The editor opens on a full-width, directly editable website canvas. Click text once and type; you see your changes on the actual page as you make them. A small floating toolbar offers formatting and image replacement. Click **Settings** only when you want the detailed inspector and move/resize handles.

- Click a text block and type directly on the page. Select words and use the floating Bold, Italic, or Link controls. Click an image to replace it.
- Change text size, color, and alignment in the inspector. Use the floating toolbar for selected text; the optional inspector also includes bullet formatting.
- Drag the blue **Move** handle to reposition an element. Drag the small bottom-right square to resize its width. Numeric offset/width fields provide precise control, and **Reset position & width** restores the original placement.
- Use **Undo / Redo** for unsaved text, image-selection, and layout changes on the current page. Saving or switching pages starts a fresh undo history. Uploaded image files remain in the media library even if their selection is undone.
- **Page layers** helps select content lower down the page or overlapping elements. **Add section** adds text and an optional image below existing page content.
- **Desktop**, **Mobile**, and **Zoom** let you inspect the layout. **Preview** hides editing outlines and includes current unsaved changes. The separate **Open full preview** link shows the last saved build.
- **Save** keeps edits locally. **Publish to GitHub** saves and publishes them using the existing Git workflow.

The underlying mirrored site still has fixed layout regions. Moving elements changes their offsets within those regions; it does not automatically rearrange other content. Check desktop and mobile layouts for overlap after moving or resizing. This is a local visual editor inspired by Wix, not the Wix platform or its full layout engine.

Temporary editor recovery files such as `.LOCAL-CMS.md.swp`, `*.swo`, and `*~` are now ignored by Git. They remain on your computer, do not get published, and no longer block Publish. Genuine unrelated files still require review.

## Open it

This folder is a working Git checkout of the lab website, with its history and remote preserved. Keep the whole folder together.

On this Mac, double-click **Start CMS.command**. It opens the editor in your browser. Leave its terminal window open while editing; close it or press Control-C to stop the server. The editor listens only on your computer, on a randomly selected local port. No hosted CMS, account, API key, or authentication service is involved.

The supplied copy is also available through the running preview at http://127.0.0.1:4178/ while this session's server remains open.

### Another computer / first-time setup

Install Git, Node.js 20 or newer, and Python 3.9 or newer. Copy this entire folder including its hidden `.git` directory, or use a clone containing these changes after they have been published. Open a terminal in that folder and run `npm ci` once to restore the site's existing build dependency. Then double-click **Start CMS.command** (macOS) or **Start CMS.bat** (Windows). On Linux, run `python3 local-cms/server.py`. On macOS, if executable permissions were lost in a transfer, run `chmod +x "Start CMS.command"` once.

The current repository is **YuGliaLab/YuGliaLab.github.io**. GitHub redirects the older `YuGliaLab/yulab.github.com` address to it. The original checkout's remote is preserved.

## Everyday editing

1. Choose Home, About the PI, People & lab photos, Publications, News, Contact, or Shared header & footer.
2. Open a text block by clicking its heading. Edit directly, select text for bold/italic or links, and use Enter for paragraphs. Pasted text is plain text so outside formatting does not damage the page.
3. For pictures, choose **Replace image**, select from the local library, or upload a PNG, JPEG, GIF, or WebP up to 8 MB. Edit the image description for accessibility. **Remove image** removes that picture when saved.
4. Use **New entry** for a new person, citation, news item, or section, with an optional link and image. New entries appear after existing page content. They become ordinary editable blocks after saving.
5. Select **Save**, then **Preview**. Review desktop and phone widths or open the full preview. Saving is local; it does not contact GitHub.
6. Select **Publish to GitHub** when ready. This also saves your open page. Publishing details lists changed files, and links to the GitHub Actions deployment status.

A successful push means GitHub received the commit; the live website updates only after the Pages workflow succeeds. The editor reports this distinction. Check Actions for the final deployment result.

## What the editor preserves and supports

The existing site is a static mirror with Nunjucks templates. The `content/pages/*.json` files and old Decap configuration were placeholders, not sources used by the build. This editor reads and writes the actual templates in `templates/`, preserving all untouched markup byte-for-byte. Existing pages, shared text, people names and biographies, publication citations and links, news, photos, styles, and assets stay in place. No content migration or redesign is performed.

New entries use flexible sections below existing content. Existing people are separate name, role, and photo blocks, as they are in the original source; they are not converted into a new people database. To remove an existing entry, clear its text blocks and remove its image. The inherited layout may retain spacing. Moving and resizing individual elements is supported through the visual canvas. Structural card reordering, adding routes/pages, and changing the underlying grid still require template work.

The mirrored site includes fixed-size layout regions. Very long replacement text may need a layout adjustment; check previews. Uploaded pictures retain the existing display dimensions. The local preview strips legacy runtime scripts and uses local assets and fallback fonts; it never needs a hosted CMS. Some original font URLs are invalid/external, and this preview does not fetch them. Published templates retain their original scripts/font declarations. The original `/admin` files remain for historical compatibility; use this local editor instead.

The duplicate static deployment workflow was removed. The remaining workflow installs the existing dependency, builds the templates, and deploys `site/`. Build failures now return a failing exit status.

## GitHub login and publishing

Publishing uses the installed `git` command and the checkout's existing remote, credential helper, or SSH agent. The CMS never asks for or stores a password or token. If Git on this computer can push to the repository, the CMS uses that same access. The connected GitHub account inside Codex is separate from the computer's Git credentials; a successful real push has not been tested as part of installation.

Before the first publish, ensure Git has your author name/email and your normal GitHub authentication is configured. If needed, use your usual GitHub CLI login/credential helper or SSH setup outside the CMS. If Git reports a missing identity, set `git config user.name "Your Name"` and `git config user.email "your address"` in this checkout. No secret should be entered into a page field.

Publish is limited to `main` and the lab repository. It checks for unrelated changes, fetches GitHub, builds, commits approved website/editor files, merges remote updates, rebuilds if needed, and pushes normally. It never force-pushes. The first publish includes the CMS implementation and deployment correction as well as any page edits. This implementation has not yet been committed or pushed to your live repository.

## When something goes wrong

- **Unsaved edits:** the editor warns before changing pages or closing the tab. Save before closing. Saved template changes survive restarting the editor.
- **Another window changed the page:** saving stops instead of overwriting it. Copy your unsaved text somewhere safe, then reload and reconcile.
- **Preview build failure:** the previous template is restored. Check that Node.js is installed and `npm ci` completes. Existing local backups are retained in `.git/local-cms-backups/`.
- **GitHub is unreachable or login fails:** your edits remain local. Restore your connection or Git authentication and retry Publish.
- **Conflicting GitHub edits:** no push occurs. Your work is retained in a local commit, and the attempted merge is aborted. The message lists affected files. A maintainer can run `git fetch origin`, then `git merge origin/main`, resolve those files, build and commit the resolution, then retry Publish. Never force-push or reset away work to resolve this.
- **Push rejected:** the local commit is retained. Retry after addressing the reported issue. A newer GitHub commit will be fetched and merged on retry. Protected branch rules may require a maintainer to publish through a pull request.
- **Unexpected repository files:** publishing stops so unrelated work is not accidentally included. Review and commit or move those files separately.
- **Deployment failed after push:** use the Actions link to inspect the build/deployment. The local CMS cannot bypass GitHub repository permissions or Pages settings.

Backups are local, not published. To restore one, stop the editor and have a maintainer copy the desired backup over its corresponding `templates/*.njk` file, then run `npm run build`. Git history also keeps every successful publish commit.

## Verification

Run `npm run test:cms` for automated temporary-repository tests. Tests cover untouched-template preservation, real preview builds, stale saves, failed-build recovery, new entries/images, content validation, publishing/retry, conflict abort/recovery, and unrelated-file protection. Tests never push to GitHub.
