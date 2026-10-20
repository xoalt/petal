[Documentation](../README.md) / Known limitations

# Known limitations

This is not a complete or pixel-identical replica of Tangerine. Linux fonts, widgets, material effects, codec builds, and compositor behavior differ. Compositor and system tray implementations differ; some desktops may need adjustment.

- Image → DOCX embeds the image; it does not perform OCR.
- PDF → DOCX/EPUB/MD extracts text without rebuilding tables, images, or page layout. Scans need an external OCR workflow. PDF → PPTX/XLSX reconstruction and Apple Pages/Keynote exports are not included.
- Bleep Audio mutes selected ranges rather than synthesizing a tone.
- Photo adjustments approximate the named controls; rectangle tools use draggable selections with synchronized coordinate fields; they are not a full freehand drawing or video timeline editor.
- Compression can produce a larger file. Codec support depends on the selected engine. Sample checks cannot certify every source file, input/output combination, or parameter.
- Inputs are read-only during conversions. Outputs use collision-safe names. Cancellation/failure removes staging; a filesystem failure during publication can leave already-published results. Move is a separate, explicitly chosen operation that changes file locations.
- Archive extraction rejects traversal, links, and special files, with a 4 GiB / 50,000-entry expansion budget. Conversion engines process local files; keep those system programs updated.
- Native keyboard controls and accessible action buttons are tested, but full screen-reader certification is not claimed. User-selected colors and translucent wheel text may need adjustment for their wallpaper and contrast needs.

## Preview scope

Media previews are samples of up to three seconds; trim previews begin at the selected start. Other media previews show the beginning of the file, so later timed effects may not appear in that sample. The rectangle canvas uses the first video frame. Final exports process the full selection. Combined previews use up to the first 16 inputs; ordinary batch previews show the first input. PDF split previews show page one, and archive previews inspect a listing or show an archive plan without extracting or compressing. These limits are identified in the editor.

Visual document previews require a compatible office engine. PDF page previews require a compatible PDF renderer. If rendering is unavailable, the editor shows output details instead. Additional Pillow image effects export PNG and need a Pillow-decodable input.
