#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata


DEFAULT_RESOLUTIONS = "1920x1080, 2560x1440"


def wallpaper_directory() -> Path:
    """Respect XDG_DATA_HOME; normally /home/fedora/.local/share/wallpapers."""
    data_home = os.environ.get("XDG_DATA_HOME", "")
    base = Path(data_home) if data_home and Path(data_home).is_absolute() else Path.home() / ".local/share"
    return base / "wallpapers"


def folder_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", normalized).strip("-_")[:80] or "wallpaper"


def parse_resolutions(value: str) -> list[tuple[int, int] | None]:
    """None means the original (EXIF-oriented) size of each source image."""
    sizes = []
    for item in value.split(","):
        item = item.strip().lower()
        if item == "original":
            size = None
        else:
            match = re.fullmatch(r"([1-9][0-9]*)\s*[x×]\s*([1-9][0-9]*)", item)
            if not match:
                raise ValueError("Enter sizes such as 1920x1080, 2560x1440, or original.")
            size = (int(match[1]), int(match[2]))
            # Bound allocations from a mistyped resolution before creating images.
            if size[0] * size[1] > 50_000_000:
                raise ValueError("Each output resolution must be at most 50 megapixels.")
        if size not in sizes:
            sizes.append(size)
    return sizes


def create_package(
    light: Path,
    dark: Path,
    name: str,
    output: Path,
    resolutions: str = DEFAULT_RESOLUTIONS,
    fit: str = "crop",
) -> Path:
    """Create a new package. Existing folders are never replaced.

    Images are rendered into a temporary folder first. A failed export leaves
    no partial wallpaper package in the destination.
    """
    from PIL import Image, ImageOps

    name = " ".join(name.split())
    if not name:
        raise ValueError("Please enter a wallpaper name.")
    if fit not in {"crop", "contain"}:
        raise ValueError("Image fit must be crop or contain.")
    sizes = parse_resolutions(resolutions)
    output = Path(output).expanduser().resolve()
    target = output / folder_name(name)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"This folder already exists:\n{target}\n\nChoose a different wallpaper name or output folder.")

    sources = []
    try:
        for label, path in (("Light", light), ("Dark", dark)):
            path = Path(path).expanduser()
            if not path.is_file():
                raise ValueError(f"Choose a valid {label.lower()} image.")
            try:
                with Image.open(path) as source:
                    if getattr(source, "is_animated", False):
                        raise ValueError("Choose a still image; animated wallpapers are not supported.")
                    oriented = ImageOps.exif_transpose(source)
                    rgba = oriented.convert("RGBA")
                    image = Image.new("RGB", rgba.size, "white")
                    image.paste(rgba, mask=rgba.getchannel("A"))
                    sources.append(image)
            except (OSError, Image.DecompressionBombError) as error:
                raise ValueError(f"Cannot read the {label.lower()} image:\n{path}\n\n{error}") from error

        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".wallpaper-export-", dir=output) as temporary:
            staging = Path(temporary)
            for subdir, image in zip(("images", "images_dark"), sources):
                destination = staging / "contents" / subdir
                destination.mkdir(parents=True)
                for requested in sizes:
                    size = requested or image.size
                    if size == image.size:
                        rendered = image
                    elif fit == "crop":
                        rendered = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
                    else:
                        rendered = ImageOps.pad(image, size, method=Image.Resampling.LANCZOS, color="black")
                    try:
                        rendered.save(destination / f"{size[0]}x{size[1]}.jpg", quality=95, subsampling=0)
                    finally:
                        if rendered is not image:
                            rendered.close()

            metadata = {"KPlugin": {"Id": target.name, "Name": name, "Description": "Light and dark wallpaper"}}
            (staging / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
            desktop_name = name.replace("\\", "\\\\")
            (staging / "metadata.desktop").write_text(
                "[Desktop Entry]\n"
                f"Name={desktop_name}\n"
                "Comment=Light and dark wallpaper\n"
                "Icon=preferences-desktop-wallpaper\n"
                f"X-KDE-PluginInfo-Name={target.name}\n",
                encoding="utf-8",
            )

            # Reserve the destination exclusively, including when two exports race.
            target.mkdir()
            try:
                for child in staging.iterdir():
                    shutil.move(str(child), target / child.name)
            except BaseException:
                shutil.rmtree(target)
                raise
        return target
    finally:
        for image in sources:
            image.close()


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        from PIL import Image, ImageOps, ImageTk
    except ImportError as error:
        print(
            f"Missing GUI dependency: {error}\n\n"
            "On Fedora, install the dependencies with:\n"
            "  sudo dnf install python3-tkinter python3-pillow\n"
            "Then run: python3 kde_wallpaper_set.py",
            file=sys.stderr,
        )
        return 1

    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(f"Cannot open the GUI: {error}\nRun this script inside your desktop session.", file=sys.stderr)
        return 1

    root.title("KDE Light & Dark Wallpaper")
    root.minsize(680, 620)
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("Title.TLabel", font=("sans-serif", 16, "bold"))
    style.configure("Create.TButton", padding=(16, 9))

    frame = ttk.Frame(root, padding=20)
    frame.grid(sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    ttk.Label(frame, text="Make a light&dark wallpaper", style="Title.TLabel").grid(row=0, columnspan=2, sticky="w")
    ttk.Label(frame, text="Choose two pictures. KDE can switch between them with your theme.").grid(row=1, columnspan=2, sticky="w", pady=(5, 15))

    paths = {variant: tk.StringVar() for variant in ("light", "dark")}
    previews = {}
    preview_labels = {}
    controls = []
    name = tk.StringVar(value="My Wallpaper")
    output = tk.StringVar(value=str(wallpaper_directory()))
    resolutions = tk.StringVar(value=DEFAULT_RESOLUTIONS)
    fitting = tk.StringVar(value="Crop to fill")
    status = tk.StringVar(value="Select a light image and a dark image to begin.")
    result_queue = queue.Queue()
    created = None

    def choose_image(variant):
        selected = filedialog.askopenfilename(
            parent=root,
            title=f"Choose {variant} wallpaper",
            filetypes=[("Pictures", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"), ("All files", "*")],
        )
        if not selected:
            return
        try:
            with Image.open(selected) as source:
                if getattr(source, "is_animated", False):
                    raise ValueError("Please choose a still image.")
                preview = ImageOps.exif_transpose(source)
                size = preview.size
                preview.thumbnail((280, 160), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(preview)
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            messagebox.showerror("Cannot use this picture", str(error), parent=root)
            return
        paths[variant].set(selected)
        previews[variant] = photo
        preview_labels[variant].configure(image=photo, text="")
        status.set(f"Selected {variant} image: {size[0]} × {size[1]} pixels")

    for column, variant in enumerate(("light", "dark")):
        card = ttk.LabelFrame(frame, text=f"{variant.title()} picture", padding=10)
        card.grid(row=2, column=column, sticky="nsew", padx=(0, 8) if column == 0 else (8, 0))
        card.columnconfigure(0, weight=1)
        preview_labels[variant] = ttk.Label(card, text="No picture selected", anchor="center")
        preview_labels[variant].grid(row=0, sticky="nsew", pady=(5, 10))
        card.rowconfigure(0, minsize=170)
        ttk.Entry(card, textvariable=paths[variant], state="readonly", width=30).grid(row=1, sticky="ew", pady=(0, 8))
        button = ttk.Button(card, text=f"Choose {variant} picture…", command=lambda variant=variant: choose_image(variant))
        button.grid(row=2, sticky="ew")
        controls.append(button)

    settings = ttk.Frame(frame)
    settings.grid(row=3, columnspan=2, sticky="ew", pady=(15, 0))
    settings.columnconfigure(1, weight=1)
    for row, (label, variable) in enumerate((("Wallpaper name", name), ("Output parent folder", output), ("Resolutions", resolutions))):
        ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
        entry = ttk.Entry(settings, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        controls.append(entry)

    def choose_output():
        selected = filedialog.askdirectory(parent=root, title="Choose output parent folder", mustexist=True)
        if selected:
            output.set(selected)

    browse = ttk.Button(settings, text="Browse…", command=choose_output)
    browse.grid(row=1, column=2, padx=(8, 0))
    controls.append(browse)
    ttk.Label(settings, text="Comma-separated sizes, or original to keep the source dimensions.").grid(row=3, column=1, columnspan=2, sticky="w")
    ttk.Label(settings, text="Image fit").grid(row=4, column=0, sticky="w", pady=(10, 5))
    fit_box = ttk.Combobox(settings, textvariable=fitting, values=("Crop to fill", "Fit with black borders"), state="readonly")
    fit_box.grid(row=4, column=1, sticky="ew", pady=(10, 5))
    controls.append(fit_box)
    ttk.Label(settings, text="Crop trims edges to fill each size. Larger sizes may upscale the picture.").grid(row=5, columnspan=3, sticky="w")
    folder_label = ttk.Label(settings, wraplength=620)
    folder_label.grid(row=6, columnspan=3, sticky="w", pady=(8, 0))

    def update_folder(*_):
        folder_label.configure(text=f"Package folder: {Path(output.get()).expanduser() / folder_name(name.get())}")

    name.trace_add("write", update_folder)
    output.trace_add("write", update_folder)
    update_folder()


    def poll_result():
        nonlocal created
        try:
            succeeded, value = result_queue.get_nowait()
        except queue.Empty:
            root.after(100, poll_result)
            return
        root.configure(cursor="")
        for control in controls:
            control.configure(state="readonly" if control is fit_box else "normal")
        if not succeeded:
            status.set("Could not create the wallpaper folder.")
            messagebox.showerror("Export failed", str(value), parent=root)
            return
        created = value
        status.set("Wallpaper folder created successfully.")
        installed = created.parent == wallpaper_directory().resolve()
        instruction = "The package is in KDE's wallpaper folder.\n" if installed else f"Copy the whole {created.name} folder into:\n{wallpaper_directory()}\n"
        open_button.configure(state="normal")

    def create():
        if not paths["light"].get() or not paths["dark"].get():
            messagebox.showerror("Choose both pictures", "Select a light picture and a dark picture first.", parent=root)
            return
        if not name.get().strip() or not output.get().strip():
            messagebox.showerror("Missing setting", "Enter a wallpaper name and an output folder.", parent=root)
            return
        try:
            parse_resolutions(resolutions.get())
        except ValueError as error:
            messagebox.showerror("Invalid resolutions", str(error), parent=root)
            return
        arguments = (Path(paths["light"].get()), Path(paths["dark"].get()), name.get(), Path(output.get()), resolutions.get(), "crop" if fitting.get() == "Crop to fill" else "contain")
        for control in controls:
            control.configure(state="disabled")
        open_button.configure(state="disabled")
        root.configure(cursor="watch")
        status.set("Creating wallpaper folder…")

        def worker():
            try:
                result_queue.put((True, create_package(*arguments)))
            except Exception as error:
                result_queue.put((False, error))

        threading.Thread(target=worker).start()
        root.after(100, poll_result)

    actions = ttk.Frame(frame)
    actions.grid(row=4, columnspan=2, sticky="ew", pady=(16, 8))
    create_button = ttk.Button(actions, text="Create wallpaper folder", style="Create.TButton", command=create)
    create_button.pack(side="left")
    controls.append(create_button)

    def open_folder():
        if created:
            try:
                subprocess.Popen(["xdg-open", str(created)])
            except OSError as error:
                messagebox.showerror("Cannot open folder", str(error), parent=root)

    open_button = ttk.Button(actions, text="Open created folder", command=open_folder, state="disabled")
    open_button.pack(side="right")
    ttk.Label(frame, textvariable=status, wraplength=620).grid(row=5, columnspan=2, sticky="w", pady=(2, 8))
    frame.rowconfigure(6, weight=1)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
