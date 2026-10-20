[Documentation](../README.md) / Interactive editors

# Interactive editors

Choose a conversion or tool from the wheel. Petal opens a separate editor: adjust the settings, review the result, then choose **Create copy**. The original stays unchanged. File actions such as Open and Copy remain quick actions.

## Drag and type

Image/video crop and redaction tools show a selection rectangle. Drag outside it to draw a new selection, inside to move it, or an edge/corner handle to resize it. A full-image selection starts a new selection when dragged inside. The Left, Top, Width, and Height fields update immediately. Editing a field moves the handles as well. Video values snap to even pixels. An invalid rectangle disables export until corrected.

Annotation supports a draggable rectangle plus text, rectangle, ellipse, or arrow settings. Color controls open a native color picker. Photo adjustments, backgrounds, watermarks, borders, and image effects update their result previews as controls change.

## Review pages and batches

PDF tools render a result page with page navigation and show the resulting page count. Organize PDF starts with every page: select a row and use Page up, Page down, or Remove page. The order field updates with those buttons; entering an order updates the list. For PDFs over 1,000 pages, use the order field directly.

For multiple files, select a row and move it up or down. The reviewed order is used by merges, image-to-PDF, collages, and other batch jobs.

## New tools

| File type | Added in Beta 2 |
| --- | --- |
| Images | Blur, Sharpen, Invert Colors, Sepia, Watermark, Add Border |
| Audio | Fade in/out |
| Video | Fade from/to black |
| PDF | Reverse Pages, Remove Pages, Duplicate Pages |

Existing conversion, geometry, compression, metadata, and media tools now lead into a review screen as well. Audio trim, channel, and mute-range editors retain their waveform controls.

## What the preview shows

Images show transformed output and dimensions. PDFs show rendered pages when a renderer is available. Converted office files can be rendered through the selected compatible office engine. Text outputs show a text excerpt. Archive actions show a plan or listing before they touch output files.

Audio/video previews are samples of up to three seconds, with playback when ffplay is available. Trim starts at the selected time; other media previews start at the beginning. A timed effect later in a clip may not appear in the sample. Ordinary batch previews show the first file, and combined previews use up to the first 16 inputs. The editor explains these limits; final exports process the full selection.

## Continue editing

When export finishes, choose **Edit result** to return to the wheel with the saved copy selected. Choose another tool to continue. **Open results** shows the files, and **Done** closes completion feedback.
