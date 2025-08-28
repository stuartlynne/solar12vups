import os
import sys
import stat
import shutil
import subprocess
from pathlib import Path

SYSTEM_APPLICATIONS_DIR = Path('/usr/share/applications')
SYSTEM_ICON_BASE = Path('/usr/share/icons/hicolor')


DESKTOP_NAME = 'solar12vups.desktop'
ICON_THEME_NAME = 'solar12vups'


def _write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    # Make executable if .desktop
    if path.suffix == '.desktop':
        st = path.stat()
        path.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _find_exec_path() -> str:
    # Prefer the console script if available in PATH
    exe = shutil.which('solar12vups')
    if exe:
        return exe
    # Fallback to scripts directory under the current prefix
    # Works for virtualenvs and system installs
    scripts_dir = 'Scripts' if os.name == 'nt' else 'bin'
    candidate = Path(sys.prefix) / scripts_dir / 'solar12vups'
    return str(candidate)


def _find_icon_source() -> str:
    # Prefer installed locations
    candidates = [
        Path(sys.prefix) / 'share' / 'solar12vups' / 'favicon.png',
        Path('/usr/local/share/solar12vups/favicon.png'),
        Path('/usr/share/solar12vups/favicon.png'),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # Fallback to repo-root favicon if running from source
    repo_icon = Path(__file__).resolve().parents[1] / 'favicon.png'
    if repo_icon.exists():
        return str(repo_icon)
    return ''


def _install_icon_user(icon_source: str) -> None:
    """Copy the icon into the user's icon theme at common sizes for proper scaling."""
    if not icon_source:
        return
    sizes = (48, 64, 128, 256)
    for sz in sizes:
        icon_target = Path.home() / '.local' / 'share' / 'icons' / 'hicolor' / f'{sz}x{sz}' / 'apps' / f'{ICON_THEME_NAME}.png'
        icon_target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(icon_source, icon_target)
        except Exception:
            pass


def write_desktop_to_user(exec_path: str, icon_path: str) -> Path:
    desktop_dir = Path.home() / 'Desktop'
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = desktop_dir / DESKTOP_NAME
    # Prefer themed icon name for consistent scaling
    _install_icon_user(icon_path)

    content = f"""[Desktop Entry]
Name=Solar12VUPS
Type=Application
Comment=Solar-powered UPS monitor (BLE + Tkinter GUI)
Exec={exec_path}
Icon={ICON_THEME_NAME}
Terminal=false
Categories=Utility;System;
Keywords=Solar;UPS;Battery;BLE;Monitoring;
StartupNotify=true
"""
    _write_file(desktop_file, content)
    return desktop_file


def install_into_menu(exec_path: str, icon_source: str):
    # Ensure themed icons exist for proper scaling
    _install_icon_user(icon_source)

    # Write .desktop into user applications dir
    applications_dir = Path.home() / '.local' / 'share' / 'applications'
    applications_dir.mkdir(parents=True, exist_ok=True)
    desktop_menu_file = applications_dir / DESKTOP_NAME
    content = f"""[Desktop Entry]
Name=Solar12VUPS
Type=Application
Comment=Solar-powered UPS monitor (BLE + Tkinter GUI)
TryExec={exec_path}
Exec={exec_path}
Icon={ICON_THEME_NAME}
Terminal=false
Categories=Utility;System;
Keywords=Solar;UPS;Battery;BLE;Monitoring;
StartupNotify=true
"""
    _write_file(desktop_menu_file, content)

    # Attempt to refresh caches (best-effort)
    try:
        subprocess.run(['update-desktop-database', str(applications_dir)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _install_icon_system(icon_source: str) -> None:
    if not icon_source:
        return
    sizes = (48, 64, 128, 256)
    for sz in sizes:
        target_icon = SYSTEM_ICON_BASE / f'{sz}x{sz}' / 'apps' / f'{ICON_THEME_NAME}.png'
        target_icon.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(icon_source, target_icon)
        except Exception:
            pass


def install_into_system_menu(exec_path: str, icon_source: str):
    # Copy icon into system icon theme at common sizes
    _install_icon_system(icon_source)

    # Write .desktop into system applications dir
    SYSTEM_APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    desktop_menu_file = SYSTEM_APPLICATIONS_DIR / DESKTOP_NAME
    content = f"""[Desktop Entry]
Name=Solar12VUPS
Type=Application
Comment=Solar-powered UPS monitor (BLE + Tkinter GUI)
TryExec={exec_path}
Exec={exec_path}
Icon={ICON_THEME_NAME}
Terminal=false
Categories=Utility;System;
Keywords=Solar;UPS;Battery;BLE;Monitoring;
StartupNotify=true
"""
    _write_file(desktop_menu_file, content)

    # Refresh caches (best-effort)
    try:
        subprocess.run(['update-desktop-database', str(SYSTEM_APPLICATIONS_DIR.parent)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    try:
        subprocess.run(['gtk-update-icon-cache', '-f', str(SYSTEM_ICON_BASE)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    do_menu = False
    icon_override = ''
    exec_override = ''
    to_system = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--menu', '--applications'):
            do_menu = True
        elif a in ('--system',):
            to_system = True
        elif a == '--icon' and i + 1 < len(argv):
            icon_override = argv[i + 1]
            i += 1
        elif a == '--exec' and i + 1 < len(argv):
            exec_override = argv[i + 1]
            i += 1
        i += 1

    exec_path = exec_override or _find_exec_path()
    icon_path = icon_override or _find_icon_source()

    # Always write user's Desktop shortcut
    desktop_written = write_desktop_to_user(exec_path, icon_path or 'favicon.png')
    if do_menu:
        if to_system or (hasattr(os, 'geteuid') and os.geteuid() == 0):
            install_into_system_menu(exec_path, icon_path)
            print("Installed application menu entry to /usr/share/applications")
        else:
            install_into_menu(exec_path, icon_path)
            print("Installed application menu entry to ~/.local/share/applications")

    print(f"Wrote desktop shortcut: {desktop_written}")


if __name__ == '__main__':
    main()
