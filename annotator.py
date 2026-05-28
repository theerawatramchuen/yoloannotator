#!/usr/bin/env python3
"""
YOLO Bounding Box Annotation Tool
Supports: review, edit, create annotations for YOLO-format datasets
"""

import os
import sys
import glob
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from PIL import Image, ImageTk
import yaml


# ─── Constants ────────────────────────────────────────────────────────────────
SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
BOX_COLORS = [
    "#FF3B30", "#FF9500", "#FFCC00", "#34C759", "#007AFF",
    "#5856D6", "#AF52DE", "#FF2D55", "#00C7BE", "#A2845E", "#8E8E93",
]
MIN_BOX_PX = 5  # minimum drag size to register a box


# ─── Data helpers ─────────────────────────────────────────────────────────────

def load_classes(yaml_path):
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    return data.get("names", [])


def load_annotations(txt_path, img_w, img_h):
    """Read YOLO .txt → list of [cls, x1, y1, x2, y2] in pixel coords."""
    boxes = []
    if not os.path.exists(txt_path):
        return boxes
    with open(txt_path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) != 5:
                continue
            cls, cx, cy, bw, bh = int(parts[0]), *map(float, parts[1:])
            x1 = (cx - bw / 2) * img_w
            y1 = (cy - bh / 2) * img_h
            x2 = (cx + bw / 2) * img_w
            y2 = (cy + bh / 2) * img_h
            boxes.append([cls, x1, y1, x2, y2])
    return boxes


