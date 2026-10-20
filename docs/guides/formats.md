[Documentation](../README.md) / Formats and tools

# Formats and tools

| Input | Outputs / tools | Program used when required |
| --- | --- | --- |
| Images | JPG, PNG, WebP, HEIC, TIFF, AVIF, BMP, PDF, image-in-DOCX; compress, adjust, crop, resize, rotate, annotate, redact, backgrounds, collage | ImageMagick; Pillow for previews and photo tools |
| Audio | MP3, M4A, WAV, FLAC, OGG, Opus, AIFF, WMA; trim, channels, volume, speed, normalize, mute ranges, merge, waveform video | FFmpeg, FFprobe, FFplay for playback |
| Video | MP4, MOV, MKV, WebM, AVI, WMV, GIF, MP3 extraction; resize, crop, rotate, trim, mute, split, redact, snapshots, merge | FFmpeg and FFprobe |
| PDF | DOCX/EPUB/TXT/MD text export; PNG/JPG pages; merge, split, organize, rotate, metadata, content-stream compression | Poppler for extraction/rendering; vendored pypdf for page tools |
| Documents | PDF, DOCX, ODT, RTF, TXT, HTML, EPUB, PNG/JPG | Compatible LibreOffice command interface; formatted Markdown needs Pandoc |
| Slides | PDF, PPTX, ODP, PNG/JPG | Compatible LibreOffice command interface |
| Spreadsheets | XLSX, ODS, CSV, TSV, PDF | Compatible LibreOffice command interface; CSV/TSV conversion also works directly |
| Subtitles | SRT, VTT, TXT; time shift | Built in |
| Archives / folders | ZIP, TAR, TAR.GZ creation and safe extraction; RAR/7Z/XZ extraction | Built in; compatible 7-Zip command interface for extra archive types |

Actions include Open, shelf, file/path clipboard, explicit Move, Terminal, and Share using the selected application. Linux cannot provide Apple's AirDrop or Apple-only export formats.
