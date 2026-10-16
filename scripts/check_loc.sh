#!/usr/bin/env bash
set -euo pipefail

max_lines=500
failed=0

for root in backend frontend/src; do
    [[ -d "$root" ]] || continue

    while IFS= read -r -d '' file; do
        line_count=$(wc -l < "$file")
        if (( line_count > max_lines )); then
            printf 'File exceeds %d lines: %s (%d)\n' "$max_lines" "$file" "$line_count" >&2
            failed=1
        fi
    done < <(
        find "$root" -path '*/.venv' -prune -o -type f \( -name '*.py' -o -name '*.ts' -o -name '*.vue' \) -print0
    )
done

if (( failed != 0 )); then
    exit 1
fi

printf 'Code line limit check passed (max %d lines).\n' "$max_lines"
