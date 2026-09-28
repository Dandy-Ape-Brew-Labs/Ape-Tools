# file-media

Inspect media files without loading them as text.

```sh
file_media.py diagram.png              # {mime, width, height}
file_media.py photo.jpg --base64       # embeds base64 for vision use
file_media.py paper.pdf --pages 1-3    # text of pages 1-3 (needs pdftotext)
file_media.py scan.pdf --text          # full text extraction
```

Image dimensions are parsed from headers (PNG/JPEG/GIF/WebP) — no
dependencies. PDF features need `poppler-utils` (`pdftotext`, `pdfinfo`);
the tool fails fast with a hint when they're absent. Files >10MB refuse
`--base64`.