def save_annotations(txt_path, boxes, img_w, img_h):
    """Write list of [cls, x1, y1, x2, y2] → YOLO .txt."""
    with open(txt_path, "w") as f:
        for cls, x1, y1, x2, y2 in boxes:
            cx = ((x1 + x2) / 2) / img_w
            cy = ((y1 + y2) / 2) / img_h
            bw = abs(x2 - x1) / img_w
            bh = abs(y2 - y1) / img_h
            f.write(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")


def find_images(folder):
    imgs = []
    for ext in SUPPORTED_EXTS:
        imgs += glob.glob(os.path.join(folder, "**", f"*{ext}"), recursive=True)
        imgs += glob.glob(os.path.join(folder, "**", f"*{ext.upper()}"), recursive=True)
    return sorted(set(imgs))


def txt_for_image(img_path):
    base, _ = os.path.splitext(img_path)
    return base + ".txt"


# ─── Main App ─────────────────────────────────────────────────────────────────

class AnnotatorApp(tk.Tk):
    def __init__(self, image_dir, classes):
        super().__init__()
        self.title("YOLO Bounding Box Annotator")
        self.configure(bg="#1C1C1E")
        self.minsize(1100, 720)

        self.image_dir = image_dir
        self.classes = classes
        self.images = find_images(image_dir)
        self.current_idx = 0
        self.boxes = []          # [cls, x1, y1, x2, y2] in original image px
        self.selected_box = None
        self.dirty = False       # unsaved changes
        self._clipboard_box = None   # copied box [cls, x1, y1, x2, y2]
        self._filmstrip_visible = False  # default OFF for max image area

        # Drawing state
        self._draw_start = None
        self._draw_rect_id = None
        self._drag_box_idx = None
        self._drag_offset = None
        self._resize_handle = None  # ("tl","tr","bl","br","l","r","t","b")

        # Display
        self._photo = None
        self._scale = 1.0
        self._offset_x = 0
        self._offset_y = 0
        self._orig_w = 1
        self._orig_h = 1

        self._build_ui()
        self._bind_keys()

        if self.images:
            # Open first image without annotation
            unannotated = [i for i, p in enumerate(self.images)
                           if not os.path.exists(txt_for_image(p))]
            self.current_idx = unannotated[0] if unannotated else 0
            self._load_image(self.current_idx)
        else:
            messagebox.showinfo("No Images", "No images found in the selected folder.")

        self._update_summary()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top toolbar ──────────────────────────────────────────────────────
        toolbar = tk.Frame(self, bg="#2C2C2E", pady=4)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        btn_cfg = dict(bg="#3A3A3C", fg="white", relief=tk.FLAT,
                       padx=10, pady=4, cursor="hand2", font=("Helvetica", 11))

        tk.Button(toolbar, text="📂 Open Folder", command=self._open_folder,
                  **btn_cfg).pack(side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="💾 Save  (S)", command=self._save,
                  **btn_cfg).pack(side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="⟵ Prev  (A)", command=self._prev,
                  **btn_cfg).pack(side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="Next ⟶  (D)", command=self._next,
                  **btn_cfg).pack(side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="🗑 Delete Box (Del)", command=self._delete_selected,
                  **btn_cfg).pack(side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="📋 Copy Box (C)", command=self._copy_box,
                  **btn_cfg).pack(side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="📌 Paste Box (V)", command=self._paste_box,
                  **btn_cfg).pack(side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="🔍 Jump to Unannotated",
                  command=self._jump_to_unannotated, **btn_cfg).pack(side=tk.LEFT, padx=4)
        tk.Button(toolbar, text="📊 Summary", command=self._show_summary,
                  **btn_cfg).pack(side=tk.LEFT, padx=4)
        self._film_btn = tk.Button(toolbar, text="🎞 Filmstrip: OFF",
                  command=self._toggle_filmstrip, **btn_cfg)
        self._film_btn.pack(side=tk.LEFT, padx=4)

        # zoom
        tk.Label(toolbar, text="Zoom:", bg="#2C2C2E", fg="#AEAEB2",
                 font=("Helvetica", 11)).pack(side=tk.LEFT, padx=(16, 2))
        self._zoom_var = tk.StringVar(value="Fit")
        zoom_menu = ttk.Combobox(toolbar, textvariable=self._zoom_var,
                                 values=["Fit", "50%", "75%", "100%", "150%", "200%"],
                                 width=6, state="readonly")
        zoom_menu.pack(side=tk.LEFT, padx=4)
        zoom_menu.bind("<<ComboboxSelected>>", lambda e: self._redraw())

        self._status_var = tk.StringVar(value="Ready")
        tk.Label(toolbar, textvariable=self._status_var, bg="#2C2C2E", fg="#AEAEB2",
                 font=("Helvetica", 11)).pack(side=tk.RIGHT, padx=12)

        # ── Main area ─────────────────────────────────────────────────────────
        self._main_frame = tk.Frame(self, bg="#1C1C1E")
        self._main_frame.pack(fill=tk.BOTH, expand=True)
        main = self._main_frame

        # Canvas
        canvas_frame = tk.Frame(main, bg="#000")
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="#000", cursor="crosshair",
                                highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # ── Right panel ───────────────────────────────────────────────────────
        right = tk.Frame(main, bg="#2C2C2E", width=230)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        # Image info
        tk.Label(right, text="IMAGE INFO", bg="#2C2C2E", fg="#8E8E93",
                 font=("Helvetica", 10, "bold")).pack(pady=(12, 2), anchor="w", padx=10)
        self._img_info_var = tk.StringVar(value="—")
        tk.Label(right, textvariable=self._img_info_var, bg="#2C2C2E", fg="white",
                 font=("Helvetica", 10), wraplength=210, justify=tk.LEFT
                 ).pack(anchor="w", padx=10)

        tk.Frame(right, bg="#3A3A3C", height=1).pack(fill=tk.X, pady=8)

        # Class selector
        tk.Label(right, text="ACTIVE CLASS", bg="#2C2C2E", fg="#8E8E93",
                 font=("Helvetica", 10, "bold")).pack(pady=(0, 4), anchor="w", padx=10)
        self._class_var = tk.IntVar(value=0)
        self._class_listbox = tk.Listbox(right, selectmode=tk.SINGLE, height=12,
                                         bg="#3A3A3C", fg="white",
                                         selectbackground="#007AFF",
                                         font=("Helvetica", 11),
                                         relief=tk.FLAT, bd=0)
        for i, cls in enumerate(self.classes):
            self._class_listbox.insert(tk.END, f"  {i}: {cls}")
        self._class_listbox.select_set(0)
        self._class_listbox.pack(fill=tk.X, padx=8)

        tk.Frame(right, bg="#3A3A3C", height=1).pack(fill=tk.X, pady=8)

        # Box list
        tk.Label(right, text="ANNOTATIONS", bg="#2C2C2E", fg="#8E8E93",
                 font=("Helvetica", 10, "bold")).pack(pady=(0, 4), anchor="w", padx=10)
        box_list_frame = tk.Frame(right, bg="#2C2C2E")
        box_list_frame.pack(fill=tk.BOTH, expand=True, padx=8)

        sb = tk.Scrollbar(box_list_frame)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._box_listbox = tk.Listbox(box_list_frame, yscrollcommand=sb.set,
                                        bg="#3A3A3C", fg="white",
                                        selectbackground="#007AFF",
                                        font=("Helvetica", 10),
                                        relief=tk.FLAT, bd=0)
        self._box_listbox.pack(fill=tk.BOTH, expand=True)
        sb.config(command=self._box_listbox.yview)
        self._box_listbox.bind("<<ListboxSelect>>", self._on_box_list_select)

        # Change class button
        tk.Button(right, text="✏️ Change Class of Selected",
                  command=self._change_class,
                  bg="#3A3A3C", fg="white", relief=tk.FLAT,
                  padx=8, pady=4, cursor="hand2",
                  font=("Helvetica", 10)).pack(fill=tk.X, padx=8, pady=4)

        # Summary area
        tk.Frame(right, bg="#3A3A3C", height=1).pack(fill=tk.X, pady=4)
        tk.Label(right, text="DATASET SUMMARY", bg="#2C2C2E", fg="#8E8E93",
                 font=("Helvetica", 10, "bold")).pack(anchor="w", padx=10)
        self._summary_var = tk.StringVar(value="")
        tk.Label(right, textvariable=self._summary_var, bg="#2C2C2E", fg="#AEAEB2",
                 font=("Helvetica", 10), wraplength=210, justify=tk.LEFT
                 ).pack(anchor="w", padx=10, pady=(2, 10))

        # ── Bottom filmstrip (hidden by default) ─────────────────────────────
        self._film_frame = tk.Frame(self, bg="#1C1C1E", height=80)
        # NOT packed yet — starts hidden; toggle with F key or button
        self._film_frame.pack_propagate(False)

        self._film_canvas = tk.Canvas(self._film_frame, bg="#1C1C1E",
                                       height=80, highlightthickness=0)
        self._film_canvas.pack(fill=tk.X)
        self._film_canvas.bind("<Button-1>", self._film_click)
        self._film_thumbs = []  # [(PhotoImage, x_center)]

        # Canvas bindings
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Configure>", lambda e: self._redraw())

    def _bind_keys(self):
        self.bind("<s>", lambda e: self._save())
        self.bind("<a>", lambda e: self._prev())
        self.bind("<d>", lambda e: self._next())
        self.bind("<Delete>", lambda e: self._delete_selected())
        self.bind("<BackSpace>", lambda e: self._delete_selected())
        self.bind("<Escape>", lambda e: self._deselect())
        self.bind("<c>", lambda e: self._copy_box())
        self.bind("<v>", lambda e: self._paste_box())
        self.bind("<f>", lambda e: self._toggle_filmstrip())
        # Number keys to quickly switch class
        for i in range(min(10, len(self.classes))):
            self.bind(str(i), lambda e, idx=i: self._quick_class(idx))

    # ── Navigation ─────────────────────────────────────────────────────────────

    def _prompt_save_if_dirty(self):
        if self.dirty:
            ans = messagebox.askyesnocancel("Unsaved Changes",
                                             "Save changes before leaving?")
            if ans is None:
                return False   # cancel
            if ans:
                self._save()
        return True

    def _load_image(self, idx):
        if not self.images:
            return
        self.current_idx = idx
        img_path = self.images[idx]
        img = Image.open(img_path)
        self._orig_w, self._orig_h = img.size
        self._img = img
        self.boxes = load_annotations(txt_for_image(img_path), self._orig_w, self._orig_h)
        self.selected_box = None
        self.dirty = False
        self._update_box_listbox()
        self._redraw()
        self._update_status()
        self._update_image_info(img_path)
        self._update_filmstrip()

    def _prev(self):
        if not self._prompt_save_if_dirty():
            return
        if self.current_idx > 0:
            self._load_image(self.current_idx - 1)

    def _next(self):
        if not self._prompt_save_if_dirty():
            return
        if self.current_idx < len(self.images) - 1:
            self._load_image(self.current_idx + 1)

    def _jump_to_unannotated(self):
        if not self._prompt_save_if_dirty():
            return
        unannotated = [i for i, p in enumerate(self.images)
                       if not os.path.exists(txt_for_image(p))]
        if not unannotated:
            messagebox.showinfo("All Done", "All images have annotation files! 🎉")
            return
        self._load_image(unannotated[0])

    def _open_folder(self):
        if not self._prompt_save_if_dirty():
            return
        folder = filedialog.askdirectory(title="Select Image Folder")
        if folder:
            self.image_dir = folder
            self.images = find_images(folder)
            self.current_idx = 0
            if self.images:
                unannotated = [i for i, p in enumerate(self.images)
                               if not os.path.exists(txt_for_image(p))]
                self.current_idx = unannotated[0] if unannotated else 0
                self._load_image(self.current_idx)
            self._update_summary()

    # ── Save ───────────────────────────────────────────────────────────────────

    def _save(self):
        if not self.images:
            return
        img_path = self.images[self.current_idx]
        txt_path = txt_for_image(img_path)
        save_annotations(txt_path, self.boxes, self._orig_w, self._orig_h)
        self.dirty = False
        self._update_status()
        self._update_summary()
        self._update_filmstrip()

    # ── Box operations ─────────────────────────────────────────────────────────

    def _delete_selected(self):
        if self.selected_box is not None and self.selected_box < len(self.boxes):
            self.boxes.pop(self.selected_box)
            self.selected_box = None
            self.dirty = True
            self._update_box_listbox()
            self._redraw()

    def _deselect(self):
        self.selected_box = None
        self._box_listbox.selection_clear(0, tk.END)
        self._redraw()

    def _change_class(self):
        if self.selected_box is None:
            return
        sel = self._class_listbox.curselection()
        if sel:
            new_cls = sel[0]
            self.boxes[self.selected_box][0] = new_cls
            self.dirty = True
            self._update_box_listbox()
            self._redraw()

    def _quick_class(self, idx):
        self._class_listbox.selection_clear(0, tk.END)
        self._class_listbox.select_set(idx)
        if self.selected_box is not None:
            self._change_class()

    def _copy_box(self):
        """Copy the selected box to clipboard (with small offset for paste)."""
        if self.selected_box is None or self.selected_box >= len(self.boxes):
            return
        self._clipboard_box = list(self.boxes[self.selected_box])  # shallow copy
        cls = self._clipboard_box[0]
        label = self.classes[cls] if cls < len(self.classes) else str(cls)
        self._status_var.set(f"Copied: {label} box")

    def _paste_box(self):
        """Paste clipboard box with a small offset so it's visible."""
        if self._clipboard_box is None:
            return
        OFFSET = 20  # px offset so paste doesn't stack exactly on original
        cls, x1, y1, x2, y2 = self._clipboard_box
        nx1 = min(x1 + OFFSET, self._orig_w - abs(x2 - x1))
        ny1 = min(y1 + OFFSET, self._orig_h - abs(y2 - y1))
        nx2 = nx1 + abs(x2 - x1)
        ny2 = ny1 + abs(y2 - y1)
        new_box = [cls, nx1, ny1, nx2, ny2]
        self.boxes.append(new_box)
        self.selected_box = len(self.boxes) - 1
        # Update clipboard to the new position so repeated pastes cascade
        self._clipboard_box = list(new_box)
        self.dirty = True
        self._update_box_listbox()
        self._redraw()

    def _toggle_filmstrip(self):
        """Show/hide the filmstrip panel; F key or toolbar button."""
        self._filmstrip_visible = not self._filmstrip_visible
        if self._filmstrip_visible:
            self._film_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self._main_frame)
            self._film_btn.config(text="🎞 Filmstrip: ON")
            self._update_filmstrip()
        else:
            self._film_frame.pack_forget()
            self._film_btn.config(text="🎞 Filmstrip: OFF")
        self._redraw()

    def _active_class(self):
        sel = self._class_listbox.curselection()
        return sel[0] if sel else 0

    # ── Canvas drawing ─────────────────────────────────────────────────────────

    def _img_to_canvas(self, x, y):
        return x * self._scale + self._offset_x, y * self._scale + self._offset_y

    def _canvas_to_img(self, cx, cy):
        return (cx - self._offset_x) / self._scale, (cy - self._offset_y) / self._scale

    def _redraw(self):
        self.canvas.delete("all")
        if not hasattr(self, "_img"):
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 2 or ch < 2:
            return

        zoom = self._zoom_var.get()
        if zoom == "Fit":
            sx = cw / self._orig_w
            sy = ch / self._orig_h
            self._scale = min(sx, sy)
        else:
            self._scale = int(zoom.replace("%", "")) / 100.0

        dw = int(self._orig_w * self._scale)
        dh = int(self._orig_h * self._scale)
        self._offset_x = (cw - dw) // 2
        self._offset_y = (ch - dh) // 2

        resized = self._img.resize((dw, dh), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(resized)
        self.canvas.create_image(self._offset_x, self._offset_y,
                                  anchor=tk.NW, image=self._photo)

        # Draw boxes
        for i, (cls, x1, y1, x2, y2) in enumerate(self.boxes):
            color = BOX_COLORS[cls % len(BOX_COLORS)]
            cx1, cy1 = self._img_to_canvas(x1, y1)
            cx2, cy2 = self._img_to_canvas(x2, y2)
            width = 3 if i == self.selected_box else 2
            dash = () if i == self.selected_box else (4, 3)
            self.canvas.create_rectangle(cx1, cy1, cx2, cy2,
                                          outline=color, width=width,
                                          dash=dash, tags=f"box_{i}")
            # Label
            label = self.classes[cls] if cls < len(self.classes) else str(cls)
            self.canvas.create_rectangle(cx1, cy1 - 18, cx1 + len(label) * 7 + 6, cy1,
                                          fill=color, outline="")
            self.canvas.create_text(cx1 + 3, cy1 - 9, text=label,
                                     fill="white", anchor=tk.W,
                                     font=("Helvetica", 9, "bold"))
            # Resize handles if selected
            if i == self.selected_box:
                for hx, hy in [(cx1, cy1), (cx2, cy1), (cx1, cy2), (cx2, cy2)]:
                    self.canvas.create_rectangle(hx - 5, hy - 5, hx + 5, hy + 5,
                                                  fill=color, outline="white",
                                                  tags=f"handle_{i}")

    # ── Mouse interaction ──────────────────────────────────────────────────────

    def _hit_test_handle(self, cx, cy):
        """Returns (box_idx, handle_name) or None."""
        if self.selected_box is None:
            return None
        i = self.selected_box
        cls, x1, y1, x2, y2 = self.boxes[i]
        corners = {
            "tl": (x1, y1), "tr": (x2, y1),
            "bl": (x1, y2), "br": (x2, y2),
        }
        for name, (ix, iy) in corners.items():
            cx2, cy2 = self._img_to_canvas(ix, iy)
            if abs(cx - cx2) < 8 and abs(cy - cy2) < 8:
                return i, name
        return None

    def _hit_test_box(self, cx, cy):
        """Returns box index or None."""
        ix, iy = self._canvas_to_img(cx, cy)
        # Iterate in reverse so topmost (last drawn) wins
        for i in range(len(self.boxes) - 1, -1, -1):
            _, x1, y1, x2, y2 = self.boxes[i]
            if min(x1, x2) <= ix <= max(x1, x2) and min(y1, y2) <= iy <= max(y1, y2):
                return i
        return None

    def _on_canvas_press(self, event):
        cx, cy = event.x, event.y
        # Check resize handle
        handle = self._hit_test_handle(cx, cy)
        if handle:
            self._resize_handle = handle
            return
        # Check box click
        hit = self._hit_test_box(cx, cy)
        if hit is not None:
            self.selected_box = hit
            self._drag_box_idx = hit
            ix, iy = self._canvas_to_img(cx, cy)
            _, x1, y1, _, _ = self.boxes[hit]
            self._drag_offset = (ix - x1, iy - y1)
            self._box_listbox.selection_clear(0, tk.END)
            self._box_listbox.select_set(hit)
            self._redraw()
            return
        # Start drawing new box
        self.selected_box = None
        self._drag_box_idx = None
        self._draw_start = self._canvas_to_img(cx, cy)
        self._draw_rect_id = None
        self._box_listbox.selection_clear(0, tk.END)
        self._redraw()

    def _on_canvas_drag(self, event):
        cx, cy = event.x, event.y
        # Resize
        if self._resize_handle is not None:
            box_idx, handle = self._resize_handle
            ix, iy = self._canvas_to_img(cx, cy)
            ix = max(0, min(ix, self._orig_w))
            iy = max(0, min(iy, self._orig_h))
            cls, x1, y1, x2, y2 = self.boxes[box_idx]
            if "l" in handle:
                x1 = ix
            if "r" in handle:
                x2 = ix
            if "t" in handle:
                y1 = iy
            if "b" in handle:
                y2 = iy
            self.boxes[box_idx] = [cls, x1, y1, x2, y2]
            self.dirty = True
            self._redraw()
            return
        # Move existing box
        if self._drag_box_idx is not None:
            ix, iy = self._canvas_to_img(cx, cy)
            ox, oy = self._drag_offset
            cls, x1, y1, x2, y2 = self.boxes[self._drag_box_idx]
            bw, bh = x2 - x1, y2 - y1
            nx1 = max(0, min(ix - ox, self._orig_w - bw))
            ny1 = max(0, min(iy - oy, self._orig_h - bh))
            self.boxes[self._drag_box_idx] = [cls, nx1, ny1, nx1 + bw, ny1 + bh]
            self.dirty = True
            self._redraw()
            return
        # Drawing new box
        if self._draw_start:
            # Remove old rubber band
            if self._draw_rect_id:
                self.canvas.delete(self._draw_rect_id)
            sx, sy = self._img_to_canvas(*self._draw_start)
            self._draw_rect_id = self.canvas.create_rectangle(
                sx, sy, cx, cy,
                outline=BOX_COLORS[self._active_class() % len(BOX_COLORS)],
                width=2, dash=(4, 3))

    def _on_canvas_release(self, event):
        cx, cy = event.x, event.y
        # Finish resize
        if self._resize_handle is not None:
            self._resize_handle = None
            self._update_box_listbox()
            return
        # Finish move
        if self._drag_box_idx is not None:
            self._drag_box_idx = None
            self._drag_offset = None
            self._update_box_listbox()
            return
        # Finish new box
        if self._draw_start:
            if self._draw_rect_id:
                self.canvas.delete(self._draw_rect_id)
            ex, ey = self._canvas_to_img(cx, cy)
            sx, sy = self._draw_start
            self._draw_start = None
            self._draw_rect_id = None
            # Clamp
            x1, x2 = sorted([max(0, min(sx, self._orig_w)),
                              max(0, min(ex, self._orig_w))])
            y1, y2 = sorted([max(0, min(sy, self._orig_h)),
                              max(0, min(ey, self._orig_h))])
            if (x2 - x1) < MIN_BOX_PX or (y2 - y1) < MIN_BOX_PX:
                return
            cls = self._active_class()
            self.boxes.append([cls, x1, y1, x2, y2])
            self.selected_box = len(self.boxes) - 1
            self.dirty = True
            self._update_box_listbox()
            self._redraw()

    def _on_canvas_motion(self, event):
        cx, cy = event.x, event.y
        # Change cursor based on context
        handle = self._hit_test_handle(cx, cy)
        if handle:
            corner = handle[1]
            cursors = {"tl": "size_nw_se", "br": "size_nw_se",
                       "tr": "size_ne_sw", "bl": "size_ne_sw"}
            try:
                self.canvas.config(cursor=cursors.get(corner, "crosshair"))
            except Exception:
                pass
        elif self._hit_test_box(cx, cy) is not None:
            self.canvas.config(cursor="fleur")
        else:
            self.canvas.config(cursor="crosshair")
        # Coord display
        if hasattr(self, "_orig_w"):
            ix, iy = self._canvas_to_img(cx, cy)
            ix = max(0, min(int(ix), self._orig_w))
            iy = max(0, min(int(iy), self._orig_h))
            self._status_var.set(f"x={ix}  y={iy}")

    # ── Box listbox ────────────────────────────────────────────────────────────

    def _update_box_listbox(self):
        self._box_listbox.delete(0, tk.END)
        for i, (cls, x1, y1, x2, y2) in enumerate(self.boxes):
            label = self.classes[cls] if cls < len(self.classes) else str(cls)
            w = int(abs(x2 - x1))
            h = int(abs(y2 - y1))
            self._box_listbox.insert(tk.END, f" #{i+1}  {label}  [{w}×{h}]")
        if self.selected_box is not None and self.selected_box < len(self.boxes):
            self._box_listbox.select_set(self.selected_box)

    def _on_box_list_select(self, event):
        sel = self._box_listbox.curselection()
        if sel:
            self.selected_box = sel[0]
            self._redraw()

    # ── Info / status ──────────────────────────────────────────────────────────

    def _update_status(self):
        if not self.images:
            return
        img_path = self.images[self.current_idx]
        fname = os.path.basename(img_path)
        dirty_mark = " ●" if self.dirty else ""
        annotated = "✓" if os.path.exists(txt_for_image(img_path)) else "✗"
        self.title(f"YOLO Annotator — {fname}{dirty_mark}")
        self._status_var.set(
            f"{self.current_idx + 1}/{len(self.images)}  [{annotated}]{dirty_mark}")

    def _update_image_info(self, img_path):
        fname = os.path.basename(img_path)
        has_ann = "Yes ✓" if os.path.exists(txt_for_image(img_path)) else "No ✗"
        size_kb = os.path.getsize(img_path) // 1024
        self._img_info_var.set(
            f"{fname}\n"
            f"{self._orig_w}×{self._orig_h}px\n"
            f"{size_kb} KB\n"
            f"Annotated: {has_ann}\n"
            f"Boxes: {len(self.boxes)}\n"
            f"Idx: {self.current_idx + 1}/{len(self.images)}"
        )

    def _update_summary(self):
        total = len(self.images)
        annotated = sum(1 for p in self.images if os.path.exists(txt_for_image(p)))
        unannotated = total - annotated
        pct = int(annotated / total * 100) if total else 0
        self._summary_var.set(
            f"Total images: {total}\n"
            f"Annotated: {annotated} ({pct}%)\n"
            f"Unannotated: {unannotated}\n"
            f"Folder: …/{os.path.basename(self.image_dir)}"
        )

    def _show_summary(self):
        total = len(self.images)
        annotated = sum(1 for p in self.images if os.path.exists(txt_for_image(p)))
        unannotated = total - annotated

        # Count total boxes across all annotation files
        total_boxes = 0
        class_counts = {c: 0 for c in self.classes}
        for img_path in self.images:
            txt = txt_for_image(img_path)
            if os.path.exists(txt):
                with open(txt) as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) == 5:
                            total_boxes += 1
                            cls = int(parts[0])
                            if cls < len(self.classes):
                                class_counts[self.classes[cls]] = \
                                    class_counts.get(self.classes[cls], 0) + 1

        lines = [
            f"📁 Folder: {self.image_dir}",
            f"🖼  Total images   : {total}",
            f"✅  Annotated      : {annotated}",
            f"❌  Unannotated    : {unannotated}",
            f"📦  Total boxes    : {total_boxes}",
            "",
            "── Per-class box counts ──",
        ]
        for cls, cnt in class_counts.items():
            lines.append(f"  {cls:15s}: {cnt}")

        messagebox.showinfo("Dataset Summary", "\n".join(lines))

    # ── Filmstrip ──────────────────────────────────────────────────────────────

    def _update_filmstrip(self):
        if not self._filmstrip_visible:
            return
        self._film_thumbs = []
        THUMB_W, THUMB_H, PAD = 100, 68, 6
        x = PAD
        for i, img_path in enumerate(self.images):
            try:
                thumb = Image.open(img_path)
                thumb.thumbnail((THUMB_W, THUMB_H))
                photo = ImageTk.PhotoImage(thumb)
                self._film_thumbs.append((photo, x + THUMB_W // 2))
                self._film_canvas.create_image(x, 6, anchor=tk.NW, image=photo)
            except Exception:
                self._film_thumbs.append((None, x + THUMB_W // 2))

            # Highlight current
            color = "#007AFF" if i == self.current_idx else "#444"
            self._film_canvas.create_rectangle(
                x - 2, 4, x + THUMB_W + 2, THUMB_H + 8,
                outline=color, width=3 if i == self.current_idx else 1)

            # Annotated indicator
            dot_color = "#34C759" if os.path.exists(txt_for_image(img_path)) else "#FF3B30"
            self._film_canvas.create_oval(
                x + THUMB_W - 12, 8, x + THUMB_W - 4, 16, fill=dot_color, outline="")

            x += THUMB_W + PAD
        self._film_canvas.config(scrollregion=(0, 0, x, 80))

    def _film_click(self, event):
        THUMB_W, PAD = 100, 6
        idx = event.x // (THUMB_W + PAD)
        if 0 <= idx < len(self.images):
            if not self._prompt_save_if_dirty():
                return
            self._load_image(idx)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    root_pick = tk.Tk()
    root_pick.withdraw()

    # Pick data.yaml
    yaml_path = filedialog.askopenfilename(
        title="Select data.yaml (or cancel to use defaults)",
        filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")]
    )

    classes = ["object"]
    if yaml_path and os.path.exists(yaml_path):
        try:
            classes = load_classes(yaml_path)
        except Exception as e:
            messagebox.showerror("YAML Error", str(e))

    # Pick image folder
    image_dir = filedialog.askdirectory(title="Select Image Folder")
    if not image_dir:
        messagebox.showinfo("Cancelled", "No folder selected. Exiting.")
        root_pick.destroy()
        return

    root_pick.destroy()

    app = AnnotatorApp(image_dir, classes)
    app.mainloop()


if __name__ == "__main__":
    main()
