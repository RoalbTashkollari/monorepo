#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
venv_dir="${project_dir}/.venv"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required." >&2
    exit 1
fi

python3 -m venv "${venv_dir}"
"${venv_dir}/bin/python" -m pip install --upgrade pip
"${venv_dir}/bin/python" -m pip install -r "${project_dir}/requirements.txt"

if ! "${venv_dir}/bin/python" -c "import tkinter" >/dev/null 2>&1; then
    echo
    echo "Pillow was installed, but tkinter is missing. Install the system GUI package:" >&2
    if command -v dnf >/dev/null 2>&1; then
        echo "  sudo dnf install python3-tkinter" >&2
    elif command -v apt-get >/dev/null 2>&1; then
        echo "  sudo apt-get install python3-tk" >&2
    elif command -v pacman >/dev/null 2>&1; then
        echo "  sudo pacman -S tk" >&2
    else
        echo "  Install the Tk package for your Linux distribution." >&2
    fi
    exit 1
fi

echo
 echo "Installation complete. Start the app with:"
echo "  ${venv_dir}/bin/python ${project_dir}/kde_light_dark.py"
