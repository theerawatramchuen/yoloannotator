# YOLO Bounding Box Annotator

A lightweight desktop tool for creating and editing bounding box annotations in **YOLO format** (`.txt` label files). Built with Python and Tkinter — no GPU, no heavy dependencies.

---
<img width="1920" height="1100" alt="image" src="https://github.com/user-attachments/assets/5179a719-42e9-452d-8ce5-39bb52aaa121" />

## Features

| Category | Details |
|---|---|
| **Draw** | Click-drag to create new boxes on the canvas |
| **Edit** | Move boxes by dragging, resize by dragging corner handles |
| **Copy / Paste** | Copy any box and paste it with a cascading offset |
| **Delete** | Remove selected box with `Del` or toolbar button |
| **Change Class** | Select a box, pick a class in the right panel, click Change Class (or press `0`–`9`) |
| **Navigation** | Prev / Next image with unsaved-changes guard |
| **Smart Open** | Auto-jumps to the first image that has no annotation file |
| **Jump to Unannotated** | Button always finds the next unlabelled image |
| **Dataset Summary** | Total images, annotated count, unannotated count, per-class box counts |
| **Filmstrip** | Scrollable thumbnail strip with green/red annotation indicator dots (toggle on/off) |
| **Zoom** | Fit / 50% / 75% / 100% / 150% / 200% |
| **Live Coords** | Mouse pixel coordinates shown in the status bar |
| **Unsaved-change Guard** | Prompts to save before navigating away from a dirty image |

---

## Requirements

Python 3.8 or later with the following packages:

```
pillow
pyyaml
```

Install with:

```bash
pip install pillow pyyaml
```

> Tkinter is included in the standard Python distribution on Windows and macOS.  
> On Linux install it with: `sudo apt install python3-tk`

---

## Quick Start

```bash
python annotator.py
```

Two dialogs appear on launch:

1. **Select `data.yaml`** — your YOLO dataset config file (cancel to fall back to a generic `object` class).
2. **Select image folder** — the root folder containing your images (searched recursively).

The tool then opens the first image that does not yet have a matching `.txt` annotation file.

---

## Supported File Formats

### Images
`.jpg` · `.jpeg` · `.png` · `.bmp` · `.webp` (case-insensitive, recursive search)

### Annotations
Standard **YOLO format** `.txt` — one line per box:

```
<class_id> <cx> <cy> <width> <height>
```

All values are normalised to `[0, 1]` relative to image width/height.  
Annotation files are saved next to their image with the same base name.

### data.yaml
Standard YOLO dataset config:

```yaml
path: /path/to/dataset
train: images/train
val: images/valid

nc: 11
names: ['normal', 'suspected', 'sitting', 'standing', 'leaning',
        'spool', 'vacuume', 'grove', 'unzip', 'undress', 'badge']
```

Only the `names` field is read by the annotator.

---

## UI Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Toolbar: Open │ Save │ ← Prev │ Next → │ Delete │ Copy │ Paste │
│           Jump to Unannotated │ Summary │ Filmstrip │ Zoom       │
├─────────────────────────────────┬───────────────────────────────┤
│                                 │  IMAGE INFO                   │
│                                 │  filename, size, annotated?   │
│                                 ├───────────────────────────────┤
│          Canvas                 │  ACTIVE CLASS                 │
│    (image + bounding boxes)     │  scrollable class list        │
│                                 ├───────────────────────────────┤
│                                 │  ANNOTATIONS                  │
│                                 │  list of boxes on this image  │
│                                 │  [Change Class] button        │
│                                 ├───────────────────────────────┤
│                                 │  DATASET SUMMARY              │
│                                 │  total / annotated / pending  │
├─────────────────────────────────┴───────────────────────────────┤
│  Filmstrip  (hidden by default — press F to toggle)             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `A` | Previous image |
| `D` | Next image |
| `S` | Save annotations |
| `C` | Copy selected box |
| `V` | Paste copied box (cascades +20 px each paste) |
| `F` | Toggle filmstrip on / off |
| `Del` / `Backspace` | Delete selected box |
| `Esc` | Deselect current box |
| `0` – `9` | Quick-switch active class (also reassigns class if a box is selected) |

---

## Mouse Controls

| Action | How |
|---|---|
| **Draw new box** | Click and drag on an empty area of the canvas |
| **Select box** | Click inside any existing box |
| **Move box** | Click inside a selected box and drag |
| **Resize box** | Drag one of the four corner handles (appear when box is selected) |
| **Deselect** | Click empty canvas area or press `Esc` |
| **Jump to image** | Click a thumbnail in the filmstrip (when visible) |

---

## Workflow

### Annotating from scratch

1. Run `python annotator.py` and select your `data.yaml` and image folder.
2. The tool opens the first image without a `.txt` file.
3. Select the target class in the **ACTIVE CLASS** panel (or press a number key).
4. Click-drag on the canvas to draw a bounding box.
5. Repeat for all objects in the image.
6. Press `S` to save, then `D` to move to the next image.
7. Use **Jump to Unannotated** to always find the next unlabelled image quickly.

### Reviewing / correcting existing annotations

1. Open the folder as above — the tool loads existing `.txt` files automatically.
2. Navigate with `A` / `D` or click thumbnails in the filmstrip.
3. Click a box to select it; drag to move or drag a corner to resize.
4. To relabel a box: select it → pick a class → click **Change Class** (or press the number key).
5. To delete: select the box and press `Del`.
6. Press `S` to save changes.

### Copying repeated objects

When the same object appears many times in similar positions across images:

1. Draw and label the box once.
2. Press `C` to copy it.
3. Press `V` to paste — the copy appears offset by 20 px.
4. Drag the pasted box into position.
5. Repeat `V` for additional copies; each paste cascades further.

---

## Status Bar Indicators

| Indicator | Meaning |
|---|---|
| `3 / 120` | Current image index / total images |
| `[✓]` | This image has a saved annotation file |
| `[✗]` | This image has no annotation file yet |
| `●` | Unsaved changes exist (also shown in window title) |
| `x=412  y=308` | Mouse cursor position in original image pixels |

### Filmstrip dot colours

| Colour | Meaning |
|---|---|
| 🟢 Green | Annotation file exists |
| 🔴 Red | No annotation file yet |
| Blue border | Currently open image |

---

## File Structure

The annotator reads and writes files **in-place** alongside the images:

```
dataset/
├── images/
│   ├── train/
│   │   ├── frame_001.jpg
│   │   ├── frame_001.txt   ← created / updated by annotator
│   │   ├── frame_002.jpg
│   │   └── frame_002.txt
│   └── valid/
│       ├── frame_058.jpg
│       └── frame_058.txt
└── data.yaml
```

---

## Constants (editable in source)

| Constant | Default | Description |
|---|---|---|
| `SUPPORTED_EXTS` | jpg, jpeg, png, bmp, webp | Image extensions to scan |
| `BOX_COLORS` | 11 colours | Per-class box colour palette |
| `MIN_BOX_PX` | `5` | Minimum drag size in pixels to register a new box |

---

## Known Limitations

- Annotation files store **bounding boxes only** — keypoints, segmentation masks, and OBB (oriented bounding box) formats are not supported.
- The filmstrip loads all thumbnails when toggled on; for very large datasets (10 000+ images) this may take a moment.
- No undo / redo — save frequently and use your version control system to track annotation history.

---

## License

MIT — free to use, modify, and distribute.
