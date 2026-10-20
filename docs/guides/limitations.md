[Documentation](../README.md) / Known limitations

# Known limitations

This is not a complete or pixel-identical replica of Tangerine. Linux fonts, widgets, material effects, codec builds, and compositor behavior differ. Compositor and system tray implementations differ; some desktops may need adjustment.

- Image → DOCX embeds the image; it does not perform OCR.
- PDF → DOCX/EPUB/MD extracts text without rebuilding tables, images, or page layout. Scans need an external OCR workflow. PDF → PPTX/XLSX reconstruction and Apple Pages/Keynote exports are not included.
- Bleep Audio mutes selected ranges rather than synthesizing a tone.
- Photo adjustments approximate the named controls; crop/annotation/redaction use parameter controls and previews rather than a complete canvas editor.
- Compression can produce a larger file. Codec support depends on the selected engine. Sample checks cannot certify every source file, input/output combination, or parameter.
- Inputs are read-only during conversions. Outputs use collision-safe names. Cancellation/failure removes staging; a filesystem failure during publication can leave already-published results. Move is a separate, explicitly chosen operation that changes file locations.
- Archive extraction rejects traversal, links, and special files, with a 4 GiB / 50,000-entry expansion budget. Conversion engines process local files; keep those system programs updated.
- Native keyboard controls and accessible action buttons are tested, but full screen-reader certification is not claimed. User-selected colors and translucent wheel text may need adjustment for their wallpaper and contrast needs.
