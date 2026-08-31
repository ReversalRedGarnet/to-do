"""
THROWAWAY Phase 1 spike — NOT the real NotificationService.

Goal: prove a Windows toast notification can fire from a PyInstaller-frozen
exe using winotify, before any real feature work begins (brief §2.a).

Usage:
    .venv\\Scripts\\python.exe scripts\\notification_spike.py            # unfrozen sanity check
    .venv\\Scripts\\pyinstaller.exe --onefile scripts\\notification_spike.py
    dist\\notification_spike.exe                                          # the actual go/no-go
"""

import sys


def main() -> int:
    try:
        from winotify import Notification
    except Exception as exc:  # pragma: no cover - spike only
        print(f"SPIKE FAILED: could not import winotify: {exc}")
        return 1

    try:
        toast = Notification(
            app_id="TaskPlanner Spike",
            title="Notification spike",
            msg="If you can see this, frozen-exe toasts work.",
            duration="short",
        )
        toast.show()
    except Exception as exc:  # pragma: no cover - spike only
        print(f"SPIKE FAILED: winotify raised: {exc}")
        return 1

    print("SPIKE OK: toast.show() completed without raising.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
