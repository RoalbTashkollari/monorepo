# KDE wallpaper theme with light and dark variants

A small Tkinter application for creating a KDE wallpaper package from two images:

- a light theme image
- a dark theme image

## Requirements

- Linux with a graphical desktop session
- Python 3
- Tkinter
- Pillow
- KDE Plasma 5.26 or newer for automatic light/dark theme switching

## Install

From this directory, run:

```bash
./install.sh
```

The installer creates a local `.venv` directory and installs Pillow into it. On Fedora, if Tkinter is missing, install it with:

```bash
sudo dnf install python3-tkinter
```

On Debian or Ubuntu:

```bash
sudo apt install python3-tk
```

Then run `./install.sh` again.

## Run

```bash
.venv/bin/python kde_light_dark.py
```

Choose the light and dark images, enter a wallpaper name, select the output folder, and click **Create wallpaper folder**. The default output folder is:

```text
~/.local/share/wallpapers
```

After export, open KDE's Desktop and Wallpaper settings and select the new package. Choose switching based on the light/dark theme when that option is available.

## Notes

- Supported source formats are PNG, JPEG, WebP, BMP, and TIFF.
- Animated images are not supported.
- Resolutions are entered as comma-separated values, for example `1920x1080, 2560x1440`.
- Use `original` to preserve each source image's dimensions.
- Existing wallpaper package folders are never overwritten.
