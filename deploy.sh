#!/bin/bash
# Push the page straight to Cloudflare. Seconds, no GitHub in the path.
set -e
cd "$(dirname "$0")"
export CLOUDFLARE_API_TOKEN=${CLOUDFLARE_API_TOKEN:-$(grep -oE 'CLOUDFLARE_API_TOKEN=["'"'"']?[A-Za-z0-9_-]+' ~/.zshenv | head -1 | sed 's/.*=//' | tr -d '"'"'"'')}
export CLOUDFLARE_ACCOUNT_ID=28b22d2560f6428a26cd8220fc5a4393
rm -rf dist && mkdir -p dist
cp index.html dist/
printf '/*\n  Cache-Control: public, max-age=0, must-revalidate\n' > dist/_headers
npx -y wrangler@latest pages deploy dist --project-name rbi-percentage --branch main --commit-dirty=true
